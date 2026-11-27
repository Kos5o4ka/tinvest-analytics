use serde::Serialize;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindow, WebviewWindowBuilder};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_updater::UpdaterExt;

const MAX_PICK_BYTES: u64 = 50_000_000;
const PING_TIMEOUT: Duration = Duration::from_secs(60);
const SHUTDOWN_WAIT: Duration = Duration::from_secs(3);
const RETRY_HOST: &str = "retry.tanalytic.invalid";

/// Внешние http(s)-ссылки (в том числе target=_blank и window.open) уходят в навигацию главного окна,
/// где on_navigation отклоняет их и открывает системный браузер.
const EXTERNAL_LINKS_JS: &str = r#"(function(){
  if (window.__taExt) return;
  window.__taExt = 1;
  function ext(u) {
    try {
      var x = new URL(u, location.href);
      if ((x.protocol === 'http:' || x.protocol === 'https:') && x.origin !== location.origin) return x.href;
    } catch (e) {}
    return null;
  }
  window.open = function (u) {
    var h = u ? ext(String(u)) : null;
    if (h) location.assign(h);
    return null;
  };
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a) return;
    var h = ext(a.href);
    if (h) { e.preventDefault(); location.assign(h); }
  }, true);
})();"#;

struct BackendState {
    port: u16,
    child: Mutex<Option<Child>>,
    shutdown_done: AtomicBool,
    attempt: AtomicU64,
}

#[derive(Serialize)]
struct UpdateInfo {
    version: String,
    notes: Option<String>,
}

#[derive(Serialize)]
struct PickedFile {
    name: String,
    b64: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

fn find_free_port() -> Result<u16, String> {
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|e| e.to_string())?;
    let port = listener.local_addr().map_err(|e| e.to_string())?.port();
    Ok(port)
}

fn http_get_ping(port: u16) -> bool {
    let addr: SocketAddr = ([127, 0, 0, 1], port).into();
    let Ok(mut stream) = TcpStream::connect_timeout(&addr, Duration::from_millis(250)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(400)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(400)));
    let req = format!(
        "GET /api/ping HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut buf = Vec::with_capacity(512);
    let _ = stream.read_to_end(&mut buf);
    let text = String::from_utf8_lossy(&buf);
    let Some((head, body)) = text.split_once("\r\n\r\n") else {
        return false;
    };
    if !head.starts_with("HTTP/1.1 200") && !head.starts_with("HTTP/1.0 200") {
        return false;
    }
    serde_json::from_str::<serde_json::Value>(body.trim())
        .ok()
        .and_then(|v| v.get("app").and_then(|a| a.as_str()).map(|s| s == "TAnalytic"))
        .unwrap_or(false)
}

fn http_post_shutdown(port: u16) {
    let addr: SocketAddr = ([127, 0, 0, 1], port).into();
    if let Ok(mut stream) = TcpStream::connect_timeout(&addr, Duration::from_millis(300)) {
        let _ = stream.set_read_timeout(Some(Duration::from_millis(400)));
        let _ = stream.set_write_timeout(Some(Duration::from_millis(400)));
        let req = format!(
            "POST /api/app/shutdown HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{{}}"
        );
        let _ = stream.write_all(req.as_bytes());
        let mut sink = [0u8; 256];
        let _ = stream.read(&mut sink);
    }
}

enum SidecarTarget {
    Binary(PathBuf),
    PythonScript { python: String, script: PathBuf },
}

#[cfg(target_os = "windows")]
const BACKEND_EXE: &str = "TAnalytic-backend.exe";
#[cfg(not(target_os = "windows"))]
const BACKEND_EXE: &str = "TAnalytic-backend";

/// Python-сервер лежит в ресурсах бандла (PyInstaller --onedir): <resource_dir>/backend/TAnalytic-backend[.exe].
fn locate_sidecar(resource_dir: Option<PathBuf>) -> Result<SidecarTarget, String> {
    let mut dirs: Vec<PathBuf> = Vec::new();
    if let Some(r) = resource_dir {
        dirs.push(r.join("backend"));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(d) = exe.parent() {
            dirs.push(d.join("backend"));
            dirs.push(d.join("../Resources/backend"));
        }
    }
    for dir in dirs {
        let cand = dir.join(BACKEND_EXE);
        if cand.is_file() {
            return Ok(SidecarTarget::Binary(cand));
        }
    }

    let mut search_roots: Vec<PathBuf> = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        search_roots.push(cwd.clone());
        if let Some(p) = cwd.parent() {
            search_roots.push(p.to_path_buf());
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        for anc in exe.ancestors().skip(1).take(5) {
            search_roots.push(anc.to_path_buf());
        }
    }
    for root in search_roots {
        let script = root.join("tinvest_analytics.py");
        if script.is_file() {
            let python = if cfg!(target_os = "windows") {
                "python".to_string()
            } else {
                "python3".to_string()
            };
            return Ok(SidecarTarget::PythonScript { python, script });
        }
    }

    Err("Не найден сервер TAnalytic-backend (папка backend рядом с программой) или tinvest_analytics.py".to_string())
}

