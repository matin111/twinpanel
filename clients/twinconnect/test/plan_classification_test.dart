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
