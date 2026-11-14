import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/cisco_openconnect_profile.dart';
import 'package:twinconnect/android_cisco_tunnel.dart';

void main() {
  CiscoOpenConnectProfile profile(String? pin) =>
      CiscoOpenConnectProfile(
        host: 'vpn.example.org', port: 443,
        username: 'user', password: 'not-logged',
        serverCertificate: pin,
      );

  test('Cisco accepts panel-provided SHA-256 cert fingerprint only', () {
    final fingerprint = 'a' * 64;
    expect(AndroidCiscoTunnel.requiredSha256Pin(
        profile('sha256:$fingerprint')), fingerprint);
  });

  test('Cisco accepts panel-provided SHA-256 SPKI pin', () {
    const spki = 'pin-sha256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=';
    expect(AndroidCiscoTunnel.requiredSha256Pin(profile(spki)), spki);
  });

  test('Cisco never sends credentials without a valid pin', () {
    for (final pin in <String?>[
      null, '', 'sha1:${'b' * 40}', 'sha256:garbage',
      'invalid', 'sha256:${'f' * 63}',
    ]) {
      expect(() => AndroidCiscoTunnel.requiredSha256Pin(profile(pin)),
          throwsFormatException);
    }
  });
}
