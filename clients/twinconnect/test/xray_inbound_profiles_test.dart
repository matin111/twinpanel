import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/xray_inbound_profiles.dart';

void main() {
  const uuid = '11111111-2222-4333-8444-555555555555';
  Map<String, dynamic> row(String id, String type, String security,
      {String extra = ''}) => {
    'id': id,
    'title': id,
    'uri': 'vless://$uuid@example.com:443?encryption=none'
        '&type=$type&security=$security&sni=example.com$extra',
  };

  test('preserves three independently selectable real inbounds', () {
    final response = <String, dynamic>{
      'schema': 1,
      'protocol': 'v2ray',
      'server_groups': [
        {
          'node_id': 12,
          'profiles': [
            row('websocket_tls', 'ws', 'tls', extra: '&path=%2Fsocket'),
            row('xhttp_reality', 'xhttp', 'reality',
                extra: '&path=%2Fxhttp&pbk=exampleKey&sid=01'),
            row('tcp_tls', 'tcp', 'tls'),
          ],
        },
      ],
    };
    final groups = XrayServerProfiles.fromResponse(response);
    expect(groups, hasLength(1));
    expect(groups.single.serverId, '12');
    expect(groups.single.inbounds.map((p) => p.id),
        ['websocket_tls', 'xhttp_reality', 'tcp_tls']);
  });

  test('does not invent missing or invalid inbounds', () {
    final response = <String, dynamic>{
      'schema': 1,
      'protocol': 'v2ray',
      'server_groups': [
        {
          'node_id': 2,
          'profiles': [
            row('websocket_tls', 'ws', 'tls', extra: '&path=%2Fsocket'),
            row('xhttp_reality', 'ws', 'reality',
                extra: '&path=%2Fxhttp&pbk=key&sid=01'),
            row('tcp_simple', 'tcp', 'none'),
          ],
        },
      ],
    };
    final groups = XrayServerProfiles.fromResponse(response);
    expect(groups.single.inbounds, hasLength(1));
    expect(groups.single.inbounds.single.id, 'websocket_tls');
  });

  test('rejects duplicate server identity', () {
    expect(() => XrayServerProfiles.fromResponse({
      'schema': 1,
      'protocol': 'v2ray',
      'server_groups': [
        {'node_id': 2, 'profiles': []},
        {'node_id': 2, 'profiles': []},
      ],
    }), throwsFormatException);
  });
}
