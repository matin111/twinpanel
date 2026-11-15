import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/openvpn_profile_validator.dart';

String profile({String extra = '', String remote = 'vpn.example.org 1194'}) => '''
client
dev tun
proto udp
remote $remote
redirect-gateway def1
tun-mtu 1200
mssfix 1160
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
verb 3
data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305
auth SHA256
$extra
<ca>
CA-CERT
</ca>
<cert>
USER-CERT
</cert>
<key>
SECRET-PRIVATE-KEY
</key>
''';

void main() {
  test('accepts panel-issued inline OpenVPN config', () {
    final source = profile();
    expect(OpenVpnProfileValidator.validate({'config': source}), source);
  });

  test('rejects external scripts and arbitrary OpenVPN directives', () {
    for (final injected in ['script-security 2', 'up malicious.bat',
      'plugin dangerous.dll', 'config other.ovpn', 'management 0.0.0.0 1234']) {
      expect(() => OpenVpnProfileValidator.validate({
        'config': profile(extra: injected),
      }), throwsFormatException);
    }
  });

  test('rejects remote with embedded options or control tokens', () {
    expect(() => OpenVpnProfileValidator.validate({
      'config': profile(remote: 'vpn.example.org 1194 --up'),
    }), throwsFormatException);
  });

  test('rejects missing client inline private key without leaking data', () {
    final broken = profile().replaceAll('<key>', '<keyfile>');
    expect(() => OpenVpnProfileValidator.validate({'config': broken}),
        throwsFormatException);
  });
}
