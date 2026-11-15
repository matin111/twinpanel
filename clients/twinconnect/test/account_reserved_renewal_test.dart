import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/account_snapshot.dart';

Map<String, dynamic> accountJson([Map<String, dynamic>? reserved]) => {
  'schema': 1,
  'namespace': 'TP0123456789ABCDEF',
  'traffic_limit_bytes': 10737418240,
  'traffic_used_bytes': 3221225472,
  'expires_at': '2026-12-15T12:00:00Z',
  'activation_duration_days': 30,
  'status': 'active',
  'reserved_renewal': reserved,
};

void main() {
  test('shows next reserved period without changing current account totals', () {
    final original = AppAccountSnapshot.fromJson(accountJson());
    final withRenewal = AppAccountSnapshot.fromJson(accountJson({
      'status': 'reserved',
      'plan_name': 'Premium',
      'traffic_bytes': 26843545600,
      'traffic_gb': 25.0,
      'duration_days': 45,
      'reserved_at': '2026-11-15T05:15:00Z',
    }));
    expect(original.reservedRenewal, isNull);
    expect(withRenewal.trafficLimitBytes, original.trafficLimitBytes);
    expect(withRenewal.trafficUsedBytes, original.trafficUsedBytes);
    expect(withRenewal.expiresAt, original.expiresAt);
    expect(withRenewal.reservedRenewal!.planName, 'Premium');
    expect(withRenewal.reservedRenewal!.trafficBytes, 26843545600);
    expect(withRenewal.reservedRenewal!.durationDays, 45);
    expect(withRenewal.reservedRenewal!.needsReview, false);
  });

  test('blocked renewal remains separate and is visibly flagged', () {
    final withRenewal = AppAccountSnapshot.fromJson(accountJson({
      'status': 'needs_review',
      'plan_name': 'V2Ray',
      'traffic_bytes': 10737418240,
      'duration_days': 30,
      'reserved_at': '2026-11-15T05:15:00Z',
    }));
    expect(withRenewal.reservedRenewal!.needsReview, true);
  });

  test('invalid optional renewal does not hide valid active account', () {
    final account = AppAccountSnapshot.fromJson(accountJson({
      'status': 'reserved',
      'plan_name': 'Invalid',
      'traffic_bytes': -9,
      'duration_days': 30,
      'reserved_at': 'bad-date',
    }));
    expect(account.reservedRenewal, isNull);
    expect(account.trafficLimitBytes, 10737418240);
  });
}
