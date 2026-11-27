# Оболочка TAnalytic на Tauri v2

Основная оболочка приложения: нативный контейнер (Rust + WebView2 на Windows / WKWebView на macOS), который запускает Python-сервер `TAnalytic-backend` как sidecar на случайном свободном порту `127.0.0.1`. Релизы собирает `.github/workflows/release.yml`.

## Статус

Tauri — основная оболочка релиза. Старая оболочка pywebview (`tinvest.py`, `packaging/tinvest.spec`) больше не собирается в релизе; лаунчер остаётся в репозитории как запасной запуск из исходников. Файлы `packaging/TAnalytic.iss`, `packaging/make_dmg.sh`, `make_dmg_bg.py`, `mac_codesign.sh` оставлены как устаревшие (на них ещё ссылаются тесты старого лаунчера и справка `packaging/README.md`); их можно удалить после того, как не останется пользователей оболочки pywebview.

Публикуемые файлы (имена стабильны: их ждут баннер обновления и README):

| Файл | Что это |
|---|---|
| `TAnalytic-Setup-win.exe` | установщик NSIS, x64, без прав администратора (`%LOCALAPPDATA%\TAnalytic`) |
| `TAnalytic-mac-arm64.dmg` | образ macOS (Apple Silicon; Mac на Intel не собирается) |
| `*.sig`, `TAnalytic-mac-*.app.tar.gz`, `latest.json` | артефакты автообновления (только при подписи, см. ниже) |
| `tinvest_analytics.py`, `SHA256SUMS` | как раньше |

## Структура `src-tauri/`

- `Cargo.toml`, `Cargo.lock` — Tauri v2 (`tray-icon`), плагины `single-instance`, `dialog`, `updater`. Проверка `/api/ping` и `POST /api/app/shutdown` идут через `std::net::TcpStream`.
- `tauri.conf.json` — окно, бандл (`resources`, NSIS, DMG, `createUpdaterArtifacts`), `plugins.updater`.
- `capabilities/default.json` — IPC только для `http://127.0.0.1:*/*`.
- `src/lib.rs` — порт, запуск Python-сервера в `setup()` (после single-instance), ожидание `/api/ping` до 60 с с кнопкой «Повторить», трей (пункты «Открыть» и «Выход»), `on_navigation` (внешние ссылки открываются в системном браузере), команды окна, выбора файла и обновления.
- `resources/backend/` — сюда CI кладёт папку PyInstaller `--onedir` (`TAnalytic-backend[.exe]` и `_internal/`); Tauri включает её в ресурсы бандла, Rust запускает `<resource_dir>/backend/TAnalytic-backend[.exe]`. Содержимое каталога не хранится в репозитории (в нём только `placeholder.txt`).
- `installer/` — картинки установщиков (`header.bmp`, `sidebar.bmp`, `dmg-background.png`; генерирует `packaging/tauri/make_installer_art.py`, нужен Pillow) и `hooks.nsh`.
- `entitlements.plist` — права hardened runtime для macOS (копия `packaging/entitlements.plist`: Python выделяет исполняемую память и грузит чужие библиотеки).

Python внутри бандла: пользователь ничего отдельно не скачивает. `--onedir` вместо `--onefile` — нет распаковки во временную папку при каждом запуске, быстрее старт, реже ложные срабатывания антивирусов, при kill не остаётся распакованного ребёнка. Загрузчик PyInstaller собирается из исходников (`PYINSTALLER_COMPILE_BOOTLOADER=1`).

## Как сервер связан с оболочкой

- Оболочка передаёт `--no-window --port <порт> --parent-pid <PID оболочки>` и переменные `TINVEST_SHELL=tauri`, `TINVEST_SHELL_REV=5`.
- Сервер раз в 2 с проверяет, жив ли процесс `--parent-pid`; если оболочку убили или она упала, сервер сам завершается. Job Object на Windows не используется: `--parent-pid` закрывает ту же проблему без `unsafe`.
- При штатном выходе оболочка шлёт `POST /api/app/shutdown`, ждёт до 3 с и только затем убивает процесс.
- Данные пользователя те же, что у прежней оболочки: `~/.tinvest_analytics` (сервер определяет папку сам, оболочка `TINVEST_HOME` не задаёт).
- Автозапуска нет ни в каком виде (ни плагина, ни ключа реестра, ни пункта в Настройках). Настройка трея в Настройках под Tauri скрыта.
- Блокировку программы целиком показывает сервер (экран PIN); оболочка биометрию не запрашивает.

## Установщик Windows

NSIS (русский язык, `currentUser`, свои картинки, ярлыки). WebView2 скачивается bootstrapper-ом, если его нет. Хук `installer/hooks.nsh` при установке находит старую установку Inno Setup по `AppId` (`HKCU\...\Uninstall\{EFBF9C3A-...}_is1`), тихо запускает её деинсталлятор (`/VERYSILENT /SUPPRESSMSGBOXES`, данные в `%USERPROFILE%\.tinvest_analytics` в тихом режиме не удаляются: вопрос о них задаётся только при `not UninstallSilent`) и удаляет значение `TAnalytic` в `HKCU\...\Run`, если оно осталось от прошлых версий (то же при удалении).

