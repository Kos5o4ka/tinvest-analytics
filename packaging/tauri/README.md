# Оболочка TAnalytic на Tauri v2

Нативный десктопный контейнер (Rust + WebView2 на Windows / WKWebView на macOS), запускающий Python-сервер `TAnalytic-backend` как локальный sidecar на случайном свободном порту `127.0.0.1`.

## Структура `src-tauri/`

- `Cargo.toml` — зависимости Tauri v2 (`tray-icon`, `single-instance`, `dialog`, `autostart`, `serde`, `serde_json`). HTTP-проверка `/api/ping` и завершение `/api/app/shutdown` реализованы поверх `std::net::TcpStream` без внешних HTTP-клиентов.
- `tauri.conf.json` — параметры окна (`1280×860`, минимум `960×640`, безрамочное на Windows и `Overlay` на macOS) и бандла (`ru.tanalytic.app`).
- `capabilities/default.json` — права IPC для локального сервера `http://127.0.0.1:*/*` и `http://localhost:*/*` (управление окном, диалог файлов, автозапуск).
- `src/lib.rs` — поиск свободного порта, запуск sidecar (`--no-window --port <port>`), ожидание `/api/ping` (до 15 с), системный трей, единичный экземпляр, нативная биометрия (`LAContext` на macOS / `UserConsentVerifier` на Windows) и корректное завершение сервера (`POST /api/app/shutdown`).
- `icons/` — сгенерированные из `packaging/make_icon.py` иконки (`32x32.png`, `128x128.png`, `128x128@2x.png`, `icon.icns`, `icon.ico`).

## Локальная сборка для разработки

1. Соберите единый backend-скрипт из модулей:
   ```bash
   python3 build.py
   ```
2. Установите Rust (`rustup`) и CLI Tauri v2 (`cargo install tauri-cli --version "^2"`), затем запустите:
   ```bash
   cd src-tauri && cargo tauri dev
   ```
   В режиме разработки `src-tauri/src/lib.rs` автоматически находит `tinvest_analytics.py` в корне репозитория и запускает его через `python3`.

## Продуктовая сборка с sidecar

Сборка для macOS (`aarch64-apple-darwin`, `x86_64-apple-darwin`) и Windows (`x86_64-pc-windows-msvc`) автоматизирована в `.github/workflows/tauri.yml`:

1. PyInstaller собирает `TAnalytic-backend` (`--onefile --noconsole`) из `tinvest_analytics.py`.
2. Бинарник кладётся в `src-tauri/binaries/TAnalytic-backend-<target_triple>(.exe)`.
3. `cargo tauri build` подключает его через `--config '{"bundle":{"externalBin":["binaries/TAnalytic-backend"]}}'`.
