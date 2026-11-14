#define AppName "TwinConnect WFP Guard VM Test"
#define GuardExe "TwinConnectGlobalGuard.exe"
[Setup]
AppId={{DA45E022-8D6C-4EB4-8195-3D14F251F5B3}
AppName={#AppName}
AppVersion=0.1.0-vm-test
AppPublisher=TwinConnect
DefaultDirName={autopf}\TwinConnectGuardVMTest
OutputBaseFilename=TwinConnect-WFP-Guard-VM-TEST-Setup
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
Source: "build\guard-vm-test\{#GuardExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "tools\install_guard_vm_test.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Code]
function GuardAction(Action: String): Boolean;
var
  Code: Integer;
  Args: String;
begin
  Args := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{app}\install_guard_vm_test.ps1') + '" -Action ' + Action +
    ' -BinaryPath "' + ExpandConstant('{app}\{#GuardExe}') + '"';
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    Args, '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
end;

procedure CurStepChanged(Step: TSetupStep);
begin
  if Step = ssPostInstall then
    if not GuardAction('Install') then
    begin
      MsgBox('VM-only guard service setup failed. Windows firewall blocking was NOT enabled. ' +
        'Set TWINCONNECT_DISPOSABLE_VM=1 in a disposable virtual machine.',
        mbCriticalError, MB_OK);
      Abort;
    end;
end;

procedure CurUninstallStepChanged(Step: TUninstallStep);
begin
  if Step = usUninstall then
    if not GuardAction('Uninstall') then
    begin
      MsgBox('Could not verify owned-WFP-rule removal. Uninstall stopped to preserve recovery binary.',
        mbCriticalError, MB_OK);
      Abort;
    end;
end;
