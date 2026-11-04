; ---------------------------------------------------------------------------
; REDIS — установщик только для текущего пользователя (per-user).
; Версия передаётся сборочным скриптом: ISCC /DMyAppVersion=<версия>
; ---------------------------------------------------------------------------

#ifndef MyAppVersion
  #define MyAppVersion "1.2.8"
#endif

#define MyAppName "REDIS"
#define MyAppPublisher "DippyDingo"
#define MyAppURL "https://github.com/DippyDingo/active-tracker"
#define MyAppExeName "REDIS.exe"
; Должно совпадать с мьютексом, который создаёт приложение
; (app/win32_utils.py: acquire_instance_mutex). По нему Inno понимает,
; что приложение запущено, и просит его закрыть.
; Имя намеренно оставлено прежним: установленные версии 1.4.x держат именно
; этот мьютекс, иначе тихое обновление упадёт по «приложение запущено».
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
OutputBaseFilename=REDIS-Setup-{#MyAppVersion}
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
; --onedir: основной exe + вся папка _internal с библиотеками. Установка
; «папкой», а не одним файлом — и запуск без распаковки в temp (нет белого
; окна на старте), и в каталоге программы лежат все файлы приложения.
Source: "..\dist\REDIS\REDIS.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\REDISUpdater.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\REDIS\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Автозапуск: тот же формат, что пишет приложение (значение "Nodexy",
; "<путь>" --minimized). Имя значения намеренно оставлено прежним: приложение
; (app/win32_utils.py) читает и перезаписывает именно его, поэтому смена имени
; привела бы к дублю записей и «потерянному» автозапуску. uninsdeletevalue
; убирает запись при удалении.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Nodexy"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; а) Ручная установка: галочка «Запустить REDIS» на последней странице.
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent
; б) Тихое обновление: помощник запускает установщик с /RESTARTAPP, и эта
; запись перезапускает приложение. В тихом режиме записи с postinstall не
; выполняются, поэтому запись отдельная.
Filename: "{app}\{#MyAppExeName}"; Flags: nowait skipifdoesntexist; Check: RestartAfterSilentUpdate
; в) Переход с версий 1.4.1 и ниже: их помощник после установки ищет
; Nodexy.exe, которого больше нет, и приложение не перезапустил бы никто.
; Запускаем новое имя сами — только если установку вёл старый помощник.
Filename: "{app}\{#MyAppExeName}"; Flags: nowait skipifdoesntexist; Check: RestartAfterLegacyUpdate

[UninstallDelete]
; Резервные копии апдейтера и остатки старых сборок.
Type: files; Name: "{app}\*.old"
Type: filesandordirs; Name: "{app}\_internal"

; При установке поверх старой версии _internal очищается ДО копирования:
; иначе файлы, удалённые в новой версии, остались бы и раздували каталог.
[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
; Переименование Nodexy → REDIS: старые файлы удаляются, иначе в папке
; остаются два exe и два помощника обновления.
Type: files; Name: "{app}\Nodexy.exe"
Type: files; Name: "{app}\NodexyUpdater.exe"
; Ярлыки прежнего имени указывали бы на удалённый Nodexy.exe.
Type: files; Name: "{autoprograms}\Nodexy.lnk"
Type: files; Name: "{autodesktop}\Nodexy.lnk"

[Code]
var
  AskRemoveData: boolean;
  { Обновление шло поверх версии, где приложение называлось Nodexy.exe.
    Такой апдейтер после установки ищет прежнее имя и новое не запустит —
    перезапуск берёт на себя установщик. }
  LegacySilentUpdate: boolean;

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

{ Переход с 1.4.1 и ниже: старый помощник обновления ждёт Nodexy.exe, который
  этот установщик удаляет. Приложение не поднял бы никто — запускаем сами.
  Для сборок 1.4.2+ (папка уже без Nodexy.exe) условие не срабатывает, и
  двойного запуска не бывает. }
function RestartAfterLegacyUpdate: boolean;
begin
  Result := LegacySilentUpdate and (not CmdLineParamExists('/RESTARTAPP'));
end;

{ Переход с 1.4.1 и ниже: там приложение называлось Nodexy.exe, и старый
  помощник обновления после установки ищет именно это имя. Файл к моменту
  проверки ещё на месте (InstallDelete выполняется позже), поэтому факт
  «обновляемся поверх Nodexy» определяется надёжно. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  LegacySilentUpdate := FileExists(ExpandConstant('{app}\Nodexy.exe'));
  Result := '';
end;

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
      MsgBox('REDIS устанавливается только для текущего пользователя, и папка должна быть доступна на запись — иначе программа не сможет обновляться автоматически.' #13#10#13#10
        + 'Выберите другую папку, например: D:\REDIS', mbError, MB_OK);
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
      'Software\Microsoft\Windows\CurrentVersion\Run', 'Nodexy');
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
