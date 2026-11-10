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
