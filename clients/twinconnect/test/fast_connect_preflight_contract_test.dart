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
