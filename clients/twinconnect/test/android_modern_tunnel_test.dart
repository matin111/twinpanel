import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/android_modern_tunnel.dart';
import 'package:twinconnect/vpn_policy.dart';

void main() {
  test('real engine only covers supported modern protocol families', () {
    expect(AndroidModernTunnel.protocolCodes,
        {'hysteria2', 'tuic', 'anytls', 'snell', 'socks5'});
    for (final unsupported in [
      'cisco', 'openvpn', 'l2tp', 'v2ray', 'naive', 'shadowtls',
      'mieru', 'trusttunnel', 'amneziawg', 'sudoku',
    ]) {
      expect(() => AndroidModernTunnel.ensureSupported(unsupported),
          throwsFormatException);
    }
  });

  test('modern tunnel rejects unverified VPN policy and kill switch', () {
    AndroidModernTunnel.requireSafePolicy(const VpnPolicy());
    expect(
      () => AndroidModernTunnel.requireSafePolicy(
          const VpnPolicy(killSwitchRequested: true)),
      throwsFormatException,
    );
    expect(
      () => AndroidModernTunnel.requireSafePolicy(
          const VpnPolicy(allowLan: true)),
      throwsFormatException,
    );
  });

  test('SOCKS5 requires a panel-provided authenticated outbound', () {
    final valid = AndroidModernTunnel.validatedOutbound(
      protocol: 'socks5',
      item: {
        'outbound': {
          'type': 'socks',
          'server': 'vpn.example.org',
          'server_port': 1080,
          'version': '5',
          'username': 'sample',
          'password': 'sample-password',
        },
      },
    );
    expect(valid['type'], 'socks');
    expect(
      () => AndroidModernTunnel.validatedOutbound(
        protocol: 'socks5',
        item: {'outbound': {'type': 'socks', 'server': 'vpn.example.org',
          'server_port': 1080, 'version': '5'}},
      ),
      throwsFormatException,
    );
  });
}
