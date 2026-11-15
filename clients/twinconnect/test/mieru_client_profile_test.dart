import 'dart:convert';
import 'dart:io';

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
  test('keeps actual Mieru account identity and fixes only loopback ports', () async {
    final valid = MieruClientProfile.fromItem(mieruItem());
    final runtime = valid.runtimeConfig(socks5Port: 34101, rpcPort: 34102, httpProxyPort: 34103, resolvedEndpointIpv4: '93.184.216.34');
    expect(runtime['activeProfile'], 'account-1');
    expect(runtime['socks5Port'], 34101);
    expect(runtime['rpcPort'], 34102);
    expect(runtime['socks5ListenLAN'], false);
    expect(runtime['httpProxyPort'], 34103);
    expect(runtime['httpProxyListenLAN'], false);
    expect(await valid.resolveEndpointIpv4(), '93.184.216.34');
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

  test('live Turkish style Mieru domain overrides the stale IP and pins one safe exit', () async {
    final delivered = jsonDecode(mieruItem()['config'] as String)
        as Map<String, dynamic>;
    final server = (delivered['profiles'][0]['servers'] as List).single as Map;
    server['ipAddress'] = '93.184.216.35';
    server['domainName'] = 'tr.example.org';
    final profile = MieruClientProfile.fromItem({
      'config_format': 'mieru-json', 'config': jsonEncode(delivered),
    });
    String? requestedHost;
    final endpoint = await profile.resolveEndpointIpv4(
      lookup: (host) async {
        requestedHost = host;
        return [InternetAddress('10.0.0.1'), InternetAddress('93.184.216.34')];
      },
    );
    expect(requestedHost, 'tr.example.org');
    expect(endpoint, '93.184.216.34');
    final runtime = profile.runtimeConfig(
      socks5Port: 34101, rpcPort: 34102, httpProxyPort: 34103,
      resolvedEndpointIpv4: endpoint,
    );
    final rewritten = (runtime['profiles'][0]['servers'] as List).single as Map;
    expect(rewritten['ipAddress'], '93.184.216.34');
    expect(rewritten['domainName'], '');
    expect(server['ipAddress'], '93.184.216.35');
    expect(server['domainName'], 'tr.example.org');
    final account = (runtime['profiles'] as List).single as Map;
    expect((account['user'] as Map)['password'], 'synthetic-secret');
  });

  test('Mieru accepts official domain-only and port-range config', () async {
    final delivered = jsonDecode(mieruItem()['config'] as String)
        as Map<String, dynamic>;
    final server = (delivered['profiles'][0]['servers'] as List).single as Map;
    server['ipAddress'] = '';
    server['domainName'] = 'tr.example.org';
    server['portBindings'] = [
      {'portRange': '20000-20005', 'protocol': 'TCP'},
      {'port': 24000, 'protocol': 'UDP'},
    ];
    final profile = MieruClientProfile.fromItem({
      'config_format': 'mieru-json', 'config': jsonEncode(delivered),
    });
    expect(await profile.resolveEndpointIpv4(
      lookup: (_) async => [InternetAddress('93.184.216.34')],
    ), '93.184.216.34');
  });

  test('Mieru rejects private DNS exit and malformed native binding', () async {
    final delivered = jsonDecode(mieruItem()['config'] as String)
        as Map<String, dynamic>;
    final server = (delivered['profiles'][0]['servers'] as List).single as Map;
    server['domainName'] = 'tr.example.org';
    final profile = MieruClientProfile.fromItem({
      'config_format': 'mieru-json', 'config': jsonEncode(delivered),
    });
    await expectLater(
      profile.resolveEndpointIpv4(
        lookup: (_) async => [InternetAddress('192.168.1.50')],
      ),
      throwsFormatException,
    );
    server['portBindings'] = [{'protocol': 'TCP', 'portRange': '500-200'}];
    expect(() => MieruClientProfile.fromItem({
      'config_format': 'mieru-json', 'config': jsonEncode(delivered),
    }), throwsFormatException);
  });

  test('Mieru cannot collide local SOCKS5 and RPC ports', () {
    final valid = MieruClientProfile.fromItem(mieruItem());
    expect(() => valid.runtimeConfig(socks5Port: 1080, rpcPort: 1080, httpProxyPort: 2080, resolvedEndpointIpv4: '93.184.216.34'),
        throwsFormatException);
    expect(() => valid.runtimeConfig(socks5Port: 80, rpcPort: 2000, httpProxyPort: 3000, resolvedEndpointIpv4: '93.184.216.34'),
        throwsFormatException);
  });
}
