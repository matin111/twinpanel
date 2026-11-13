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
    expect(source, contains('TransactionalDisarm('));
    expect(source, contains('I_ACCEPT_OFFLINE_RECOVERY'));
    final workflow = File('../../.github/workflows/twinconnect-wfp-experimental.yml')
        .readAsStringSync();
    expect(workflow, contains('Build experimental WFP tool without installing'));
    expect(workflow, contains("NEVER invoke 'arm' or 'disarm'"));
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
    expect(code, contains('TransactionalDisarm('));
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
