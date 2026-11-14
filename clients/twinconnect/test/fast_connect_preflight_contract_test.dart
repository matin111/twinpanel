import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('all sing-box protocols verify required checks concurrently', () {
    final engine = File('lib/windows_singbox_tunnel.dart').readAsStringSync();
    final validation = engine.indexOf('final preTunnelChecks = await Future.wait<Object>([');
    final start = engine.indexOf('started = await Process.start(');
    final gate = engine.indexOf("if (preTunnelChecks[0] != true)");
    expect(validation, greaterThan(-1));
    expect(gate, greaterThan(validation));
    expect(start, greaterThan(gate));
    expect(engine, contains('WindowsSingBoxPreflight.checkInMemory(config),'));
    expect(engine, contains('proxyCheck,'));
    expect(engine, contains('baselineCheck,'));
    expect(engine, contains('ip != before && ip == verifiedProxyIp'));
  });

  test('Fast Server respects ready protocols and never defaults to WireGuard', () {
    final ui = File('lib/live_dashboard.dart').readAsStringSync();
    final begin = ui.indexOf('Future<void> _enableFastestAndConnect()');
    final end = ui.indexOf('void _resetNetworkStats()', begin);
    final fast = ui.substring(begin, end);
    expect(fast, contains('NativeVpnBridge.protocolReadiness()'));
    expect(fast, contains('authorized.where(ready.supports)'));
    expect(fast, contains("prefs.getString('twinconnect_last_verified_protocol')"));
    expect(fast, contains('_filter != \'all\''));
    expect(fast, contains('_fastestKnownIndex'));
    expect(fast, contains('await _toggleVpn()'));
    expect(fast, contains('_filter = previousFilter'));
    expect(fast, isNot(contains("'wireguard', 'openvpn', 'cisco'")));
    expect(fast, isNot(contains('eligible.where(authorized.contains).firstOrNull')));
    expect(ui, contains('value: _autoFastest,'));
  });

  test('Xray runtime needs verified SOCKS and remote HTTPS before TUN', () {
    final xray = File('lib/windows_xray_proxy.dart').readAsStringSync();
    final ui = File('lib/live_dashboard.dart').readAsStringSync();
    expect(xray, contains('if (!ready || !identical(_child, ownedProcess))'));
    expect(xray, contains('await _probeHttpExit(httpPort)'));
    expect(ui, contains('WindowsSingBoxTunnel.measureBaselineIp()'));
    expect(ui, contains('_xrayProxy.start(chosen)'));
    expect(ui, contains('xrayVerifiedExitIp: verifiedExit'));
    expect(ui, contains('baselinePublicIp: baselineIp'));
  });

  test('health fallback never accepts arbitrary changed VPN exit IP', () {
    final tunnel = File('lib/windows_singbox_tunnel.dart').readAsStringSync();
    expect(tunnel, contains('_requestAlternativePublicIp()'));
    expect(tunnel, contains('alternate == expected'));
    expect(tunnel, contains('actual == expected'));
    expect(tunnel, contains('routeDeadline.elapsed < const Duration(seconds: 14)'));
  });
}
