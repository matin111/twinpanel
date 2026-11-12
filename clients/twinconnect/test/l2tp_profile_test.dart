import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/l2tp_profile.dart';

void main() {
  test('uses panel-issued L2TP PSK without modifying existing credentials', () {
    final profile = L2tpProfile.fromItem({
      'node_id': 28, 'server': 'vpn.example.org',
      'username': 'user1', 'password': 'private', 'psk': 'server-secret',
    });
    expect(profile.nodeId, 28);
    expect(profile.server, 'vpn.example.org');
    expect(profile.psk, 'server-secret');
  });

  test('rejects missing PSK or credential injection', () {
    expect(() => L2tpProfile.fromItem({
      'node_id': 28, 'server': 'vpn.example.org',
      'username': 'user1', 'password': 'private',
    }), throwsFormatException);
    expect(() => L2tpProfile.fromItem({
      'node_id': 28, 'server': 'vpn.example.org',
      'username': 'user1\nbad', 'password': 'private', 'psk': 'psk',
    }), throwsFormatException);
  });

  test('rejects invalid endpoints and missing node identity', () {
    expect(() => L2tpProfile.fromItem({
      'node_id': 0, 'server': 'vpn.example.org',
      'username': 'user1', 'password': 'pass', 'psk': 'psk',
    }), throwsFormatException);
    expect(() => L2tpProfile.fromItem({
      'node_id': 2, 'server': 'host/path',
      'username': 'user1', 'password': 'pass', 'psk': 'psk',
    }), throwsFormatException);
  });
}
