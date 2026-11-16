import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/windows_public_ip_probe.dart';

void main() {
  test('parses primary JSON IPv4 and fallback plain text IPv4', () {
    expect(WindowsPublicIpProbe.parseResponse('{"ip":"203.0.113.10"}'),
        '203.0.113.10');
    expect(WindowsPublicIpProbe.parseResponse('203.0.113.11\n'),
        '203.0.113.11');
  });

  test('accepts IPv6 and rejects malformed or non-IP body', () {
    expect(WindowsPublicIpProbe.parseResponse('2001:db8::1'),
        '2001:db8::1');
    expect(WindowsPublicIpProbe.parseResponse('<html>error</html>'), isNull);
    expect(WindowsPublicIpProbe.parseResponse('{"ip":"broken"}'), isNull);
    expect(WindowsPublicIpProbe.parseResponse('{"ip":123}'), isNull);
    expect(WindowsPublicIpProbe.parseResponse('{"ip":"127.0.0.1"}'), isNull);
    expect(WindowsPublicIpProbe.parseResponse('{"ip":"224.0.0.1"}'), isNull);
    expect(WindowsPublicIpProbe.parseResponse('{"ip":"fe80::1"}'), isNull);
  });
}
