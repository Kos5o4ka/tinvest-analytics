; Установщик TAnalytic для Windows (Inno Setup 6.3+).
; Сборка (из корня репозитория, после PyInstaller и packaging/make_icon.py build_icons):
;   set APP_VER=0.31 & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\TAnalytic.iss
; Результат: build_out\TAnalytic-Setup-win.exe. Файл должен храниться в UTF-8 с BOM — иначе русский текст исказится.
; Установка идёт в %LOCALAPPDATA%\Programs\TAnalytic без прав администратора. Данные пользователя лежат отдельно
; (%USERPROFILE%\.tinvest_analytics) и при обновлении не трогаются.

#define MyAppName "TAnalytic"
#define MyAppExe  "TAnalytic.exe"
#define MyAppVer  GetEnv("APP_VER")
#if MyAppVer == ""
  #define MyAppVer "0.0"
#endif

[Setup]
; Идентификатор приложения: не менять, иначе обновление поставит вторую копию рядом
AppId={{EFBF9C3A-E919-491B-9C8A-03A56D69E1E3}
AppName={#MyAppName}
AppVersion={#MyAppVer}
AppPublisher=TAnalytic
AppPublisherURL=https://github.com/Kos5o4ka/tinvest-analytics
AppSupportURL=https://github.com/Kos5o4ka/tinvest-analytics/issues
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\build_out
OutputBaseFilename=TAnalytic-Setup-win
SetupIconFile=..\build_icons\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Имя мьютекса создаёт лаунчер (tinvest.py, SingleInstance): установщик не заменит файлы запущенной программы
AppMutex=TAnalyticSingleInstanceMutex
CloseApplications=yes
RestartApplications=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Files]
Source: "..\build_out\dist\TAnalytic\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[InstallDelete]
; onedir: при обновлении убираем прежнюю папку библиотек, чтобы в ней не копились лишние файлы старых версий
Type: filesandordirs; Name: "{app}\_internal"

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent
; Тихое обновление из программы (/SILENT /RELAUNCH=1): старая копия уже закрылась сама, поэтому /RESTARTAPPLICATIONS
; её не вернёт — запускаем обновлённую программу здесь
Filename: "{app}\{#MyAppExe}"; Flags: nowait; Check: RelaunchAfterUpdate

[Code]
var
  DownloadPage: TDownloadWizardPage;
  WebView2File: String;

function RelaunchAfterUpdate(): Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RELAUNCH|0}') = '1');
end;

// Microsoft Edge WebView2 Runtime: на свежей Windows 10/11 уже есть, на старой Windows 10 может отсутствовать
function WebView2Installed(): Boolean;
var
  v: String;
begin
  Result := False;
  if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v) then
    Result := (v <> '') and (v <> '0.0.0.0');
  if (not Result) and RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v) then
    Result := (v <> '') and (v <> '0.0.0.0');
end;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

procedure InitializeWizard();
begin
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), SetupMessage(msgPreparingDesc), @OnDownloadProgress);
end;

// Перед копированием файлов: если WebView2 нет, скачиваем официальный установщик Microsoft.
// Не получилось — установка продолжается: программа откроется в запасном окне или в браузере.
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and (not WebView2Installed()) then
  begin
    DownloadPage.Clear;
    DownloadPage.Add('https://go.microsoft.com/fwlink/p/?LinkId=2124703', 'MicrosoftEdgeWebview2Setup.exe', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
        WebView2File := ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe');
      except
        WebView2File := '';
        if not DownloadPage.AbortedByUser then
          SuppressibleMsgBox('Не удалось скачать Microsoft Edge WebView2 Runtime, он нужен для окна программы.'#13#10 +
            'Установка продолжится. Если окно не откроется, установите WebView2 с сайта Microsoft: ' +
            'developer.microsoft.com/microsoft-edge/webview2', mbInformation, MB_OK, IDOK);
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  code: Integer;
begin
  if (CurStep = ssPostInstall) and (WebView2File <> '') then
    Exec(WebView2File, '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, code);
end;

// При удалении спрашиваем, стирать ли данные (по умолчанию — «Нет», чтобы при переустановке ничего не потерялось)
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  dataDir: String;
begin
  if CurUninstallStep = usUninstall then
    // автозапуска в программе больше нет: убираем значение, оставшееся от прошлых версий
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#MyAppName}');
  if CurUninstallStep = usPostUninstall then
  begin
    dataDir := ExpandConstant('{%USERPROFILE}\.tinvest_analytics');
    if DirExists(dataDir) and (not UninstallSilent) then
    begin
      if MsgBox('Удалить сохранённые данные: портфель, базу, кэш и настройки (' + dataDir + ')?'#13#10 +
                'Если вы собираетесь установить программу снова, нажмите «Нет».',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(dataDir, True, True, True);
    end;
  end;
end;
