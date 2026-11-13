import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/native_vpn_bridge.dart';
import 'package:twinconnect/vpn_policy.dart';

void main() {
  test('Windows WFP preflight is read-only and never enables global filtering', () {
    final header = File('native/windows/twinconnect_global_killswitch.h')
        .readAsStringSync();
    expect(header, contains('FwpmEngineOpen0('));
    expect(header, contains('FWPM_SESSION_FLAG_DYNAMIC'));
    expect(header, contains('FwpmEngineClose0(engine)'));
    expect(header, contains('const bool recoveryVerified = false;'));
    expect(header, contains('OpenServiceW('));
    expect(header, contains('OwnedFilterExists('));
    expect(header, contains('FWPM_SESSION_FLAG_DYNAMIC'));
    expect(header, isNot(contains('FwpmFilterAdd')));
    expect(header, isNot(contains('FwpmFilterDelete')));
    expect(header, isNot(contains('FwpmSubLayerAdd')));
    expect(header, isNot(contains('FWPM_FILTER_FLAG_PERSISTENT')));
  });

  test('system-wide WFP experiment includes atomic restore and dual-stack filters', () {
    final source = File('native/windows/twinconnect_global_guard_experimental.cpp')
        .readAsStringSync();
    expect(source, contains('FWPM_FILTER_FLAG_PERSISTENT'));
    expect(source, contains('FWPM_CONDITION_ALE_APP_ID'));
    expect(source, contains('FwpmGetAppIdFromFileName0'));
    expect(source, contains('FWPM_CONDITION_IP_REMOTE_ADDRESS'));
    expect(source, contains('FWP_ACTION_PERMIT'));
    expect(source, contains('AddBlockRule('));
    expect(source, contains('AddTransportPermit('));
    expect(source, contains('RemoveOwned(engine, kPermitV4)'));
    expect(source, contains('FWPM_LAYER_ALE_AUTH_CONNECT_V4'));
    expect(source, contains('FWPM_LAYER_ALE_AUTH_CONNECT_V6'));
    expect(source, contains('FwpmTransactionBegin0('));
    expect(source, contains('FwpmTransactionCommit0('));
    expect(source, contains('FwpmTransactionAbort0('));
    expect(source, contains('filter->action.type'));
    expect(source, contains('FWPM_CONDITION_IP_LOCAL_INTERFACE'));
    expect(source, contains('FWPM_CONDITION_ALE_APP_ID'));
    expect(source, contains('filter->numFilterConditions'));
    expect(source, contains('const DWORD recovery = TransactionalDisarm(engine)'));

    expect(source, contains('TransactionalDisarm('));
    expect(source, contains('I_ACCEPT_OFFLINE_RECOVERY'));
    final workflow = File('../../.github/workflows/twinconnect-wfp-experimental.yml')
        .readAsStringSync();
    expect(workflow, contains('Build experimental WFP tool without installing'));
    expect(workflow, contains("NEVER invoke 'arm' or 'disarm'"));
  });

  test('VM leak test must verify network recovery and retain emergency restore until confirmed', () {
    final script = File('tools/test_windows_global_guard_vm.ps1')
        .readAsStringSync();
    final workflow = File('../../.github/workflows/twinconnect-wfp-vm-leak-test.yml')
        .readAsStringSync();
    expect(script, contains('TwinConnectWfpEmergencyRestore'));
    expect(script, contains('function Test-Physical-Dns'));
    expect(script, contains('function Set-Physical-Interface'));
    expect(script, contains('HostToNetworkOrder'));
    expect(script, contains('SetSocketOption('));
    expect(script, contains(r'-InterfaceIndex $physicalV4Index'));
    expect(script, contains(r'-InterfaceIndex $physicalV6Index'));

    expect(script, contains('IPv4 DNS UDP leaked outside tunnel'));
    expect(script, contains('IPv6 DNS UDP leaked outside tunnel'));
    expect(script, contains('dns4Restored'));
    expect(script, contains('dns6Restored'));
    expect(script, contains('OWNED_RULES_PRESENT 0 0 0'));
    expect(script, contains(r'if ($recovered -and $restored)'));
    expect(script, contains(r'if (!$recovered -or !$restored)'));
    expect(script, contains(r'Test-Physical-Egress -SourceAddress $PhysicalIpv4'));
    expect(script, contains(r'Test-Physical-Egress -SourceAddress $PhysicalIpv6'));
    expect(workflow, contains('self-hosted, windows, x64, twinconnect-disposable-vm'));
    expect(workflow, isNot(contains('runs-on: windows-latest')));
  });

  test('privileged Windows service owns lockdown and independent recovery', () {
    final code = File('native/windows/twinconnect_global_guard_service_experimental.cpp')
        .readAsStringSync();
    expect(code, contains('SERVICE_WIN32_OWN_PROCESS'));
    expect(code, contains('StartServiceCtrlDispatcherW('));
    expect(code, contains('CreateNamedPipeW('));
    expect(code, contains('PIPE_REJECT_REMOTE_CLIENTS'));
    expect(code, contains('D:P(A;;GA;;;SY)(A;;GA;;;BA)'));
    expect(code, contains('TransactionalArm('));
    expect(code, contains('RecoveryTaskReady()'));
    expect(code, contains('GetIfEntry2(&adapter)'));
    expect(code, contains('adapter.OperStatus != IfOperStatusUp'));
    expect(code, contains('adapter.InterfaceAndOperStatusFlags.HardwareInterface'));
    expect(code, contains('IF_TYPE_SOFTWARE_LOOPBACK'));

    expect(code, contains('ERR RECOVERY_TASK_NOT_VERIFIED'));
    expect(code, contains('CLSID_TaskScheduler'));
    expect(code, contains('TwinConnectWfpEmergencyRestore'));
    expect(code, contains('get_NextRunTime'));
    expect(code, contains('recover I_ACCEPT_OFFLINE_RECOVERY'));

    expect(code, contains('TransactionalDisarm('));
    expect(code, contains('offline-status'));
    expect(code, contains('OwnedFilterPresent(engine.handle, kBlockV4)'));
    expect(code, contains('recover'));
    expect(code, contains('InstallVmOnlyService('));
    expect(code, contains('UninstallVmOnlyService('));
    expect(code, contains('SERVICE_DEMAND_START'));
    expect(code, isNot(contains('SERVICE_AUTO_START')));
    final workflow = File('../../.github/workflows/twinconnect-wfp-experimental.yml')
        .readAsStringSync();
    expect(workflow, contains('Compile standalone privileged guard service'));
    expect(workflow, contains("Never invoke 'arm'"));
    expect(workflow, contains(r'recover $ack'));
    expect(workflow, contains(r'uninstall-vm $ack'));
  });

  test('VM-only control is wired from Flutter through native Windows to admin IPC', () {
    final bridge = File('lib/native_vpn_bridge.dart').readAsStringSync();
    final settings = File('lib/vpn_settings.dart').readAsStringSync();
    final installer = File('tools/install_windows_native.py').readAsStringSync();
    final header = File('native/windows/twinconnect_guard_control.h').readAsStringSync();
    expect(bridge, contains('experimentalVmGlobalGuard'));
    expect(settings, contains("Key('vpnVmArm')"));
    expect(settings, contains("Key('vpnVmDisarm')"));
    expect(settings, contains("TWINCONNECT_DISPOSABLE_VM"));
    expect(installer, contains('experimentalVmGlobalGuard'));
    expect(installer, contains('twinconnect_guard_control::SendVmOnly'));
    expect(header, contains('PIPE_READMODE_MESSAGE'));
    expect(header, contains('SERVICE_UNAVAILABLE'));
    expect(header, contains('VM_ONLY'));
  });

  test('Windows setup provisions only a certified signed guard with recovery-first uninstall', () {
    final setup = File('installer.iss').readAsStringSync();
    final script = File('tools/install_guard_service.ps1').readAsStringSync();
    expect(setup, contains('#define IncludeVerifiedGlobalGuard 0'));
    expect(setup, contains('#if IncludeVerifiedGlobalGuard'));
    expect(setup, contains('install_guard_service.ps1'));
    expect(setup, contains('-Action Install'));
    expect(setup, contains('-Action Uninstall'));
    expect(script, contains("Get-AuthenticodeSignature"));
    expect(script, contains('ExpectedSignerThumbprint'));
    expect(script, contains('Assert-ServiceIdentity'));
    expect(script, contains('offline-status'));
    expect(script, contains(r"if ($service.Status -ne 'Running')"));
    expect(script, contains("start= auto"));
    expect(script, contains("Start-Service -Name"));
    expect(script, contains(r'& $binary recover $ack'));
    expect(script, contains("Owned WFP filters still present"));
    expect(script, contains("offline-status"));
    expect(script, contains("Stop-Service -Name"));

    expect(script, isNot(contains("arm I_ACCEPT_OFFLINE_RECOVERY")));
  });

  test('native bridge installs only a read-only guard status method', () {
    final install = File('tools/install_windows_native.py')
        .readAsStringSync();
    expect(install, contains('twinconnect_global_killswitch.h'));
    expect(install, contains('getGlobalKillSwitchStatus'));
    expect(install, contains('twinconnect_global_killswitch::Preflight()'));
    expect(install, isNot(contains('setGlobalKillSwitchEnabled')));
  });

  test('system-wide kill switch must not be claimed through saved preferences', () {
    const policy = VpnPolicy(killSwitchRequested: true);
    final native = NativeVpnCapabilities(
      platform: VpnPlatform.windows,
      engineReady: true,
      fullTunnel: true,
      dnsGuard: true,
      ipv6Guard: true,
      killSwitchEnforced: false,
    );
    expect(policy.connectionProblems(native),
        contains('KILL_SWITCH_NOT_ENFORCED'));
    expect(
      () => NativeVpnBridge.requireSafeToConnect(policy, native),
      throwsStateError,
    );
  });

  test('settings cannot activate global guard without enforcement', () {
    final screen = File('lib/vpn_settings.dart').readAsStringSync();
    expect(screen, contains('NativeVpnBridge.globalKillSwitchStatus()'));
    expect(screen, contains('Protection service not ready'));
    expect(screen, contains('onChanged: null'));
    expect(screen, isNot(contains('setGlobalKillSwitchEnabled')));
  });
}
