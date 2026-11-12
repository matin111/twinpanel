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
  OpenConnectManifest: String;
  OpenVpnInstaller: String;
  OpenVpnBinary: String;
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
    { The signed vendor setup has an OPTIONAL CLI component which /S omits.
      CI extracts and checks the CLI and Windows route script into our app
      bundle, independent of the vendor's GUI installer defaults. }
    OpenConnectManifest := ExpandConstant(
      '{app}\engines\openconnect\OPENCONNECT-ENGINE-MANIFEST.txt');
    if not FileExists(OpenConnectManifest) then
    begin
      MsgBox('Cisco engine bundle missing; Cisco remains disabled.',
        mbError, MB_OK);
    end;
    { Install official vendor-signed OpenVPN Community x64 package only if
      its CLI is absent. The MSI was verified in Windows CI and is bundled.
      Inno Setup is already elevated: users need no separate installation. }
    OpenVpnBinary := ExpandConstant('{pf}\OpenVPN\bin\openvpn.exe');
    OpenVpnInstaller := ExpandConstant(
      '{app}\prerequisites\OpenVPN-2.7.9-I001-amd64.msi');
    if not FileExists(OpenVpnBinary) then
    begin
      if FileExists(OpenVpnInstaller) then
      begin
        Ok := Exec(ExpandConstant('{sys}\msiexec.exe'),
                   '/i "' + OpenVpnInstaller + '" /qn /norestart',
                   '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
        if (not Ok) or ((ExitCode <> 0) and (ExitCode <> 3010)) then
          MsgBox('OpenVPN engine installation failed; OpenVPN will remain disabled.' +
                 #13#10 + 'Other VPN connections are unaffected.',
                 mbError, MB_OK);
      end
      else
        MsgBox('OpenVPN signed vendor prerequisite is missing from Setup.',
               mbError, MB_OK);
    end;
    { Vendor GUI setup may still supply adapter/driver prerequisites.
      Its success is NOT proof that Cisco tunnel routing is functional. }
    if FileExists(OpenConnectInstaller) then
    begin
      Ok := Exec(OpenConnectInstaller, '/S', '', SW_HIDE,
                 ewWaitUntilTerminated, ExitCode);
      if (not Ok) or (ExitCode <> 0) then
        MsgBox('Cisco vendor prerequisites could not be installed.' + #13#10 +
          'Other VPN protocols remain available.', mbError, MB_OK);
    end;
  end;
end;
