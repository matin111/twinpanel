import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/plan_classification.dart';

void main() {
  test('reads both panel categories without guessing from plan names', () {
    final row = AppPlanClassification.fromJson({
      'schema': 1,
      'namespace': 'TPABCDEF',
      'plan_id': 42,
      'subscription_type': 'ویژه',
      'user_count_category': '۲ کاربره',
      'device_limit': 2,
    });
    expect(row.subscriptionType, 'ویژه');
    expect(row.userCountCategory, '۲ کاربره');
    expect(row.deviceLimit, 2);
    expect(row.planId, 42);
  });

  test('does not substitute user count category with device limit', () {
    final row = AppPlanClassification.fromJson({
      'schema': 1,
      'namespace': 'TPABCDEF',
      'plan_id': 43,
      'subscription_type': 'ویتوری',
      'user_count_category': '۴ کاربره',
      'device_limit': 1,
    });
    expect(row.userCountCategory, '۴ کاربره');
    expect(row.deviceLimit, 1);
  });

  test('legacy unassigned plan is accepted without inventing device capacity', () {
    final row = AppPlanClassification.fromJson({
      'schema': 1,
      'namespace': 'TP934FE9',
      'plan_id': 0,
      'subscription_type': 'اشتراک عمومی',
      'user_count_category': 'سایر پلن‌ها',
      'device_limit': 0,
    });
    expect(row.planId, 0);
    expect(row.hasAssignedPlan, isFalse);
    expect(row.deviceLimit, 0);
    expect(row.userCountCategory, 'سایر پلن‌ها');
  });

  test('vitory category limits app filters to V2Ray and Hysteria2', () {
    final plan = AppPlanClassification.fromJson({
      'schema': 1,
      'namespace': 'TPABCDEF',
      'plan_id': 22,
      'subscription_type': 'اشتراک ویتوری',
      'user_count_category': 'یک کاربره',
      'device_limit': 1,
    });
    expect(plan.permitsProtocol('v2ray'), isTrue);
    expect(plan.permitsProtocol('hysteria2'), isTrue);
    for (final other in ['cisco', 'wireguard', 'openvpn', 'tuic', 'socks5']) {
      expect(plan.permitsProtocol(other), isFalse);
    }
  });

  test('special category follows live plan catalogue instead of hardcoded limit', () {
    final plan = AppPlanClassification.fromJson({
      'schema': 1,
      'namespace': 'TPABCDEF',
      'plan_id': 23,
      'subscription_type': 'ویژه',
      'user_count_category': 'دو کاربره',
      'device_limit': 2,
    });
    expect(plan.permitsProtocol('cisco'), isTrue);
    expect(plan.permitsProtocol('hysteria2'), isTrue);
  });

  test('plan protocol whitelist comes from the panel, not all native engines', () {
    final special = AppPlanClassification.fromJson({
      'schema': 1,
      'namespace': 'TPABCDEF',
      'plan_id': 101,
      'subscription_type': 'ویژه',
      'user_count_category': 'دو کاربره',
      'device_limit': 2,
      'allowed_protocols': ['cisco', 'v2ray', 'hysteria2'],
    });
    expect(special.permitsProtocol('cisco'), isTrue);
    expect(special.permitsProtocol('wireguard'), isFalse);
    final vitory = AppPlanClassification.fromJson({
      'schema': 1,
      'namespace': 'TPABCDEF',
      'plan_id': 102,
      'subscription_type': 'ویتوری',
      'user_count_category': 'یک کاربره',
      'device_limit': 1,
      'allowed_protocols': ['v2ray', 'hysteria2', 'cisco'],
    });
    expect(vitory.permitsProtocol('v2ray'), isTrue);
    expect(vitory.permitsProtocol('hysteria2'), isTrue);
    expect(vitory.permitsProtocol('cisco'), isFalse);
  });

  test('invalid panel protocol lists cannot expand account entitlement', () {
    expect(() => AppPlanClassification.fromJson({
      'schema': 1,
      'namespace': 'TPABCDEF',
      'plan_id': 3,
      'subscription_type': 'ویژه',
      'user_count_category': 'دو کاربره',
      'device_limit': 2,
      'allowed_protocols': ['not-a-real-protocol'],
    }), throwsFormatException);
  });

  test('rejects negative plan IDs', () {
    expect(() => AppPlanClassification.fromJson({
      'schema': 1,
      'namespace': 'TPABCDEF',
      'plan_id': -2,
      'subscription_type': 'ویژه',
      'user_count_category': '۲ کاربره',
      'device_limit': 2,
    }), throwsFormatException);
  });

  test('rejects malformed classifications', () {
    expect(() => AppPlanClassification.fromJson({
      'schema': 1, 'namespace': 'TPABCDEF', 'plan_id': 1,
      'subscription_type': '', 'user_count_category': '۲ کاربره',
      'device_limit': 2,
    }), throwsFormatException);
  });
}
