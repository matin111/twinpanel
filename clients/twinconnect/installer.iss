#define MyAppName "TwinConnect"
#define MyAppVersion "0.1.0-preview"
#define MyAppExeName "twinconnect.exe"

[Setup]
AppId={{D662C7C4-9DB8-4F2B-9320-8CF0AF73D613}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=TwinConnect
DefaultDirName={autopf}\TwinConnect
DefaultGroupName=TwinConnect
OutputDir=.
OutputBaseFilename=TwinConnect-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableProgramGroupPage=yes

[Files]
Source: "build\windows\x64\runner\Release\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "tools\install_prerequisites.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\TwinConnect"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\TwinConnect"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\tools\install_prerequisites.ps1"""; StatusMsg: "Installing verified VPN prerequisite (WireGuard)..."; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Launch TwinConnect"; Flags: postinstall nowait skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ExitCode: Integer;
  Ok: Boolean;
  PowershellPath: String;
  Parameters: String;
begin
  if CurStep = ssPostInstall then
  begin
    PowershellPath := ExpandConstant('{sys}\\WindowsPowerShell\\v1.0\\powershell.exe');
    Parameters := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
      ExpandConstant('{app}\\tools\\install_prerequisites.ps1') + '"';
    Ok := Exec(PowershellPath, Parameters, '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
    if (not Ok) or (ExitCode <> 0) then
    begin
      MsgBox('WireGuard prerequisite was not installed successfully.' + #13#10 +
        'TwinConnect was installed, but native VPN connections may not work.' + #13#10 +
        'See: C:\\ProgramData\\TwinConnect\\install-prerequisites.log',
        mbError, MB_OK);
    end;
  end;
end;
