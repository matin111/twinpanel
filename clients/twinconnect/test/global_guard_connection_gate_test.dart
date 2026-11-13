import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/global_guard_connection_gate.dart';
import 'package:twinconnect/vpn_policy.dart';

void main() {
  const requiredPolicy = VpnPolicy(killSwitchRequested: true);
  const normalPolicy = VpnPolicy();
  const verifiedStatus = <String, dynamic>{
    'contractVersion': 1,
    'serviceInstalled': true,
    'armed': true,
    'enforcedV4': true,
    'enforcedV6': true,
    'recoveryVerified': true,
  };

  test('Kill Switch disabled does not change existing connections', () {
    expect(() => GlobalGuardConnectionGate.ensureCanConnect(
      normalPolicy, const <String, dynamic>{}), returnsNormally);
  });

  test('Kill Switch requested rejects absent or incomplete service', () {
    expect(() => GlobalGuardConnectionGate.ensureCanConnect(
      requiredPolicy, const <String, dynamic>{}), throwsFormatException);
    for (final name in verifiedStatus.keys) {
      final broken = Map<String, dynamic>.from(verifiedStatus);
      broken[name] = name == 'contractVersion' ? 0 : false;
      expect(() => GlobalGuardConnectionGate.ensureCanConnect(
        requiredPolicy, broken), throwsFormatException,
        reason: 'Missing $name must fail closed.');
    }
  });

  test('Only complete verified native acknowledgement can pass gate', () {
    expect(GlobalGuardConnectionGate.verified(verifiedStatus), isTrue);
    expect(() => GlobalGuardConnectionGate.ensureCanConnect(
      requiredPolicy, verifiedStatus), returnsNormally);
  });

  test('all native protocol entry points check guard before handoff', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final names = <String>[
      '_startCiscoTunnel',
      '_startOpenVpnTunnel',
      '_startL2tpTunnel',
      '_startXrayTunnel',
      '_startSudokuTunnel',
      '_startAmneziaWgTunnel',
      '_startMieruTunnel',
      '_startTrustTunnel',
      '_startModernTunnel',
    ];
    for (final name in names) {
      final start = dashboard.indexOf('Future<void> $name(');
      expect(start, greaterThanOrEqualTo(0), reason: 'Missing $name');
      final segment = dashboard.substring(start, start + 520);
      expect(segment, contains('await _requireVerifiedGuardIfRequested();'),
          reason: '$name must fail closed before its first native action');
    }
    final wireguard = dashboard.indexOf(
        'Validate the target and obtain only its authorized profile BEFORE');
    expect(wireguard, greaterThanOrEqualTo(0));
    expect(dashboard.substring(wireguard, wireguard + 400),
        contains('await _requireVerifiedGuardIfRequested();'));
  });
}
