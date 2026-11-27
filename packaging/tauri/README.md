# Оболочка TAnalytic на Tauri v2

Основная оболочка приложения: нативный контейнер (Rust + WebView2 на Windows / WKWebView на macOS), который запускает Python-сервер `TAnalytic-backend` как sidecar на случайном свободном порту `127.0.0.1`. Релизы собирает `.github/workflows/release.yml`.

## Статус

Tauri — основная оболочка релиза. Старая оболочка pywebview (`tinvest.py`, `packaging/tinvest.spec`) больше не собирается в релизе; лаунчер остаётся в репозитории как запасной запуск из исходников. Файлы `packaging/TAnalytic.iss`, `packaging/make_dmg.sh`, `make_dmg_bg.py`, `mac_codesign.sh` оставлены как устаревшие (на них ещё ссылаются тесты старого лаунчера и справка `packaging/README.md`); их можно удалить после того, как не останется пользователей оболочки pywebview.

Публикуемые файлы (имена стабильны: их ждут баннер обновления и README):

| Файл | Что это |
|---|---|
| `TAnalytic-Setup-win.exe` | установщик NSIS, x64, без прав администратора (`%LOCALAPPDATA%\TAnalytic`) |
| `TAnalytic-mac-arm64.dmg`, `TAnalytic-mac-x64.dmg` | образы macOS (Apple Silicon и Intel) |
| `*.sig`, `TAnalytic-mac-*.app.tar.gz`, `latest.json` | артефакты автообновления (только при подписи, см. ниже) |
| `tinvest_analytics.py`, `SHA256SUMS` | как раньше |

## Структура `src-tauri/`

- `Cargo.toml`, `Cargo.lock` — Tauri v2 (`tray-icon`), плагины `single-instance`, `dialog`, `autostart`, `updater`. Проверка `/api/ping` и `POST /api/app/shutdown` идут через `std::net::TcpStream`.
- `tauri.conf.json` — окно, бандл (`externalBin`, NSIS, DMG, `createUpdaterArtifacts`), `plugins.updater`.
- `capabilities/default.json` — IPC только для `http://127.0.0.1:*/*`.
- `src/lib.rs` — порт, запуск sidecar в `setup()` (после single-instance), ожидание `/api/ping` до 60 с с кнопкой «Повторить», трей, `on_navigation` (внешние ссылки открываются в системном браузере), команды окна, выбора файла, автозапуска и обновления.
- `installer/` — картинки установщиков (`header.bmp`, `sidebar.bmp`, `dmg-background.png`; генерирует `packaging/tauri/make_installer_art.py`, нужен Pillow) и `hooks.nsh`.
- `entitlements.plist` — права hardened runtime для macOS (копия `packaging/entitlements.plist`: Python-sidecar выделяет исполняемую память и грузит чужие библиотеки).

## Как sidecar связан с оболочкой

- Оболочка передаёт `--no-window --port <порт> --parent-pid <PID оболочки>` и переменные `TINVEST_SHELL=tauri`, `TINVEST_SHELL_REV=5`.
- Сервер раз в 2 с проверяет, жив ли процесс `--parent-pid`; если оболочку убили или она упала, сервер сам завершается (в onefile-сборке PyInstaller прямой родитель Python — загрузчик, поэтому PID передаётся явно). Job Object на Windows не используется: `--parent-pid` закрывает ту же проблему без `unsafe`.
- При штатном выходе оболочка шлёт `POST /api/app/shutdown`, ждёт до 3 с и только затем убивает процесс.
- Под Tauri карточка «Окно программы» (трей и реестр Run) в Настройках скрыта: там остаётся только «Запускать вместе с системой» через `tauri_autostart_*`. Автозапуск стартует без аргументов; пункт трея «Открыть» показывает окно.
- Блокировку программы целиком показывает сервер (экран PIN); оболочка биометрию не запрашивает.

## Установщик Windows

