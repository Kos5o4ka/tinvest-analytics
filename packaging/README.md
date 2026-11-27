# Сборка приложений

Собирает `.github/workflows/release.yml` при публикации релиза; руками — так же, как в этом файле.

| Система | Результат | Как |
|---|---|---|
| macOS | `TAnalytic.app` (onedir) → образ `TAnalytic-mac-arm64.dmg` / `TAnalytic-mac-x64.dmg` | PyInstaller, затем `packaging/make_dmg.sh` |
| Windows | папка `TAnalytic\` (onedir) → установщик `TAnalytic-Setup-win.exe` | PyInstaller, затем Inno Setup (`packaging/TAnalytic.iss`) |

## Установщик Windows

* ставится в `%LOCALAPPDATA%\Programs\TAnalytic` без прав администратора, ярлык в меню «Пуск» и по желанию на рабочем столе;
* перед копированием проверяет Microsoft Edge WebView2 Runtime и при его отсутствии докачивает официальный установщик Microsoft;
* `AppMutex=TAnalyticSingleInstanceMutex` — это имя создаёт лаунчер (`SingleInstance` в `tinvest.py`); `CloseApplications` закрывает запущенную программу;
* при удалении спрашивает, стирать ли данные (`%USERPROFILE%\.tinvest_analytics`); по умолчанию — «Нет»;
* опция «Запускать вместе с Windows» пишет в `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` значение `TAnalytic` с командой `"...\TAnalytic.exe" --tray`;
  ту же запись ведёт переключатель в «Настройках» (`src/py/13z_shell.py`);
* версия берётся из переменной окружения `APP_VER` (в CI — тег без буквы `v`);
* файл `TAnalytic.iss` хранится в UTF-8 с BOM.

Ручная сборка на Windows: `pip install pyinstaller certifi pillow pywebview pythonnet`, затем
`python packaging/make_icon.py build_icons`, `pyinstaller --noconfirm --distpath build_out/dist --workpath build_out/work packaging/tinvest.spec`,
`set APP_VER=0.31` и `"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\TAnalytic.iss`.

## Образ macOS

`packaging/make_dmg.sh <TAnalytic.app> <выход.dmg>` собирает образ только системными `hdiutil`, `ditto` и `osascript`: внутри
`TAnalytic.app` и ярлык `Applications` (перетащить для установки), фон со стрелкой (`make_dmg_bg.py`, нужен Pillow) и раскладка
иконок через Finder. Если Finder недоступен (нет графического сеанса, нет прав на автоматизацию) или не ответил за минуту,
скрипт предупреждает и собирает образ без раскладки; `DMG_NO_LAYOUT=1` отключает её явно. Сборки раздельные, по архитектуре раннера:
`macos-latest` — arm64, `macos-15-intel` — x86_64 (universal2 не нужен: зависимости собираются под архитектуру раннера).
Раннеры GitHub с Finder работают, но если раскладка начнёт давать сбой, это не ломает релиз.
Ручная сборка: `pyinstaller ... packaging/tinvest.spec`, затем `packaging/make_dmg.sh build_out/dist/TAnalytic.app TAnalytic-mac-arm64.dmg`.
Прежние zip с `.app` не публикуются: на них ничего не ссылалось (адрес берётся из `shell_status` в `src/py/13z_shell.py`).

## Подпись и нотаризация macOS

Необязательны: `packaging/mac_codesign.sh` вызывается из `release.yml` всегда и сам решает по секретам репозитория
(Settings → Secrets and variables → Actions):

| Секрет | Что это |
|---|---|
| `APPLE_DEVELOPER_ID_CERT` | сертификат «Developer ID Application» вместе с закрытым ключом, файл `.p12` в base64: `base64 -i cert.p12 \| pbcopy` |
| `APPLE_CERT_PASSWORD` | пароль, заданный при экспорте `.p12` |
| `APPLE_ID` | Apple ID владельца аккаунта разработчика |
| `APPLE_TEAM_ID` | Team ID (10 символов): developer.apple.com → Membership details |
| `APPLE_APP_PASSWORD` | пароль для приложений: account.apple.com → Вход и безопасность → Пароли для приложений |

Как получить: вступить в Apple Developer Program (платно, 99 USD в год); в Xcode (Settings → Accounts → Manage Certificates)
или на developer.apple.com → Certificates создать **Developer ID Application**; в «Связке ключей» найти сертификат вместе с ключом,
выбрать «Экспортировать» в `.p12` с паролем; закодировать в base64 и занести секреты.