fn spawn_sidecar(app: &AppHandle, port: u16) -> Result<Child, String> {
    let target = locate_sidecar(app.path().resource_dir().ok())?;
    let port_str = port.to_string();
    let pid_str = std::process::id().to_string();
    let mut cmd = match target {
        SidecarTarget::Binary(bin) => Command::new(bin),
        SidecarTarget::PythonScript { python, script } => {
            let mut c = Command::new(python);
            c.arg(script);
            c
        }
    };
    // --parent-pid: сервер сам завершится, если оболочку убили или она упала (в onefile-сборке
    // прямой родитель Python — загрузчик PyInstaller, поэтому полагаемся именно на этот PID).
    cmd.args([
        "--no-window",
        "--port",
        port_str.as_str(),
        "--parent-pid",
        pid_str.as_str(),
    ]);
    cmd.env("PYTHONUTF8", "1")
        .env("TINVEST_SHELL", "tauri")
        .env("TINVEST_SHELL_REV", "5")
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    cmd.spawn()
        .map_err(|e| format!("Не удалось запустить сервер TAnalytic: {e}"))
}

fn shutdown_backend(state: &BackendState) {
    if state.shutdown_done.swap(true, Ordering::SeqCst) {
        return;
    }
    http_post_shutdown(state.port);
    if let Ok(mut guard) = state.child.lock() {
        if let Some(mut child) = guard.take() {
            let deadline = Instant::now() + SHUTDOWN_WAIT;
            loop {
                match child.try_wait() {
                    Ok(Some(_)) => return,
                    Ok(None) if Instant::now() < deadline => {
                        std::thread::sleep(Duration::from_millis(50));
                    }
                    _ => break,
                }
            }
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn failure_hint() -> &'static str {
    if cfg!(debug_assertions) {
        " Проверьте, что установлен Python 3 и рядом есть tinvest_analytics.py."
    } else {
        " Закройте программу и запустите её снова. Если ошибка повторяется, проверьте, что антивирус не блокирует TAnalytic-backend."
    }
}

fn navigate_html(win: &WebviewWindow, html: &str) {
    if let Ok(url) = tauri::Url::parse(html) {
        let _ = win.navigate(url);
    }
}

/// Запускает (или перезапускает) sidecar и ждёт его готовности в фоновом потоке.
fn start_backend(app: &AppHandle) {
    let state = app.state::<BackendState>();
    let attempt = state.attempt.fetch_add(1, Ordering::SeqCst) + 1;
    if let Some(win) = app.get_webview_window("main") {
        navigate_html(&win, &build_splash_html("Запускаю сервер портфеля…", false, false));
    }
    let had_old = match state.child.lock() {
        Ok(mut guard) => match guard.take() {
            Some(mut old) => {
                let _ = old.kill();
                let _ = old.wait();
                true
            }
            None => false,
        },
        Err(_) => false,
    };
    if had_old {
        http_post_shutdown(state.port);
    }
    let mut spawn_error: Option<String> = None;
    match spawn_sidecar(app, state.port) {
        Ok(ch) => {
            if let Ok(mut guard) = state.child.lock() {
                *guard = Some(ch);
            }
        }
        Err(e) => spawn_error = Some(e),
    }
    let handle = app.clone();
    std::thread::spawn(move || wait_for_backend(handle, attempt, spawn_error));
}

fn wait_for_backend(app: AppHandle, attempt: u64, spawn_error: Option<String>) {
    let state = app.state::<BackendState>();
    let port = state.port;
    let mut failure: Option<String> = spawn_error;
    if failure.is_none() {
        let deadline = Instant::now() + PING_TIMEOUT;
        loop {
            if state.attempt.load(Ordering::SeqCst) != attempt {
                return;
            }
            if http_get_ping(port) {
                break;
            }
            if let Ok(mut guard) = state.child.lock() {
                if let Some(ch) = guard.as_mut() {
                    if let Ok(Some(status)) = ch.try_wait() {
                        let code = match status.code() {
                            Some(c) => format!("код {c}"),
                            None => "по сигналу".to_string(),
                        };
                        failure = Some(format!(
                            "Сервер TAnalytic неожиданно завершился ({code}).{}",
                            failure_hint()
                        ));
                        break;
                    }
                }
            }
            if Instant::now() >= deadline {
                failure = Some(format!(
                    "Сервер TAnalytic не ответил за {} секунд.{}",
                    PING_TIMEOUT.as_secs(),
                    failure_hint()
                ));
                break;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
    }
    if state.attempt.load(Ordering::SeqCst) != attempt {
        return;
    }
    let Some(win) = app.get_webview_window("main") else {
        return;
    };
    match failure {
        None => {
            if let Ok(url) = tauri::Url::parse(&format!("http://127.0.0.1:{port}/")) {
                let _ = win.navigate(url);
            }
        }
        Some(msg) => navigate_html(&win, &build_splash_html(&msg, true, true)),
    }
}

/// Открывает http(s)-ссылку в системном браузере (без оболочки командной строки).
fn open_external(url: &str) {
    if !(url.starts_with("http://") || url.starts_with("https://")) {
        return;
    }
    #[cfg(target_os = "macos")]
    let res = Command::new("open").arg(url).spawn();
    #[cfg(target_os = "windows")]
    let res = {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        Command::new("rundll32")
            .args(["url.dll,FileProtocolHandler", url])
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
    };
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    let res = Command::new("xdg-open").arg(url).spawn();
    if let Ok(mut child) = res {
        std::thread::spawn(move || {
            let _ = child.wait();
        });
    }
}

/// Главное окно остаётся на своём сервере; всё остальное http(s) открывается в браузере.
fn handle_navigation(app: &AppHandle, url: &tauri::Url) -> bool {
    match url.scheme() {
        "data" | "about" | "blob" => true,
        "http" | "https" => {
            let host = url.host_str().unwrap_or("");
            if host == RETRY_HOST {
                let handle = app.clone();
                std::thread::spawn(move || start_backend(&handle));
                return false;
            }
            if url.scheme() == "http" && host == "127.0.0.1" {
                if let Some(st) = app.try_state::<BackendState>() {
                    if url.port() == Some(st.port) {
                        return true;
                    }
                }
            }
            open_external(url.as_str());
            false
        }
        _ => false,
    }
}

fn show_main_window(app: &AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.show();
        let _ = win.unminimize();
        let _ = win.set_focus();
    }
}

fn b64_encode(bytes: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(((bytes.len() + 2) / 3) * 4);
    for chunk in bytes.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = if chunk.len() > 1 { chunk[1] as u32 } else { 0 };
        let b2 = if chunk.len() > 2 { chunk[2] as u32 } else { 0 };
        let triple = (b0 << 16) | (b1 << 8) | b2;
        out.push(TABLE[((triple >> 18) & 0x3f) as usize] as char);
        out.push(TABLE[((triple >> 12) & 0x3f) as usize] as char);
        out.push(if chunk.len() > 1 {
            TABLE[((triple >> 6) & 0x3f) as usize] as char
        } else {
            '='
        });
        out.push(if chunk.len() > 2 {
            TABLE[(triple & 0x3f) as usize] as char
        } else {
            '='
        });
    }
    out
}

#[tauri::command]
fn tauri_win_minimize(window: WebviewWindow) -> Result<(), String> {
    window.minimize().map_err(|e| e.to_string())
}

#[tauri::command]
fn tauri_win_toggle_max(window: WebviewWindow) -> Result<bool, String> {
    let is_max = window.is_maximized().map_err(|e| e.to_string())?;
    if is_max {
        window.unmaximize().map_err(|e| e.to_string())?;
        Ok(false)
    } else {
        window.maximize().map_err(|e| e.to_string())?;
        Ok(true)
    }
}

#[tauri::command]
fn tauri_win_close(window: WebviewWindow) -> Result<(), String> {
    window.close().map_err(|e| e.to_string())
}

#[tauri::command]
async fn tauri_pick_file(app: AppHandle) -> Result<Option<PickedFile>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let picked = app
            .dialog()
            .file()
            .add_filter(
                "Отчёты брокера",
                &["xlsx", "xls", "xlsm", "csv", "txt", "html", "htm", "xml"],
            )
            .blocking_pick_file();
        let Some(fp) = picked else {
            return Ok(None);
        };
        let path = fp.into_path().map_err(|e| e.to_string())?;
        let name = path
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("report")
            .to_string();
        let meta = std::fs::metadata(&path).map_err(|e| e.to_string())?;
        if meta.len() > MAX_PICK_BYTES {
            return Ok(Some(PickedFile {
                name,
                b64: String::new(),
                error: Some("Файл больше 50 МБ".to_string()),
            }));
        }
        let bytes = std::fs::read(&path).map_err(|e| e.to_string())?;
        Ok(Some(PickedFile {
            name,
            b64: b64_encode(&bytes),
            error: None,
        }))
    })
    .await
    .map_err(|e| e.to_string())?
}

