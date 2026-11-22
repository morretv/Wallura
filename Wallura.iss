; Inno-Setup-Skript für Wallura. Gebaut wird es über build_installer.bat.

#ifndef AppVer
  #define AppVer "1.1.0"
#endif

[Setup]
AppName=Wallura
AppVersion={#AppVer}
AppPublisher=MorreTv
AppCopyright=Copyright (C) 2026 MorreTv. MIT-Lizenz.
VersionInfoCompany=MorreTv
VersionInfoCopyright=Copyright (C) 2026 MorreTv. MIT-Lizenz.
DefaultDirName={autopf}\Wallura
DefaultGroupName=Wallura
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=Wallura-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=wallura.ico
UninstallDisplayIcon={app}\Wallura.exe
ArchitecturesInstallIn64BitMode=x64compatible

#if FileExists(CompilerPath + "Languages\German.isl")
[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"
Name: "autostart"; Description: "Wallura mit Windows starten"
Name: "ffmpeg"; Description: "Optional: ffmpeg installieren (bessere Qualität beim Herunterladen, ca. 100 MB)"; Flags: unchecked

[Files]
Source: "dist\Wallura\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Wallura"; Filename: "{app}\Wallura.exe"
Name: "{autodesktop}\Wallura"; Filename: "{app}\Wallura.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Wallura"; ValueData: """{app}\Wallura.exe"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""winget install -e --id Gyan.FFmpeg --silent --accept-source-agreements --accept-package-agreements"""; StatusMsg: "Installiere ffmpeg ..."; Flags: runhidden waituntilterminated; Tasks: ffmpeg
Filename: "{app}\Wallura.exe"; Description: "Wallura jetzt starten"; Flags: nowait postinstall skipifsilent
; Stilles Update aus der App heraus: danach automatisch wieder starten
Filename: "{app}\Wallura.exe"; Parameters: "--minimized"; Flags: nowait; Check: WizardSilent

[Code]
procedure KillApp();
var
  R: Integer;
begin
  Exec('taskkill.exe', '/F /IM Wallura.exe', '', SW_HIDE, ewWaitUntilTerminated, R);
  Exec('taskkill.exe', '/F /IM LiveWall.exe', '', SW_HIDE, ewWaitUntilTerminated, R);
end;

function InitializeSetup(): Boolean;
begin
  KillApp();
  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  KillApp();
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if not UninstallSilent then
      if MsgBox('Auch Einstellungen, Downloads und Vorschaubilder löschen?', mbConfirmation, MB_YESNO) = IDYES then
        DelTree(ExpandConstant('{userappdata}\Wallura'), True, True, True);
end;

{ Alte Installation „LiveWall“ still entfernen (Einstellungen und Downloads bleiben, Wallura übernimmt sie). }
procedure CurStepChanged(CurStep: TSetupStep);
var
  S: String;
  R: Integer;
begin
  if CurStep = ssPostInstall then
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\LiveWall_is1', 'UninstallString', S) then
      Exec(RemoveQuotes(S), '/SILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, R);
end;
