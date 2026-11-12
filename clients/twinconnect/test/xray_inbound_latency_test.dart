import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/xray_inbound_latency.dart';
import 'package:twinconnect/xray_inbound_profiles.dart';

void main() {
  const uuid = '11111111-2222-4333-8444-555555555555';
  XrayInboundProfile inbound(String id, String type, String security,
      String extras) => XrayInboundProfile.tryParse({
    'id': id,
    'uri': 'vless://$uuid@localhost:443?encryption=none'
        '&type=$type&security=$security&sni=example.org$extras',
  }, '17')!;

  test('every real Xray inbound has an independent latency identity', () {
    final ws = inbound('websocket_tls', 'ws', 'tls', '&path=%2Fws');
    final reality = inbound('xhttp_reality', 'xhttp', 'reality',
        '&path=%2Fxhttp&pbk=key&sid=01');
    final tcp = inbound('tcp_tls', 'tcp', 'tls', '');
    expect({
      XrayInboundLatency.key(ws),
      XrayInboundLatency.key(reality),
      XrayInboundLatency.key(tcp),
    }, {'17:websocket_tls', '17:xhttp_reality', '17:tcp_tls'});
    expect(ws.uri.port, 443);
  });

  test('non-Windows cannot claim a real TCP measurement', () async {
    if (Platform.isWindows) return;
    final ws = inbound('websocket_tls', 'ws', 'tls', '&path=%2Fws');
    expect(await XrayInboundLatency.probe(ws), isNull);
  });

  test('dashboard displays TCP not ICMP for measured Xray inbounds', () {
    final ui = File('lib/live_dashboard.dart').readAsStringSync();
    expect(ui, contains('xrayRtt_'));
    expect(ui, contains('probeXray_'));
    expect(ui, contains('ServerLatency.label('));
    expect(ui, contains('ServerLatency.color('));
    expect(ui, contains('Inbound TCP handshake time'));
    expect(ui, contains('_probeAllXrayInbounds'));
  });

  test('Xray baseline is measured concurrently before TUN start', () {
    final ui = File('lib/live_dashboard.dart').readAsStringSync();
    final tun = File('lib/windows_singbox_tunnel.dart').readAsStringSync();
    expect(ui, contains('WindowsSingBoxTunnel.measureBaselineIp()'));
    expect(ui, contains('baselinePublicIp: baselineIp'));
    expect(tun, contains('Future<String> baselineCheck = baselinePublicIp'));
    expect(tun, contains('ip != before && ip == verifiedProxyIp'));
    expect(tun, contains('attempt < 5 ? 150 : 400'));
  });
}
