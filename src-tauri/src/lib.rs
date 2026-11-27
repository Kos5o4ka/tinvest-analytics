use serde::Serialize;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindow, WebviewWindowBuilder};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt as AutostartManagerExt};
use tauri_plugin_dialog::DialogExt;

const MAX_PICK_BYTES: u64 = 50_000_000;
const PING_TIMEOUT: Duration = Duration::from_secs(15);

struct BackendState {
    port: u16,
    child: Mutex<Option<Child>>,
    shutdown_done: AtomicBool,
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

fn locate_sidecar() -> Result<SidecarTarget, String> {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let mut candidates: Vec<PathBuf> = Vec::new();
            #[cfg(target_os = "windows")]
            {
                candidates.push(dir.join("TAnalytic-backend.exe"));
                candidates.push(dir.join("TAnalytic-backend").join("TAnalytic-backend.exe"));
            }
            #[cfg(not(target_os = "windows"))]
            {
                candidates.push(dir.join("TAnalytic-backend"));
                candidates.push(dir.join("TAnalytic-backend").join("TAnalytic-backend"));
                candidates.push(dir.join("../Resources/TAnalytic-backend"));
                candidates.push(dir.join("../Resources/TAnalytic-backend/TAnalytic-backend"));
            }
            for cand in candidates {
                if cand.is_file() {
                    return Ok(SidecarTarget::Binary(cand));
                }
            }
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

    Err("Не найден сервер TAnalytic-backend или tinvest_analytics.py".to_string())
}

fn spawn_sidecar(port: u16) -> Result<Child, String> {
    let target = locate_sidecar()?;
    let port_str = port.to_string();
    let mut cmd = match target {
        SidecarTarget::Binary(bin) => {
            let mut c = Command::new(bin);
            c.args(["--no-window", "--port", &port_str]);
            c
        }
        SidecarTarget::PythonScript { python, script } => {
            let mut c = Command::new(python);
            c.arg(script).args(["--no-window", "--port", &port_str]);
            c
        }
    };
    cmd.env("PYTHONUTF8", "1")
        .env("TINVEST_SHELL_REV", "4")
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
            let deadline = Instant::now() + Duration::from_millis(800);
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

#[tauri::command]
fn tauri_autostart_get(app: AppHandle) -> Result<bool, String> {
    app.autolaunch().is_enabled().map_err(|e| e.to_string())
}

#[tauri::command]
fn tauri_autostart_set(app: AppHandle, enabled: bool) -> Result<bool, String> {
    let mgr = app.autolaunch();
    if enabled {
        mgr.enable().map_err(|e| e.to_string())?;
    } else {
        mgr.disable().map_err(|e| e.to_string())?;
    }
    mgr.is_enabled().map_err(|e| e.to_string())
}

#[tauri::command]
async fn tauri_bio_verify(reason: Option<String>) -> Result<bool, String> {
    let prompt = reason
        .filter(|s| !s.trim().is_empty())
        .unwrap_or_else(|| "Подтвердите вход в TAnalytic".to_string());
    tauri::async_runtime::spawn_blocking(move || bio_verify_native(&prompt))
        .await
        .map_err(|e| e.to_string())?
}

fn bio_verify_native(reason: &str) -> Result<bool, String> {
    #[cfg(target_os = "macos")]
    {
        let swift_code = r#"
import Foundation
import LocalAuthentication

let ctx = LAContext()
let reason = ProcessInfo.processInfo.environment["TA_BIO_REASON"] ?? "Разблокируйте TAnalytic"
var err: NSError?
if !ctx.canEvaluatePolicy(.deviceOwnerAuthentication, error: &err) {
    exit(2)
}
let sem = DispatchSemaphore(value: 0)
var ok = false
ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { success, _ in
    ok = success
    sem.signal()
}
sem.wait()
exit(ok ? 0 : 1)
"#;
        let status = Command::new("swift")
            .arg("-e")
            .arg(swift_code)
            .env("TA_BIO_REASON", reason)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map_err(|e| e.to_string())?;
        return Ok(status.success());
    }

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let ps = r#"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Security.Credentials.UI.UserConsentVerifier,Windows.Security.Credentials.UI,ContentType=WindowsRuntime]
$op = [Windows.Security.Credentials.UI.UserConsentVerifier]::RequestVerificationAsync($env:TA_BIO_REASON)
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.IsGenericMethod })[0].MakeGenericMethod([Windows.Security.Credentials.UI.UserConsentVerificationResult])
$res = $asTask.Invoke($null, @($op)).GetAwaiter().GetResult()
if ($res -eq [Windows.Security.Credentials.UI.UserConsentVerificationResult]::Verified) { exit 0 } else { exit 1 }
"#;
        let status = Command::new("powershell")
            .args(["-NoProfile", "-NonInteractive", "-Command", ps])
            .env("TA_BIO_REASON", reason)
            .creation_flags(CREATE_NO_WINDOW)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map_err(|e| e.to_string())?;
        return Ok(status.success());
    }

    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        let _ = reason;
        Ok(false)
    }
}

