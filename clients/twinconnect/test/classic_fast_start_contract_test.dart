import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Cisco/OpenVPN/L2TP first-connect uses fresh parallel HTTPS baseline', () {
    final ui = File('lib/live_dashboard.dart').readAsStringSync();
    expect(ui, contains('bool get _canPrefetchDirectBaseline'));
    expect(ui, contains('!_vpnUp && !_vpnCleanup && !_vpnUnmanaged && !_modernUp'));
    expect(ui, contains('!_modernTunnel.isRunning && !_xrayProxy.isRunning'));
    expect(ui, contains('_loadNativeProfilesWithBaseline('));
    expect(ui, contains('directIp().then((ip) => (ip: ip, measuredAt: DateTime.now()))'));
    expect(ui, contains('const Duration(seconds: 8)'));
    expect(ui, contains('directIp: WindowsOpenConnectTunnel.directPublicIp'));
    expect(ui, contains('directIp: WindowsOpenVpnTunnel.publicIp'));
    expect(ui, contains('directIp: WindowsL2tpTunnel.directPublicIp'));
    expect(ui, contains('baselinePublicIp: prepared.baselineIp'));
  });

  test('classic engines never skip native status or verified egress', () {
    final cisco = File('lib/windows_openconnect_tunnel.dart').readAsStringSync();
    final openvpn = File('lib/windows_openvpn_tunnel.dart').readAsStringSync();
    final l2tp = File('lib/windows_l2tp_tunnel.dart').readAsStringSync();
    expect(cisco, contains("'openConnectStatus'"));
    expect(cisco, contains('if (ip != _baselineIp)'));
    expect(cisco, contains('Future.wait<Object?>(['));
    expect(openvpn, contains('Future.wait<Object>(['));
    expect(openvpn, contains('verifiedEgressAfterConnect(before)'));
    expect(openvpn, contains('if (ip != baseline) return ip'));
    expect(l2tp, contains('if (status.state == 2)'));
    expect(l2tp, contains('hasVpnEgress(baselineIp: baselineIp, currentIp: newIp)'));
    expect(l2tp, contains('L2TP_EGRESS_NOT_VERIFIED'));
  });

  test('WireGuard catalog overlaps local checks and is still authorized', () {
    final ui = File('lib/live_dashboard.dart').readAsStringSync();
    final bootstrap = File('lib/connection_bootstrap.dart').readAsStringSync();
    expect(ui, contains('currentAttemptCatalog: Future<PanelProtocolCatalog>.value('));
    expect(ui, contains('api.loadSessionProtocolCatalog('));
    expect(bootstrap, contains('currentAttemptCatalog ??'));
    expect(bootstrap, contains('catalog.namespace != panel.namespace'));
    expect(bootstrap, contains("'PROTOCOL_NOT_ALLOWED'"));
  });
}
