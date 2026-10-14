; ---------------------------------------------------------------------------
; Nodexy — установщик только для текущего пользователя (per-user).
; Версия передаётся сборочным скриптом: ISCC /DMyAppVersion=<версия>
; ---------------------------------------------------------------------------

#ifndef MyAppVersion
  #define MyAppVersion "1.2.8"
#endif

#define MyAppName "Nodexy"
#define MyAppPublisher "DippyDingo"
#define MyAppURL "https://github.com/DippyDingo/active-tracker"
#define MyAppExeName "Nodexy.exe"
; Должно совпадать с мьютексом, который создаёт приложение
; (app/win32_utils.py: acquire_instance_mutex). По нему Inno понимает,
; что приложение запущено, и просит его закрыть.
#define MyAppMutex "NodexySingleInstanceMutex"

[Setup]
; AppId — фиксированный GUID. НИКОГДА не менять: он связывает обновления
; и запись в «Приложения и компоненты».
AppId={{4B8E2F7A-9C3D-4A61-B5E8-6F1D0C9A7E42}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
; Per-user: {autopf} при PrivilegesRequired=lowest раскрывается в
; %LOCALAPPDATA%\Programs. Каталог всегда доступен пользователю на запись —
; это обязательное условие работы автообновления.
DefaultDirName={autopf}\{#MyAppName}
; Страница выбора каталога показывается всегда (путь может быть любым,
; кроме Program Files и Windows — защита в [Code]).
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
; PrivilegesRequiredOverridesAllowed НАМЕРЕННО не задан: опции
; «установить для всех пользователей» быть не должно.
OutputDir=..\dist-installer
OutputBaseFilename=Nodexy-Setup-{#MyAppVersion}
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no
MinVersion=10.0
; Примечание: в Inno Setup 6.0–6.2 вместо x64compatible нужно писать x64.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Если приложение запущено — мастер попросит его закрыть (в тихом режиме
; установка прервётся; помощник обновления запускает установщик только
; после полного выхода приложения).
AppMutex={#MyAppMutex}
CloseApplications=yes
; Inno сам не перезапускает приложение — это делает запись [Run]
; с Check: RestartAfterSilentUpdate (параметр /RESTARTAPP).
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
; unchecked — по умолчанию не отмечены; выбор пользователя наследуется при апгрейде.
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"; Flags: unchecked
Name: "autostart"; Description: "Запускать при входе в Windows"; GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Автозапуск: тот же формат, что пишет приложение (значение "Nodexy",
; "<путь>" --minimized). uninsdeletevalue убирает запись при удалении.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; а) Ручная установка: галочка «Запустить Nodexy» на последней странице.
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent
; б) Тихое обновление (стратегия B): помощник запускает установщик с
; /RESTARTAPP, и эта запись перезапускает приложение. В тихом режиме
; записи с postinstall не выполняются, поэтому запись отдельная.
Filename: "{app}\{#MyAppExeName}"; Flags: nowait skipifdoesntexist; Check: RestartAfterSilentUpdate

[UninstallDelete]
; Резервные копии апдейтера и задел на возможный переход на onedir.
Type: files; Name: "{app}\*.old"
Type: filesandordirs; Name: "{app}\_internal"

[Code]
var
  AskRemoveData: boolean;

{ Есть ли параметр командной строки установщика (без учёта регистра). }
function CmdLineParamExists(const param: string): boolean;
var
  i: integer;
begin
  Result := False;
  for i := 1 to ParamCount do
    if CompareText(ParamStr(i), param) = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

{ Тихое обновление просит перезапустить приложение (/RESTARTAPP). }
function RestartAfterSilentUpdate: boolean;
begin
  Result := CmdLineParamExists('/RESTARTAPP');
end;

{ Защита выбора каталога: только переносимые на запись пользователю папки. }
function NextButtonClick(CurPageID: integer): boolean;
var
  dir: string;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    dir := WizardDirValue;
    if (Pos(ExpandConstant('{commonpf}'), dir) = 1)
      or (Pos(ExpandConstant('{commonpf32}'), dir) = 1)
      or (Pos(ExpandConstant('{win}'), dir) = 1) then
    begin
      MsgBox('Nodexy устанавливается только для текущего пользователя, и папка должна быть доступна на запись — иначе программа не сможет обновляться автоматически.' #13#10#13#10
        + 'Выберите другую папку, например: D:\Nodexy', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  { Если задача «автозапуск» не выбрана, в реестре не должно остаться
    значения, указывающего на фактический путь установки. }
  if (CurStep = ssPostInstall) and (not WizardIsTaskSelected('autostart')) then
    RegDeleteValue(HKEY_CURRENT_USER,
      'Software\Microsoft\Windows\CurrentVersion\Run', '{#MyAppName}');
end;

function InitializeUninstall: boolean;
var
  dataDir: string;
begin
  Result := True;
  AskRemoveData := False;
  { Тихая деинсталляция (в т.ч. обновление/удаление скриптами) НИКОГДА не
    удаляет данные: вопрос задаётся только живому пользователю. }
  if UninstallSilent then
    Exit;
  dataDir := ExpandConstant('{userappdata}\ActiveTracker');
  { Данные удаляются только по явному согласию; по умолчанию — НЕТ. }
  if DirExists(dataDir) then
    AskRemoveData := MsgBox(
      'Удалить также статистику и настройки?' #13#10#13#10
        + 'Будет удалена папка:' #13#10 + dataDir,
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and AskRemoveData then
    DelTree(ExpandConstant('{userappdata}\ActiveTracker'), True, True, True);
end;
