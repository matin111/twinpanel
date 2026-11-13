import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/xray_endpoint_route.dart';
import 'package:twinconnect/xray_inbound_profiles.dart';
import 'package:twinconnect/xray_windows_config.dart';
import 'package:twinconnect/singbox_windows_config.dart';

void main() {
  const uuid = '11111111-2222-4333-8444-555555555555';
  XrayInboundProfile profile(String id, String type, String security,
      String extras) => XrayInboundProfile.tryParse({
    'id': id,
    'uri': 'vless://$uuid@vpn.example.org:443?encryption=none'
        '&type=$type&security=$security&sni=front.example.org$extras',
  }, '23')!;

  test('one validated public IPv4 is the only TUN route exclusion', () {
    expect(XrayEndpointRoute.requirePublicIPv4('203.0.113.40'),
        '203.0.113.40');
    final config = SingBoxWindowsConfig.compose(
      protocol: 'v2ray', item: const <String, dynamic>{},
      xraySocksPort: 18008,
      xrayEndpointIPv4: '203.0.113.40',
    );
    final tun = (config['inbounds'] as List).single as Map;
    expect(tun['route_exclude_address'], ['203.0.113.40/32']);
    expect(tun['strict_route'], true);
    expect((config['dns'] as Map)['final'], 'dns-remote');
  });

  test('private/multicast and broad routes cannot bypass TUN', () {
    for (final ip in ['10.2.3.4', '172.20.1.1', '192.168.1.1',
      '100.100.1.1', '127.0.0.1', '224.0.0.1', '0.0.0.0',
      '203.0.113.0/24', '::1']) {
      expect(() => XrayEndpointRoute.requirePublicIPv4(ip),
          throwsFormatException, reason: ip);
    }
  });

  test('pinned VLESS endpoint preserves TLS SNI and HTTP Host', () {
    final inbound = profile('websocket_tls', 'ws', 'tls', '&path=%2Fws');
    final config = XrayWindowsConfig.compose(
      inbound: inbound, localSocksPort: 18008,
      pinnedServerIPv4: '203.0.113.40',
    );
    final outbound = (config['outbounds'] as List).first as Map;
    final server = ((outbound['settings'] as Map)['vnext'] as List).first as Map;
    final stream = outbound['streamSettings'] as Map;
    expect(server['address'], '203.0.113.40');
    expect((stream['tlsSettings'] as Map)['serverName'], 'front.example.org');
    expect((stream['wsSettings'] as Map)['headers']['Host'],
        'vpn.example.org');
  });

  test('REALITY public key and server name survive IPv4 pinning', () {
    final inbound = profile('xhttp_reality', 'xhttp', 'reality',
        '&path=%2Fxhttp&pbk=publicKey&sid=01');
    final config = XrayWindowsConfig.compose(
      inbound: inbound, localSocksPort: 18008,
      pinnedServerIPv4: '203.0.113.40',
    );
    final stream = (config['outbounds'] as List).first['streamSettings'] as Map;
    expect(stream['security'], 'reality');
    expect((stream['realitySettings'] as Map)['serverName'],
        'front.example.org');
    expect((stream['realitySettings'] as Map)['publicKey'], 'publicKey');
    expect((stream['xhttpSettings'] as Map)['path'], '/xhttp');
  });
}
