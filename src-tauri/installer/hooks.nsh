; Хуки установщика NSIS (Tauri). Файл в UTF-8; сообщения пользователю не выводятся.
;
; Миграция со старой установки на Inno Setup (pywebview-оболочка, packaging/TAnalytic.iss):
;  * находим её по AppId в HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{AppId}_is1;
;  * тихо запускаем её деинсталлятор (/VERYSILENT /SUPPRESSMSGBOXES /NORESTART). В тихом режиме он данные
;    пользователя (%USERPROFILE%\.tinvest_analytics) не удаляет: вопрос о них задаётся только при `not UninstallSilent`;
;  * убираем старый автозапуск: значение TAnalytic в HKCU\...\Run, оканчивающееся на " --tray" (его писал старый установщик).
;    Автозапуск оболочки Tauri пишет то же имя значения, но без аргументов, поэтому его не трогаем.

!macro NSIS_HOOK_PREINSTALL
  ; --- старая установка Inno Setup ---
  ReadRegStr $R0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{EFBF9C3A-E919-491B-9C8A-03A56D69E1E3}_is1" "UninstallString"
  ReadRegStr $R4 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\{EFBF9C3A-E919-491B-9C8A-03A56D69E1E3}_is1" "Inno Setup: App Path"
  ${If} $R0 != ""
    ExecWait '$R0 /VERYSILENT /SUPPRESSMSGBOXES /NORESTART' $R1
    ; деинсталлятор Inno заканчивает работу во втором процессе: ждём, пока он удалит сам себя (до 20 с)
    ${If} $R4 != ""
      StrCpy $R5 0
      ${While} $R5 < 40
        ${IfNot} ${FileExists} "$R4\unins000.exe"
          ${Break}
        ${EndIf}
        Sleep 500
        IntOp $R5 $R5 + 1
      ${EndWhile}
    ${EndIf}
  ${EndIf}

  ; --- автозапуск старой оболочки: "...\TAnalytic.exe" --tray ---
  ReadRegStr $R2 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "TAnalytic"
  ${If} $R2 != ""
    StrCpy $R3 $R2 7 -7
    ${If} $R3 == " --tray"
      DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "TAnalytic"
    ${EndIf}
  ${EndIf}
!macroend

!macro NSIS_HOOK_POSTINSTALL
!macroend

!macro NSIS_HOOK_PREUNINSTALL
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
!macroend
