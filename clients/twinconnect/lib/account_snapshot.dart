/// Authenticated and non-secret subscription totals from the owning panel.
class AppAccountSnapshot {
  const AppAccountSnapshot({
    required this.namespace,
    required this.trafficLimitBytes,
    required this.trafficUsedBytes,
    required this.expiresAt,
    required this.activationDurationDays,
    required this.status,
  });
  final String namespace;
  final int trafficLimitBytes;
  final int trafficUsedBytes;
  final DateTime? expiresAt;
  final int? activationDurationDays;
  final String status;

  factory AppAccountSnapshot.fromJson(Map<String, dynamic> json) {
    final limit = json['traffic_limit_bytes'];
    final used = json['traffic_used_bytes'];
    final expiry = json['expires_at'];
    final duration = json['activation_duration_days'];
    final namespace = json['namespace'];
    final status = json['status'];
    if (json['schema'] != 1 || namespace is! String ||
        !RegExp(r'^TP[A-Fa-f0-9]{6,16}$').hasMatch(namespace) ||
        limit is! int || limit < 0 ||
        used is! int || used < 0 ||
        (expiry != null && expiry is! String) ||
        (duration != null && (duration is! int || duration < 0)) ||
        status is! String) {
      throw const FormatException('INVALID_ACCOUNT_SNAPSHOT');
    }
    final parsedExpiry = expiry is String ? DateTime.tryParse(expiry) : null;
    if (expiry is String && parsedExpiry == null) {
      throw const FormatException('INVALID_ACCOUNT_EXPIRY');
    }
    return AppAccountSnapshot(
      namespace: namespace.toUpperCase(),
      trafficLimitBytes: limit,
      trafficUsedBytes: used,
      expiresAt: parsedExpiry?.toUtc(),
      activationDurationDays: duration,
      status: status,
    );
  }
}
