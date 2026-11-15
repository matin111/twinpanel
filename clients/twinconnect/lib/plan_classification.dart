/// Read-only classification from the app subscription's panel.
/// Legacy subscriptions can be unassigned (planId = 0).
/// Type and user-count group are independent admin-managed panel dimensions.
class AppPlanClassification {
  const AppPlanClassification({
    required this.namespace,
    required this.planId,
    required this.subscriptionType,
    required this.userCountCategory,
    required this.deviceLimit,
    this.allowedProtocolCodes,
  });

  final String namespace;
  /// 0 means historical subscription without a plan; not a real plan id.
  final int planId;
  bool get hasAssignedPlan => planId > 0;

  final String subscriptionType;
  final String userCountCategory;
  final int deviceLimit;
  /// Null means a legacy panel did not provide an explicit whitelist.
  final Set<String>? allowedProtocolCodes;

  /// Commercial type comes from /session/plan, never a guessed plan title.
  /// Explicit protocol flags in the session catalogue are checked separately.
  bool permitsProtocol(String code) {
    final kind = subscriptionType.trim().toLowerCase();
    final vitory = kind.contains('ویتوری') ||
        kind.contains('vitory') || kind.contains('v2ray');
    if (vitory && code != 'v2ray' && code != 'hysteria2') return false;
    return allowedProtocolCodes?.contains(code) ?? true;
  }

  factory AppPlanClassification.fromJson(Map<String, dynamic> json) {
    final namespace = json['namespace'];
    final planId = json['plan_id'];
    final type = json['subscription_type'];
    final group = json['user_count_category'];
    final limit = json['device_limit'];
    final rawAllowed = json['allowed_protocols'];
    if (rawAllowed != null &&
        (rawAllowed is! List ||
         rawAllowed.length > 16 ||
         rawAllowed.any((x) => x is! String ||
             !const {
               'cisco', 'openvpn', 'wireguard', 'l2tp', 'v2ray',
               'hysteria2', 'tuic', 'anytls', 'naive', 'shadowtls',
               'snell', 'socks5', 'mieru', 'trusttunnel',
               'amneziawg', 'sudoku',
             }.contains(x)))) {
      throw const FormatException('INVALID_PLAN_PROTOCOLS');
    }
    if (json['schema'] != 1 ||
        namespace is! String ||
        !RegExp(r'^TP[A-Fa-f0-9]{6,16}$').hasMatch(namespace) ||
        planId is! int || planId < 0 ||
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
      allowedProtocolCodes: rawAllowed == null
          ? null : Set.unmodifiable((rawAllowed as List).cast<String>()),
    );
  }
}
