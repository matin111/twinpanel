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
    expect(AndroidCiscoTunnel.validatedServerTrust(
        profile('sha256:$fingerprint')), fingerprint);
  });

  test('Cisco accepts panel-provided SHA-256 SPKI pin', () {
    const spki = 'pin-sha256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=';
    expect(AndroidCiscoTunnel.validatedServerTrust(profile(spki)), spki);
  });

  test('Cisco uses platform CA and TLS hostname validation with no pin', () {
    expect(AndroidCiscoTunnel.validatedServerTrust(profile(null)), '');
    expect(AndroidCiscoTunnel.validatedServerTrust(profile('')), '');
  });

  test('Cisco rejects malformed explicit certificate pins', () {
    for (final pin in <String?>[
      'sha1:${'b' * 40}', 'sha256:garbage',
      'invalid', 'sha256:${'f' * 63}',
    ]) {
      expect(() => AndroidCiscoTunnel.validatedServerTrust(profile(pin)),
          throwsFormatException);
    }
  });
}
