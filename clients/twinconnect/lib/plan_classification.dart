/// Read-only classification from the exact plan linked to an app subscription.
/// Type and user-count group are independent admin-managed panel dimensions.
class AppPlanClassification {
  const AppPlanClassification({
    required this.namespace,
    required this.planId,
    required this.subscriptionType,
    required this.userCountCategory,
    required this.deviceLimit,
  });

  final String namespace;
  final int planId;
  final String subscriptionType;
  final String userCountCategory;
  final int deviceLimit;

  factory AppPlanClassification.fromJson(Map<String, dynamic> json) {
    final namespace = json['namespace'];
    final planId = json['plan_id'];
    final type = json['subscription_type'];
    final group = json['user_count_category'];
    final limit = json['device_limit'];
    if (json['schema'] != 1 ||
        namespace is! String ||
        !RegExp(r'^TP[A-Fa-f0-9]{6,16}$').hasMatch(namespace) ||
        planId is! int || planId <= 0 ||
        type is! String || type.trim().isEmpty || type.length > 120 ||
        group is! String || group.trim().isEmpty || group.length > 120 ||
        limit is! int || limit < 0) {
      throw const FormatException('INVALID_PLAN_CLASSIFICATION');
    }
    return AppPlanClassification(
      namespace: namespace.toUpperCase(),
      planId: planId,
      subscriptionType: type.trim(),
      userCountCategory: group.trim(),
      deviceLimit: limit,
    );
  }
}
