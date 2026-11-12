import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/mieru_client_profile.dart';

Map<String, dynamic> mieruItem() => {
  'config_format': 'mieru-json',
  'node_id': 25,
  'config': jsonEncode({
    'profiles': [{
      'profileName': 'account-1',
      'user': {'name': 'account-1', 'password': 'synthetic-secret'},
      'servers': [{
        'ipAddress': '93.184.216.34',
        'domainName': '',
        'portBindings': [
          {'port': 12345, 'protocol': 'TCP'},
          {'port': 12345, 'protocol': 'UDP'},
        ],
      }],
      'mtu': 1400,
      'multiplexing': {'level': 'MULTIPLEXING_LOW'},
      'handshakeMode': 'HANDSHAKE_STANDARD',
    }],
    'activeProfile': 'account-1',
    'rpcPort': 8964,
    'socks5Port': 1080,
    'socks5ListenLAN': false,
    'httpProxyPort': 8080,
    'httpProxyListenLAN': false,
  }),
};

void main() {
  test('keeps actual Mieru account identity and fixes only loopback ports', () {
    final valid = MieruClientProfile.fromItem(mieruItem());
    final runtime = valid.runtimeConfig(socks5Port: 34101, rpcPort: 34102, httpProxyPort: 34103);
    expect(runtime['activeProfile'], 'account-1');
    expect(runtime['socks5Port'], 34101);
    expect(runtime['rpcPort'], 34102);
    expect(runtime['socks5ListenLAN'], false);
    expect(runtime['httpProxyPort'], 34103);
    expect(runtime['httpProxyListenLAN'], false);
    expect(valid.endpointIpv4, '93.184.216.34');
    final account = (runtime['profiles'] as List).single as Map;
    expect((account['user'] as Map)['password'], 'synthetic-secret');
    expect(((account['servers'] as List).single as Map)['portBindings'],
        hasLength(2));
  });

  test('Mieru rejects unauthorized dialers and LAN listening', () {
    final obj = jsonDecode(mieruItem()['config'] as String)
        as Map<String, dynamic>;
    obj['socks5ListenLAN'] = true;
    expect(() => MieruClientProfile.fromItem({
      'config_format': 'mieru-json', 'config': jsonEncode(obj),
    }), throwsFormatException);
    obj['socks5ListenLAN'] = false;
    obj['profiles'][0]['dialer'] = {'protocol': 'SOCKS5_PROXY_PROTOCOL'};
    expect(() => MieruClientProfile.fromItem({
      'config_format': 'mieru-json', 'config': jsonEncode(obj),
    }), throwsFormatException);
  });

  test('Mieru cannot collide local SOCKS5 and RPC ports', () {
    final valid = MieruClientProfile.fromItem(mieruItem());
    expect(() => valid.runtimeConfig(socks5Port: 1080, rpcPort: 1080, httpProxyPort: 2080),
        throwsFormatException);
    expect(() => valid.runtimeConfig(socks5Port: 80, rpcPort: 2000, httpProxyPort: 3000),
        throwsFormatException);
  });
}
