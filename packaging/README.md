# Сборка приложений

Собирает `.github/workflows/release.yml` при публикации релиза; руками — так же, как в этом файле.

| Система | Результат | Как |
|---|---|---|
| macOS | `TAnalytic.app` (onedir), в релизе — zip | `pyinstaller packaging/tinvest.spec` |
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

## Обновление оболочки из программы

Лаунчер (оболочка) обновляет только `tinvest_analytics.py`; окно, трей и установщик живут в самой оболочке. Когда программа
видит, что ревизия оболочки старее (`SHELL_REV_LATEST` в `src/py/13z_shell.py`), а оболочка умеет самообновляться,
лаунчер сам (не браузер) скачивает `TAnalytic-Setup-win.exe` из последнего релиза, сверяет SHA256 с `SHA256SUMS`, показывает
«Обновить и перезапустить» и по согласию запускает `/SILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /RELAUNCH=1`.
Скачанное самой программой не получает метку «из интернета», поэтому SmartScreen при этом не срабатывает.
Разрешены только адреса GitHub (`check_url`). Оболочки старше ревизии 4 этого не умеют: им в баннере показывается ссылка на установщик.

При смене ревизии оболочки поднимайте номер в двух местах: `SHELL_REV` в `tinvest.py` и `SHELL_REV_LATEST` в `src/py/13z_shell.py`.

## Подпись и репутация (настраивается отдельно, здесь не включено)

1. **SignPath Foundation** — бесплатная подпись для открытого кода. После одобрения заявки в `release.yml` между сборкой установщика
   и загрузкой артефакта добавляется шаг `signpath/github-action-submit-signing-request`; подписывать нужно `TAnalytic-Setup-win.exe`
   (и, до упаковки, `TAnalytic.exe`).
2. **Microsoft Security Intelligence** — после каждого релиза отправлять установщик на странице «Submit a file for malware analysis»
   (тип «Software developer»): снимает ложные срабатывания Defender и копит репутацию файла.
3. Платный сертификат OV/EV — репутация SmartScreen копится на сертификат и не сбрасывается между релизами.