/// Скачанное в фоне обновление ждёт перезапуска: пользователь нажимает кнопку в баннере, иначе оно ставится при закрытии.
struct PendingUpdate {
    slot: Mutex<Option<(tauri_plugin_updater::Update, Vec<u8>)>>,
}

fn pending_version(app: &AppHandle) -> Option<UpdateInfo> {
    let pend = app.try_state::<PendingUpdate>()?;
    let guard = pend.slot.lock().ok()?;
    guard.as_ref().map(|(u, _)| UpdateInfo {
        version: u.version.clone(),
        notes: u.body.clone(),
    })
}

/// Проверяет latest.json и, если есть подписанное обновление, скачивает его в память (подпись проверяет плагин).
async fn check_and_download(app: &AppHandle) -> Result<(), String> {
    if pending_version(app).is_some() {
        return Ok(());
    }
    let updater = app.updater().map_err(|e| e.to_string())?;
    let Some(update) = updater.check().await.map_err(|e| e.to_string())? else {
        return Ok(());
    };
    let bytes = update
        .download(|_chunk, _total| {}, || {})
        .await
        .map_err(|e| e.to_string())?;
    if let Some(pend) = app.try_state::<PendingUpdate>() {
        if let Ok(mut guard) = pend.slot.lock() {
            *guard = Some((update, bytes));
        }
    }
    Ok(())
}

