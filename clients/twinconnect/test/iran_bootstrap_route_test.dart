import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/iran_bootstrap_route.dart';

void main() {
  test('only the pinned real panel hostname may use domestic bootstrap', () {
    expect(IranBootstrapRoute.supports(
        Uri.parse('https://panel.matindnspro.sbs/v1/app/resolve/TP123456')),
        isTrue);
    expect(IranBootstrapRoute.supports(
        Uri.parse('https://panel.matindnspro.sbs/v1/central-app/session/servers')),
        isTrue);
    for (final url in [
      'http://panel.matindnspro.sbs',
      'https://panel.matindnspro.sbs:8443',
      'https://panel.matindnspro.sbs.attacker.example',
      'https://10.0.0.1',
      'https://otherpanel.example.com',
      'https://someone@panel.matindnspro.sbs',
    ]) {
      expect(IranBootstrapRoute.supports(Uri.parse(url)), isFalse,
          reason: 'should reject $url');
    }
  });

  test('Iran endpoint is a verified public IPv4 and never an untrusted route',
      () {
    expect(IranBootstrapRoute.parsePublicIpv4('94.183.231.158'),
        isA<InternetAddress>());
    for (final address in [
      '127.0.0.1', '10.8.0.1', '192.168.1.7', '172.16.2.1',
      '100.64.3.1', '169.254.5.1', '224.0.0.1', '::1',
      '192.0.2.1', '203.0.113.99', 'example.org',
    ]) {
      expect(IranBootstrapRoute.parsePublicIpv4(address), isNull,
          reason: 'should not route credentials to $address');
    }
    expect(IranBootstrapRoute.targetFor(
        Uri.parse('https://irrelevant.example.org')), isNull);
  });

  test('domestic transport rejects other names and never accepts bad TLS',
      () {
    final ip = InternetAddress('94.183.231.158');
    expect(() => IranBootstrapRoute.clientFor(
        Uri.parse('https://attacker.example.org'), ip),
        throwsFormatException);
    final http = IranBootstrapRoute.clientFor(
        Uri.parse('https://panel.matindnspro.sbs/health'), ip);
    expect(http.badCertificateCallback, isNull);
    http.close(force: true);
  });

  test('only transport failures are retryable, not HTTP denials', () {
    expect(IranBootstrapRoute.isTransient(
        const SocketException('unreachable')), isTrue);
    expect(IranBootstrapRoute.isTransient(
        const HandshakeException('invalid certificate')), isTrue);
    expect(IranBootstrapRoute.isTransient(
        const FormatException('rejected by server')), isFalse);
  });
}
