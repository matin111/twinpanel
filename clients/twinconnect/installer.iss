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

; TwinConnect requires elevation on launch for the Windows VPN service.
; Avoid Inno Setup's postinstall process launch (CreateProcess 740).
; The installed Start Menu/Desktop shortcuts invoke Windows UAC normally.
; Prerequisites are installed once in ssPostInstall below.

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ExitCode: Integer;
  Ok: Boolean;
  PowershellPath: String;
  Parameters: String;
  OpenConnectInstaller: String;
  OpenConnectCli: String;
  OpenConnectScript: String;
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
    { One installer for the customer: the signed upstream OpenConnect
      package and its TAP driver are bundled, never fetched at install time.
      NSIS silent installation avoids requiring a separate download. }
    OpenConnectInstaller := ExpandConstant(
      '{app}\\prerequisites\\openconnect-gui-1.6.2-win64.exe');
    OpenConnectCli := ExpandConstant('{autopf}\\OpenConnect-GUI\\openconnect.exe');
    OpenConnectScript := ExpandConstant('{autopf}\\OpenConnect-GUI\\vpnc-script-win.js');
    { Do not reinstall shared upstream dependencies on every TwinConnect update. }
    if not FileExists(OpenConnectCli) then
    begin
      if not FileExists(OpenConnectInstaller) then
      begin
        MsgBox('Cisco/OpenConnect prerequisite missing from TwinConnect installer.',
          mbError, MB_OK);
      end
      else
      begin
        Ok := Exec(OpenConnectInstaller, '/S', '', SW_HIDE,
                   ewWaitUntilTerminated, ExitCode);
        if (not Ok) or (ExitCode <> 0) then
        begin
          MsgBox('The bundled Cisco/OpenConnect prerequisite could not be installed.' +
            #13#10 + 'Other VPN protocols remain available.', mbError, MB_OK);
        end;
      end;
    end;
    if not FileExists(OpenConnectCli) then
    begin
      MsgBox('Cisco CLI component was not installed by upstream setup.' +
        #13#10 + 'Cisco will remain disabled; other VPN protocols are unaffected.',
        mbError, MB_OK);
    end
    else if (not FileExists(OpenConnectScript)) and
      (not FileExists(ExpandConstant('{autopf}\\OpenConnect-GUI\\vpnc-script.js'))) then
    begin
      MsgBox('Cisco/OpenConnect routing script is missing.' +
        #13#10 + 'Cisco will remain disabled to prevent broken Windows routes.',
        mbError, MB_OK);
    end;
  end;
end;