/// Проверка при старте (через 20 с, когда окно уже загрузилось) и затем раз в 6 часов.
fn start_update_loop(app: AppHandle) {
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(20));
        loop {
            let _ = tauri::async_runtime::block_on(check_and_download(&app));
            std::thread::sleep(Duration::from_secs(6 * 60 * 60));
        }
    });
}

/// Версия уже скачанного обновления (или null): баннер в программе опрашивает эту команду.
#[tauri::command]
fn tauri_update_status(app: AppHandle) -> Option<UpdateInfo> {
    pending_version(&app)
}

/// Принудительная проверка; возвращает версию готового обновления.
#[tauri::command]
async fn tauri_update_check(app: AppHandle) -> Result<Option<UpdateInfo>, String> {
    check_and_download(&app).await?;
    Ok(pending_version(&app))
}

/// Ставит скачанное обновление и перезапускает программу. Вызывается по кнопке «Перезапустить».
#[tauri::command]
fn tauri_update_apply(app: AppHandle) -> Result<(), String> {
    let taken = app
        .try_state::<PendingUpdate>()
        .and_then(|p| p.slot.lock().ok().and_then(|mut g| g.take()));
    let Some((update, bytes)) = taken else {
        return Err("Обновление ещё не скачано".to_string());
    };
    // сервер закрываем до замены файлов (на Windows установщик завершает программу сам)
    if let Some(st) = app.try_state::<BackendState>() {
        shutdown_backend(&st);
    }
    if let Err(e) = update.install(bytes) {
        if let Some(st) = app.try_state::<BackendState>() {
            st.shutdown_done.store(false, Ordering::SeqCst);
        }
        start_backend(&app);
        return Err(e.to_string());
    }
    app.restart()
}

/// Не нажали «Перезапустить» — обновление ставится при закрытии программы.
fn install_pending_on_exit(app: &AppHandle) {
    let taken = app
        .try_state::<PendingUpdate>()
        .and_then(|p| p.slot.lock().ok().and_then(|mut g| g.take()));
    if let Some((update, bytes)) = taken {
        let _ = update.install(bytes);
    }
}