NSIS (русский язык, `currentUser`, свои картинки, ярлыки). WebView2 скачивается bootstrapper-ом, если его нет. Хук `installer/hooks.nsh` при установке находит старую установку Inno Setup по `AppId` (`HKCU\...\Uninstall\{EFBF9C3A-...}_is1`), тихо запускает её деинсталлятор (`/VERYSILENT /SUPPRESSMSGBOXES`, данные в `%USERPROFILE%\.tinvest_analytics` в тихом режиме не удаляются: вопрос о них задаётся только при `not UninstallSilent`) и убирает старый автозапуск (значение `TAnalytic` в `HKCU\...\Run`, оканчивающееся на ` --tray`).

## Установщик macOS

DMG с фоном 660x400, значок приложения слева и «Программы» справа. `minimumSystemVersion` 11.0. Без секретов Apple сборка не падает (подпись ad-hoc, при первом запуске нужно «Открыть» в меню Finder или разрешить в «Конфиденциальность и безопасность»).

## Автообновление

Плагин `tauri-plugin-updater`, адрес: `https://github.com/Kos5o4ka/tinvest-analytics/releases/latest/download/latest.json`, публичный ключ вписан в `tauri.conf.json`. В программе баннер (`66_shell_notice.js`) спрашивает обновление командой `tauri_update_check` и после согласия пользователя вызывает `tauri_update_install` (скачивание, проверка подписи, закрытие сервера, установка, перезапуск).

Ключ подписи уже создан владельцем локально (`~/.tauri/tanalytic.key`, пароль пустой). Нужно один раз добавить секреты репозитория (Settings, Secrets and variables, Actions):

1. `TAURI_SIGNING_PRIVATE_KEY` — содержимое файла `~/.tauri/tanalytic.key`.
2. `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` — пустая строка (или пароль, если задавали).

Новую пару при необходимости создают так: `cargo tauri signer generate -w ~/.tauri/tanalytic.key` (или `npx @tauri-apps/cli signer generate -w ...`); публичный ключ из `.key.pub` вписывают в `plugins.updater.pubkey`, секретный остаётся только у владельца. Без секрета `TAURI_SIGNING_PRIVATE_KEY` workflow отключает артефакты обновления (`createUpdaterArtifacts: false`), печатает предупреждение, `latest.json` не создаётся, а сборка не падает.

## Подпись macOS (необязательно)

Секреты: `APPLE_CERTIFICATE` (сертификат Developer ID Application в base64 `.p12`), `APPLE_CERTIFICATE_PASSWORD`, `APPLE_ID`, `APPLE_PASSWORD` (пароль приложения), `APPLE_TEAM_ID`. `tauri-action` импортирует сертификат, Tauri подписывает бандл (включая sidecar из `externalBin`) с правами из `entitlements.plist` и отправляет на нотаризацию.

## Переход пользователей pywebview

`SHELL_REV_LATEST` в `src/py/13z_shell.py` равен 5; sidecar Tauri сообщает ревизию 5 и `TINVEST_SHELL=tauri`, поэтому у него баннер оболочки не показывается. У оболочек pywebview (ревизия 4 и ниже) баннер предлагает установить новую версию: Windows скачивает `TAnalytic-Setup-win.exe`, сверяет сумму и запускает его (старые лаунчеры передают ключи Inno, NSIS показывает обычное окно установщика; хук удаляет старую копию), macOS заменяет `.app` из `.dmg`.

## Локальная разработка и сборка

```bash
python3 build.py
mkdir -p src-tauri/binaries && touch src-tauri/binaries/TAnalytic-backend-aarch64-apple-darwin   # заглушка для cargo check
cd src-tauri && cargo check --target aarch64-apple-darwin
cargo tauri dev        # найдёт tinvest_analytics.py в корне и запустит python3
```

Полная сборка (`cargo tauri build --target ...`) требует настоящего sidecar `src-tauri/binaries/TAnalytic-backend-<triple>`, как в `release.yml`. Без ключа обновлений добавьте `--config '{"bundle":{"createUpdaterArtifacts":false}}'`.
