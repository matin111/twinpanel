import 'package:flutter_test/flutter_test.dart';

void main() {
  test('DNS detection regex works on Windows Dart/ECMAScript RegExp', () {
    final expression = RegExp(
      r'^dhcp-option\s+DNS\s+',
      caseSensitive: false,
      multiLine: true,
    );
    expect(expression.hasMatch('client\nDHCP-OPTION DNS 1.1.1.1\n'), isTrue);
    expect(expression.hasMatch('client\ndhcp-option dns 8.8.8.8\n'), isTrue);
    expect(expression.hasMatch('client\nremote vpn.example 1194\n'), isFalse);
  });
}