fn build_splash_html(message: &str, is_error: bool, retry: bool) -> String {
    let color = if is_error { "#f0626a" } else { "#94a3b8" };
    let button = if retry {
        format!(
            "<div><a href=\"https://{RETRY_HOST}/\" style=\"display:inline-block;margin-top:18px;padding:8px 20px;border-radius:8px;background:%233b82f6;color:%23ffffff;text-decoration:none;font-weight:600\">Повторить</a></div>"
        )
    } else {
        String::new()
    };
    let safe_msg = message
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('%', "%25")
        .replace('#', "%23");
    format!(
        "data:text/html;charset=utf-8,<!doctype html><html><body style=\"margin:0;height:100vh;display:grid;place-items:center;background:%2307090e;color:%23f1f5f9;font:14px/1.5 -apple-system,Segoe UI,sans-serif;user-select:none\"><div style=\"text-align:center;max-width:420px;padding:24px\"><div style=\"font-size:18px;font-weight:700;margin-bottom:8px\">TAnalytic</div><div style=\"color:{color}\">{msg}</div>{button}</div></body></html>",
        color = color.replace('#', "%23"),
        msg = safe_msg,
        button = button
    )
}

fn setup_tray(app: &AppHandle) -> Result<(), tauri::Error> {
    let open_item = MenuItem::with_id(app, "open", "Открыть TAnalytic", true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "quit", "Выход", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open_item, &quit_item])?;

    let mut builder = TrayIconBuilder::new()
        .menu(&menu)
        .tooltip("TAnalytic")
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => show_main_window(app),
            "quit" => {
                if let Some(st) = app.try_state::<BackendState>() {
                    shutdown_backend(&st);
                }
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main_window(tray.app_handle());
            }
        });

    if let Some(icon) = app.default_window_icon().cloned() {
        builder = builder.icon(icon);
    }
    builder.build(app)?;
    Ok(())
}

fn create_main_window(app: &AppHandle) -> Result<WebviewWindow, tauri::Error> {
    let splash = build_splash_html("Запускаю сервер портфеля…", false, false);
    let splash_url = tauri::Url::parse(&splash).unwrap_or_else(|_| {
        tauri::Url::parse("about:blank").expect("valid about:blank")
    });

    let mut builder = if let Some(cfg) = app.config().app.windows.first() {
        let mut cfg = cfg.clone();
        cfg.url = WebviewUrl::External(splash_url);
        WebviewWindowBuilder::from_config(app, &cfg)?
    } else {
        WebviewWindowBuilder::new(app, "main", WebviewUrl::External(splash_url))
            .title("TAnalytic")
            .inner_size(1280.0, 860.0)
            .min_inner_size(960.0, 640.0)
            .center()
            .decorations(false)
    };

    #[cfg(target_os = "macos")]
    {
        builder = builder
            .decorations(true)
            .title_bar_style(tauri::TitleBarStyle::Overlay)
            .hidden_title(true);
    }

    let nav_app = app.clone();
    builder = builder
        .initialization_script(EXTERNAL_LINKS_JS)
        .on_navigation(move |url| handle_navigation(&nav_app, url));

    builder.build()
}

pub fn run() {
    let port = find_free_port().expect("failed to bind ephemeral localhost port");

    tauri::Builder::default()
        // single-instance — первым плагином: вторая копия завершается до запуска sidecar (он стартует в setup)
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_main_window(app);
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(PendingUpdate {
            slot: Mutex::new(None),
        })
        .manage(BackendState {
            port,
            child: Mutex::new(None),
            shutdown_done: AtomicBool::new(false),
            attempt: AtomicU64::new(0),
        })
        .invoke_handler(tauri::generate_handler![
            tauri_win_minimize,
            tauri_win_toggle_max,
            tauri_win_close,
            tauri_pick_file,
            tauri_update_status,
            tauri_update_check,
            tauri_update_apply,
        ])
        .setup(|app| {
            setup_tray(app.handle())?;
            create_main_window(app.handle())?;
            start_backend(app.handle());
            start_update_loop(app.handle().clone());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building TAnalytic Tauri application")
        .run(|app_handle, event| match event {
            RunEvent::ExitRequested { .. } | RunEvent::Exit => {
                if let Some(st) = app_handle.try_state::<BackendState>() {
                    shutdown_backend(&st);
                }
                install_pending_on_exit(app_handle);
            }
            _ => {}
        });
}
