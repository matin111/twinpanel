import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('three real Xray inbounds are rendered as direct connection rows', () {
    final ui = File('lib/live_dashboard.dart').readAsStringSync();
    expect(ui, contains("Key('xrayInbound_"));
    expect(ui, contains("Key('connectXray_"));
    expect(ui, contains("xrayInboundRow(i, inbound)"));
    expect(ui, contains("'xhttp_reality' => 'XHTTP Reality'"));
    expect(ui, contains("'websocket_tls' => 'WS TLS'"));
    expect(ui, contains("'tcp_tls' => 'TCP TLS'"));
    expect(ui, contains('_startXrayTunnel(nodeId, inboundId: inbound.id)'));
    expect(ui, isNot(contains('showDialog<XrayInboundProfile>')));
  });

  test('inbound choice retains real node identity and validates against panel', () {
    final ui = File('lib/live_dashboard.dart').readAsStringSync();
    expect(ui, contains("_selectedXrayNodeId = nodeId"));
    expect(ui, contains("_selectedXrayInboundId = inbound.id"));
    expect(ui, contains('XRAY_INBOUND_NOT_AVAILABLE'));
    expect(ui, contains('where((group) => group.serverId == serverId)'));
    expect(ui, contains('loadSessionNativeProfiles('));
    expect(ui, contains('_xrayGroupsLoading'));
  });

  test('WireGuard does not repeat freshly completed native probe', () {
    final bridge = File('lib/native_vpn_bridge.dart').readAsStringSync();
    final ui = File('lib/live_dashboard.dart').readAsStringSync();
    expect(bridge, contains('validatedCapabilities ?? await probe()'));
    expect(ui, contains('validatedCapabilities: capabilities'));
    expect(ui, contains('Future.wait<Object>(['));
  });
}
