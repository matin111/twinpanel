import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/android_openvpn_tunnel.dart';
import 'package:twinconnect/vpn_policy.dart';

void main() {
  test('OpenVPN requires genuine client config from tenant API', () {
    expect(
      () => AndroidOpenVpnTunnel.requireProfile(const {
        'config': '[Interface]\\nPrivateKey = example\\n',
      }), throwsFormatException,
    );
    final sample = [
      'client',
      'dev tun',
      'proto udp',
      'remote vpn.example.org 1194',
      'remote-cert-tls server',
      'auth-user-pass',
      'nobind',
      'persist-tun',
      'persist-key',
    ].join('\n');
    // Test profile has no working server credentials or real endpoint.
    expect(AndroidOpenVpnTunnel.requireProfile({'config': sample}), sample);
  });

  test('OpenVPN refuses unsupported security policy', () {
    AndroidOpenVpnTunnel.requireSafePolicy(const VpnPolicy());
    expect(
      () => AndroidOpenVpnTunnel.requireSafePolicy(
        const VpnPolicy(killSwitchRequested: true)),
      throwsFormatException,
    );
    expect(
      () => AndroidOpenVpnTunnel.requireSafePolicy(
        const VpnPolicy(allowLan: true)),
      throwsFormatException,
    );
  });
}