Что делает сборка: с `APPLE_DEVELOPER_ID_CERT` и `APPLE_CERT_PASSWORD` — подпись всех вложенных файлов, затем `TAnalytic.app` с
`--options runtime` (hardened runtime) и `packaging/entitlements.plist`, подпись `.dmg`; ещё и с `APPLE_ID`, `APPLE_TEAM_ID`,
`APPLE_APP_PASSWORD` — `xcrun notarytool submit --wait` и `stapler staple` для образа. Любого секрета нет — ad-hoc подпись
(`codesign -s -`, без неё arm64 не запускается), нотаризация пропускается, шаги не падают. Если нотаризацию Apple отклонила, сборка падает.
Права в `entitlements.plist`: `allow-unsigned-executable-memory` (ctypes и libffi у Python и pyobjc) и `disable-library-validation`
(библиотеки из pip-колёс подписаны чужими сертификатами). Права на сеть и WKWebView не нужны: они относятся к App Sandbox, а приложение
в песочнице не работает.

Без подписи и нотаризации пользователь видит «не удаётся проверить, что приложение не содержит вредоносного ПО» (macOS 15 и новее —
«Apple не удалось проверить…»). Открыть: правый клик по приложению → «Открыть» → «Открыть»; либо «Системные настройки →
Конфиденциальность и безопасность» → внизу «Всё равно открыть»; либо в Терминале `xattr -dr com.apple.quarantine /Applications/TAnalytic.app`.
Приложение, обновлённое самой программой, карантинной метки не получает (см. ниже), поэтому предупреждение появляется только при первой установке.

## Обновление оболочки из программы

Лаунчер (оболочка) обновляет только `tinvest_analytics.py`; окно, трей и установщик живут в самой оболочке. Когда программа
видит, что ревизия оболочки старее (`SHELL_REV_LATEST` в `src/py/13z_shell.py`), а оболочка умеет самообновляться,
лаунчер сам (не браузер) скачивает `TAnalytic-Setup-win.exe` из последнего релиза, сверяет SHA256 с `SHA256SUMS`, показывает
«Обновить и перезапустить» и по согласию запускает `/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /RELAUNCH=1`.
Скачанное самой программой не получает метку «из интернета», поэтому SmartScreen при этом не срабатывает.
Разрешены только адреса GitHub (`check_url`). Оболочки старше ревизии 4 этого не умеют: им в баннере показывается ссылка на установщик.

**macOS.** Так же скачивается `TAnalytic-mac-<arm64|x64>.dmg` (архитектура — по `platform.machine()`) и сверяется с `SHA256SUMS`. По
«Обновить и перезапустить» (`install_mac_and_exit` в `tinvest.py`): образ монтируется `hdiutil attach -nobrowse -readonly`, приложение
копируется `ditto` во временную папку рядом с текущим `.app` (путь — по `sys.executable`), с копии снимается `com.apple.quarantine`,
`codesign --verify` проверяет целостность, затем два переименования (прежнее в `.old`, новое на место). Любая ошибка — прежнее
приложение остаётся на месте. После этого отдельный короткий `sh`-процесс ждёт выхода программы (`graceful_exit`), делает
`open -n` и стирает `.old`. Если приложение запущено из образа диска, из App Translocation (`/private/var/folders/...`) или из
незаписываемой папки, ничего не трогается, а баннер показывает ссылку на скачивание. Ревизию оболочки не поднимали: сборка
macOS с образом уже умеет обновляться, а у сборок из zip самообновления не было.

При смене ревизии оболочки поднимайте номер в двух местах: `SHELL_REV` в `tinvest.py` и `SHELL_REV_LATEST` в `src/py/13z_shell.py`.

## Подпись и репутация (настраивается отдельно, здесь не включено)

1. **SignPath Foundation** — бесплатная подпись для открытого кода. После одобрения заявки в `release.yml` между сборкой установщика
   и загрузкой артефакта добавляется шаг `signpath/github-action-submit-signing-request`; подписывать нужно `TAnalytic-Setup-win.exe`
   (и, до упаковки, `TAnalytic.exe`).
2. **Microsoft Security Intelligence** — после каждого релиза отправлять установщик на странице «Submit a file for malware analysis»
   (тип «Software developer»): снимает ложные срабатывания Defender и копит репутацию файла.
3. Платный сертификат OV/EV — репутация SmartScreen копится на сертификат и не сбрасывается между релизами.
