import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/singbox_windows_config.dart';

void main() {
  test('Xray SOCKS bridge builds strict-route TUN without exposing LAN proxy', () {
    final config = SingBoxWindowsConfig.compose(
      protocol: 'v2ray',
      item: const <String, dynamic>{},
      xraySocksPort: 19768,
      xrayEndpointIPv4: '203.0.113.45',
    );
    final outbounds = config['outbounds'] as List;
    final bridge = outbounds.single as Map;
    expect(bridge['type'], 'socks');
    expect(bridge['server'], '127.0.0.1');
    expect(bridge['server_port'], 19768);
    expect(bridge['version'], '5');
    final tun = (config['inbounds'] as List).single as Map;
    expect(tun['type'], 'tun');
    expect(tun['auto_route'], true);
    expect(tun['strict_route'], true);
    expect(tun['route_exclude_address'], ['203.0.113.45/32']);
    final dns = config['dns'] as Map;
    expect(dns['final'], 'dns-remote');
    final routes = config['route'] as Map;
    expect(routes['final'], 'proxy');
  });

  test('rejects Xray bridge with external port or wrong protocol', () {
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'v2ray', item: const <String, dynamic>{},
      xraySocksPort: 80,
    ), throwsFormatException);
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'openvpn', item: const <String, dynamic>{},
      xraySocksPort: 19768,
    ), throwsFormatException);
  });

  test('Xray bridge never accepts missing or broad route exceptions', () {
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'v2ray', item: const <String, dynamic>{},
      xraySocksPort: 19768,
    ), throwsFormatException);
    expect(() => SingBoxWindowsConfig.compose(
      protocol: 'v2ray', item: const <String, dynamic>{},
      xraySocksPort: 19768, xrayEndpointIPv4: '10.0.0.1',
    ), throwsFormatException);
    final ordinary = SingBoxWindowsConfig.compose(
      protocol: 'v2ray',
      item: const <String, dynamic>{},
      xraySocksPort: 19768,
      xrayEndpointIPv4: '203.0.113.45',
    );
    expect(ordinary['route']?['final'], 'proxy');
    expect((ordinary['inbounds'] as List).single['strict_route'], true);
  });

  test('real connection path checks both remote exit and post-TUN route', () {
    final xray = File('lib/windows_xray_proxy.dart').readAsStringSync();
    final tunnel = File('lib/windows_singbox_tunnel.dart').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(xray, contains('_probeHttpExit'));
    expect(xray, contains('XRAY_REMOTE_EGRESS_NOT_VERIFIED'));
    expect(tunnel, contains('xraySocksPort'));
    expect(tunnel, contains('ip != before && ip == verifiedProxyIp'));
    expect(dashboard, contains('_startXrayTunnel'));
    expect(dashboard, contains('xrayEndpointIPv4: pinnedEndpointIPv4'));
    // Inbounds are direct-selectable server rows: no extra modal.
    expect(dashboard, isNot(contains('showDialog<XrayInboundProfile>')));
    expect(dashboard, contains('xrayInboundRow(i, inbound)'));
    expect(dashboard, contains('_startXrayTunnel(nodeId, inboundId: inbound.id)'));
    expect(dashboard, contains('if (_xrayProxy.isRunning) await _xrayProxy.stop();'));
  });
}
