#define MyAppName "TwinConnect"
#define MyAppVersion "0.1.0-preview"
#define MyAppExeName "twinconnect.exe"

; Release gate: verified signed system guard is not ready.
; Only certified builds may define IncludeVerifiedGlobalGuard from the
; compiler command line AFTER service integration and leak/recovery tests.
#ifndef IncludeVerifiedGlobalGuard
  #define IncludeVerifiedGlobalGuard 0
#endif
#if IncludeVerifiedGlobalGuard
  #ifndef GuardSigningThumbprint
    #error "Verified Kill Switch setup requires a pinned service signing thumbprint."
  #endif
#endif

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
Source: "tools\reset_windows_network.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "tools\restore_windows_network_launcher.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "tools\windows_guard_control.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "tools\windows_app_network_lock.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "tools\windows_system_proxy.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "tools\check_windows_real_device_readonly.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
#if IncludeVerifiedGlobalGuard
Source: "build\windows\x64\runner\Release\services\TwinConnectGlobalGuard.exe"; DestDir: "{app}\services"; Flags: ignoreversion
Source: "tools\install_guard_service.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
#endif

[Icons]
Name: "{autoprograms}\TwinConnect"; Filename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\TwinConnect - Restore Internet"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\restore_windows_network_launcher.ps1"""
Name: "{autoprograms}\TwinConnect - Restore System Proxy"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\windows_system_proxy.ps1"" -Action Disable"
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
  AmneziaWgInstaller: String;
  AmneziaWgBinary: String;
#if IncludeVerifiedGlobalGuard
  GuardInstallerArgs: String;
#endif
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
          MsgBox('OpenVPN engine installation failed; OpenVPN will remain disabled.' + #13#10 +
                 'Other VPN connections are unaffected.',
                 mbError, MB_OK);
      end
      else
        MsgBox('OpenVPN signed vendor prerequisite is missing from Setup.',
               mbError, MB_OK);
    end;
    { AmneziaWG has its own Windows driver and service. Do not substitute
      ordinary WireGuard for the native v1 obfuscated AWG profile.
      The official upstream MSI is bundled and SHA256-verified by CI.
      Install only when its official executable is absent. }
    AmneziaWgBinary := ExpandConstant('{pf}\\AmneziaWG\\amneziawg.exe');
    AmneziaWgInstaller := ExpandConstant(
      '{app}\\prerequisites\\amneziawg-amd64-3.1.0.msi');
    if not FileExists(AmneziaWgBinary) then
    begin
      if FileExists(AmneziaWgInstaller) then
      begin
        Ok := Exec(ExpandConstant('{sys}\\msiexec.exe'),
                   '/i "' + AmneziaWgInstaller + '" /qn /norestart',
                   '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
        if (not Ok) or ((ExitCode <> 0) and (ExitCode <> 3010)) then
          MsgBox('Official AmneziaWG driver prerequisite could not be installed.' + #13#10 +
                 'All other VPN protocols remain available.', mbError, MB_OK);
      end
      else
        MsgBox('AmneziaWG Windows prerequisite is missing from Setup.' + #13#10 +
               'Other VPN protocols are unaffected.', mbError, MB_OK);
    end;
#if IncludeVerifiedGlobalGuard
    { Install and start a VERIFIED, signed service automatically at setup
      time, while leaving the blocking policy OFF until user opt-in.
      Do not allow a missing/invalid guard binary to silently pass. }
    GuardInstallerArgs := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
      ExpandConstant('{app}\tools\install_guard_service.ps1') + '" -Action Install -BinaryPath "' +
      ExpandConstant('{app}\services\TwinConnectGlobalGuard.exe') + '" -ExpectedSignerThumbprint "{#GuardSigningThumbprint}"';
    Ok := Exec(PowershellPath, GuardInstallerArgs, '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
    if (not Ok) or (ExitCode <> 0) then
    begin
      MsgBox('Kill Switch service could not be verified and installed. Setup cannot continue.',
        mbCriticalError, MB_OK);
      Abort;
    end;
#endif
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

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ExitCode: Integer;
  Ok: Boolean;
  AppGuard: String;
#if IncludeVerifiedGlobalGuard
  Args: String;
#endif
begin
  if CurUninstallStep = usUninstall then
  begin
    { Persistent per-app WFP filters must never survive removal of their
      recovery executable. Recovery is limited to our own fixed filter GUIDs. }
    AppGuard := ExpandConstant('{app}\services\TwinConnectAppKillSwitch.exe');
    if FileExists(AppGuard) then
    begin
      Ok := Exec(AppGuard, 'recover', '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
      if (not Ok) or (ExitCode <> 0) then
      begin
        MsgBox('Selected-app Kill Switch recovery failed. Uninstall stopped to prevent an orphan firewall rule.',
          mbCriticalError, MB_OK);
        Abort;
      end;
    end;
#if IncludeVerifiedGlobalGuard
    Args := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
      ExpandConstant('{app}\tools\install_guard_service.ps1') +
      '" -Action Uninstall -BinaryPath "' +
      ExpandConstant('{app}\services\TwinConnectGlobalGuard.exe') + '" -ExpectedSignerThumbprint "{#GuardSigningThumbprint}"';
    Ok := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      Args, '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
    if (not Ok) or (ExitCode <> 0) then
    begin
      MsgBox('Kill Switch recovery failed. Uninstall has been stopped to prevent a network lockout.',
        mbCriticalError, MB_OK);
      Abort;
    end;
#endif
  end;
end;
