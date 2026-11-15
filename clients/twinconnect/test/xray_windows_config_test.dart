import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/xray_inbound_profiles.dart';
import 'package:twinconnect/xray_windows_config.dart';

void main() {
  const uuid = '11111111-2222-4333-8444-555555555555';

  XrayInboundProfile parse(String id, String type, String security,
      String extra) {
    final row = <String, dynamic>{
      'id': id,
      'uri': 'vless://$uuid@example.com:443?encryption=none'
          '&type=$type&security=$security&sni=example.org$extra',
    };
    return XrayInboundProfile.tryParse(row, '7')!;
  }

  test('TLS TCP uses TLS network and unchanged target', () {
    final profile = parse('tcp_tls', 'tcp', 'tls', '&fp=chrome');
    final config = XrayWindowsConfig.compose(
        inbound: profile, localSocksPort: 13579);
    final outbound = (config['outbounds'] as List).first as Map;
    final stream = outbound['streamSettings'] as Map;
    expect(stream['network'], 'tcp');
    expect((stream['tlsSettings'] as Map)['serverName'], 'example.org');
    final vnext = ((outbound['settings'] as Map)['vnext'] as List).first as Map;
    expect(vnext['address'], 'example.com');
    expect(vnext['port'], 443);
    expect((config['inbounds'] as List).first['listen'], '127.0.0.1');
  });

  test('WS TLS retains path and Host', () {
    final profile = parse('websocket_tls', 'ws', 'tls',
        '&path=%2Fws-inbound&host=cdn.example.org');
    final config = XrayWindowsConfig.compose(
        inbound: profile, localSocksPort: 13580);
    final stream = (config['outbounds'] as List).first['streamSettings'] as Map;
    expect((stream['wsSettings'] as Map)['path'], '/ws-inbound');
    expect((stream['wsSettings'] as Map)['headers']['Host'],
        'cdn.example.org');
  });

  test('XHTTP Reality retains public key, short ID, and stream-one', () {
    final profile = parse('xhttp_reality', 'xhttp', 'reality',
        '&path=%2Fxhttp&mode=stream-one&pbk=publicKeyHere&sid=0123');
    final config = XrayWindowsConfig.compose(
        inbound: profile, localSocksPort: 13581);
    final stream = (config['outbounds'] as List).first['streamSettings'] as Map;
    expect(stream['network'], 'xhttp');
    expect((stream['xhttpSettings'] as Map)['mode'], 'stream-one');
    expect((stream['realitySettings'] as Map)['publicKey'], 'publicKeyHere');
    expect((stream['realitySettings'] as Map)['shortId'], '0123');
  });

  test('rejects invalid listener port', () {
    final profile = parse('tcp_tls', 'tcp', 'tls', '');
    expect(() => XrayWindowsConfig.compose(
        inbound: profile, localSocksPort: 80), throwsFormatException);
  });
}