fn build_splash_html(message: &str, is_error: bool) -> String {
    let color = if is_error { "#f0626a" } else { "#94a3b8" };
    format!(
        "data:text/html;charset=utf-8,<!doctype html><html><body style=\"margin:0;height:100vh;display:grid;place-items:center;background:%2307090e;color:%23f1f5f9;font:14px/1.5 -apple-system,Segoe UI,sans-serif;user-select:none\"><div style=\"text-align:center;max-width:420px;padding:24px\"><div style=\"font-size:18px;font-weight:700;margin-bottom:8px\">TAnalytic</div><div style=\"color:{color}\">{msg}</div></div></body></html>",
        color = color.replace('#', "%23"),
        msg = message.replace('%', "%25").replace('#', "%23")
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
    let splash = build_splash_html("Запускаю сервер портфеля…", false);
    let splash_url = tauri::Url::parse(&splash).unwrap_or_else(|_| {
        tauri::Url::parse("about:blank").expect("valid about:blank")
    });

    let mut builder = if let Some(cfg) = app.config().app.windows.first() {
        WebviewWindowBuilder::from_config(app, cfg)?.url(WebviewUrl::External(splash_url))
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

    builder.build()
}

pub fn run() {
    let port = find_free_port().expect("failed to bind ephemeral localhost port");
    let child = spawn_sidecar(port).ok();

    tauri::Builder::default()
        .manage(BackendState {
            port,
            child: Mutex::new(child),
            shutdown_done: AtomicBool::new(false),
        })
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_main_window(app);
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            Some(vec!["--tray"]),
        ))
        .invoke_handler(tauri::generate_handler![
            tauri_win_minimize,
            tauri_win_toggle_max,
            tauri_win_close,
            tauri_pick_file,
            tauri_autostart_get,
            tauri_autostart_set,
            tauri_bio_verify,
        ])
        .setup(|app| {
            setup_tray(app.handle())?;
            let win = create_main_window(app.handle())?;
            let handle = app.handle().clone();

            std::thread::spawn(move || {
                let state = handle.state::<BackendState>();
                let port = state.port;
                let deadline = Instant::now() + PING_TIMEOUT;
                let mut ready = false;

                while Instant::now() < deadline {
                    if http_get_ping(port) {
                        ready = true;
                        break;
                    }
                    if let Ok(mut guard) = state.child.lock() {
                        if let Some(ch) = guard.as_mut() {
                            if let Ok(Some(_)) = ch.try_wait() {
                                break;
                            }
                        } else {
                            break;
                        }
                    }
                    std::thread::sleep(Duration::from_millis(100));
                }

                if ready {
                    if let Ok(url) = tauri::Url::parse(&format!("http://127.0.0.1:{port}/")) {
                        let _ = win.navigate(url);
                    }
                } else {
                    let err_html = build_splash_html(
                        "Сервер TAnalytic не ответил вовремя. Проверьте установку Python или перезапустите приложение.",
                        true,
                    );
                    if let Ok(url) = tauri::Url::parse(&err_html) {
                        let _ = win.navigate(url);
                    }
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building TAnalytic Tauri application")
        .run(|app_handle, event| match event {
            RunEvent::ExitRequested { .. } | RunEvent::Exit => {
                if let Some(st) = app_handle.try_state::<BackendState>() {
                    shutdown_backend(&st);
                }
            }
            _ => {}
        });
}
