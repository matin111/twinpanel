#define AppName "TwinConnect Guard Diagnostic"
#define ServiceExe "TwinConnectGuardDiagnostic.exe"
[Setup]
AppId={{C66E76E5-F84A-485D-9795-7B584DAAC7E7}
AppName={#AppName}
AppVersion=0.1.0-diagnostic
AppPublisher=TwinConnect
DefaultDirName={autopf}\TwinConnectGuardDiagnostic
OutputBaseFilename=TwinConnect-Guard-Diagnostic-Setup
OutputDir=.
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
DisableProgramGroupPage=yes
Uninstallable=yes

[Files]
Source: "build\guard-diagnostic\{#ServiceExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "tools\install_guard_diagnostic.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Code]
function RunServiceAction(Action: String): Boolean;
var
  Cmd: String;
  Code: Integer;
begin
  Cmd := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{app}\install_guard_diagnostic.ps1') + '" -Action ' +
    Action + ' -BinaryPath "' + ExpandConstant('{app}\{#ServiceExe}') + '"';
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    Cmd, '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    if not RunServiceAction('Install') then
    begin
      MsgBox('Diagnostic Windows service installation failed. No Kill Switch was activated.',
        mbCriticalError, MB_OK);
      Abort;
    end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    if not RunServiceAction('Uninstall') then
    begin
      MsgBox('Diagnostic service removal failed. Check Windows Services before deleting program files.',
        mbCriticalError, MB_OK);
      Abort;
    end;
end;