## Установщик macOS

Подпись под значком в окне образа без «.app» (`--hide-extension` бандлера) и фон с позициями значков задаются AppleScript-ом Finder: в CI бандлер его пропускает, поэтому в `release.yml` стоит `TAURI_BUNDLER_DMG_IGNORE_CI=true`. Если у пользователя в Finder включено «Показывать все расширения имён файлов», расширение видно всегда: это настройка Finder, конфигом образа её не обойти.

DMG с фоном 660x400, значок приложения слева и «Программы» справа. `minimumSystemVersion` 11.0. Без секретов Apple сборка не падает (подпись ad-hoc, при первом запуске нужно «Открыть» в меню Finder или разрешить в «Конфиденциальность и безопасность»).

## Автообновление (единственный канал)

После первой установки обновляется всё сразу (оболочка, Python-сервер, программа): `tauri-plugin-updater`, адрес `https://github.com/Kos5o4ka/tinvest-analytics/releases/latest/download/latest.json`, публичный ключ в `tauri.conf.json`. Старый канал самообновления `tinvest_analytics.py` под Tauri не работает: сервер в бандле всегда той же версии, что оболочка, а баннер оболочки pywebview не показывается (`TINVEST_SHELL=tauri`).

Схема по шагам:

1. Через 20 с после запуска и затем раз в 6 часов Rust запрашивает `latest.json`.
2. Если версия новее, подписанное обновление скачивается в фоне (подпись проверяет плагин публичным ключом).
3. Баннер в программе (`66_shell_notice.js`, опрос `tauri_update_status`) показывает «Готово обновление до версии X» и кнопку «Перезапустить» (`tauri_update_apply`: остановка сервера, установка, перезапуск).
4. Не нажали кнопку: обновление ставится при закрытии программы. Windows: NSIS в режиме `passive` в папку пользователя, без UAC; macOS: плагин заменяет `.app`.

Ключ подписи уже создан владельцем локально (`~/.tauri/tanalytic.key`, пароль пустой). Нужно один раз добавить секреты репозитория (Settings, Secrets and variables, Actions):

1. `TAURI_SIGNING_PRIVATE_KEY` — содержимое файла `~/.tauri/tanalytic.key`.
2. `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` — пустая строка (или пароль, если задавали).

Новую пару при необходимости создают так: `cargo tauri signer generate -w ~/.tauri/tanalytic.key` (или `npx @tauri-apps/cli signer generate -w ...`); публичный ключ из `.key.pub` вписывают в `plugins.updater.pubkey`, секретный остаётся только у владельца. Без секрета `TAURI_SIGNING_PRIVATE_KEY` workflow отключает артефакты обновления (`createUpdaterArtifacts: false`), печатает предупреждение, `latest.json` не создаётся, а сборка не падает.

## Подпись macOS (необязательно)

Python-сервер лежит в ресурсах бандла, а Tauri подписывает только само приложение, поэтому перед упаковкой CI подписывает все Mach-O папки `resources/backend` (`packaging/mac_codesign.sh dir`: Developer ID с hardened runtime и `entitlements.plist`, без сертификата ad-hoc). Секреты: `APPLE_CERTIFICATE` (сертификат Developer ID Application в base64 `.p12`), `APPLE_CERTIFICATE_PASSWORD`, `APPLE_ID`, `APPLE_PASSWORD` (пароль приложения), `APPLE_TEAM_ID`. `tauri-action` импортирует сертификат, Tauri подписывает бандл с правами из `entitlements.plist` и отправляет на нотаризацию.

## Переход пользователей pywebview (один раз)

`SHELL_REV_LATEST` в `src/py/13z_shell.py` равен 5; сервер Tauri сообщает ревизию 5 и `TINVEST_SHELL=tauri`, поэтому у него баннер оболочки не показывается. У оболочек pywebview (ревизия 4 и ниже) баннер предлагает установить новую версию: Windows скачивает `TAnalytic-Setup-win.exe` (теперь NSIS), сверяет сумму и запускает его (старые лаунчеры передают ключи Inno, NSIS показывает обычное окно установщика; хук удаляет старую Inno-установку и ключ автозапуска, данные не трогает), macOS заменяет `.app` содержимым `.dmg` (приложение называется так же, `TAnalytic.app`). Дальше обновляет сам Tauri.

## Локальная разработка и сборка

```bash
python3 build.py
mkdir -p src-tauri/resources/backend   # в каталоге должен быть хотя бы placeholder.txt; для cargo check этого достаточно
cd src-tauri && cargo check --target aarch64-apple-darwin
cargo tauri dev        # найдёт tinvest_analytics.py в корне и запустит python3
```

Полная сборка (`cargo tauri build --target ...`) требует собранной папки Python-сервера в `src-tauri/resources/backend/`, как в `release.yml`. Без ключа обновлений добавьте `--config '{"bundle":{"createUpdaterArtifacts":false}}'`.
