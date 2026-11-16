/// A paid next period, never part of the currently consumable account quota.
class ReservedRenewalSnapshot {
  const ReservedRenewalSnapshot({
    required this.status,
    required this.planName,
    required this.trafficBytes,
    required this.durationDays,
    required this.reservedAt,
  });

  final String status;
  final String planName;
  final int trafficBytes;
  final int durationDays;
  final DateTime reservedAt;
  bool get needsReview => status == 'needs_review';

  factory ReservedRenewalSnapshot.fromJson(Map<String, dynamic> json) {
    final status = json['status'];
    final plan = json['plan_name'];
    final traffic = json['traffic_bytes'];
    final duration = json['duration_days'];
    final created = json['reserved_at'];
    final parsedDate = created is String ? DateTime.tryParse(created) : null;
    if ((status != 'reserved' && status != 'needs_review') ||
        plan is! String || plan.trim().isEmpty ||
        traffic is! int || traffic < 0 ||
        duration is! int || duration < 0 ||
        parsedDate == null) {
      throw const FormatException('INVALID_RESERVED_RENEWAL');
    }
    return ReservedRenewalSnapshot(
      status: status as String,
      planName: plan.trim(),
      trafficBytes: traffic,
      durationDays: duration,
      reservedAt: parsedDate.toUtc(),
    );
  }
}

/// Authenticated and non-secret subscription totals from the owning panel.
class AppAccountSnapshot {
  const AppAccountSnapshot({
    required this.namespace,
    required this.trafficLimitBytes,
    required this.trafficUsedBytes,
    required this.expiresAt,
    required this.activationDurationDays,
    required this.status,
    this.reservedRenewal,
    this.reservedRenewals = const [],
  });
  final String namespace;
  final int trafficLimitBytes;
  final int trafficUsedBytes;
  final DateTime? expiresAt;
  final int? activationDurationDays;
  final String status;
  final ReservedRenewalSnapshot? reservedRenewal;
  final List<ReservedRenewalSnapshot> reservedRenewals;

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
    ReservedRenewalSnapshot? nextRenewal;
    final next = json['reserved_renewal'];
    if (next is Map<String, dynamic>) {
      try {
        nextRenewal = ReservedRenewalSnapshot.fromJson(next);
      } on FormatException {
        // A malformed optional field must not hide existing quota/expiry.
      }
    }
    // New panels expose every queued item. Older panels expose only the
    // next renewal; never render the same reservation twice.
    final queued = <ReservedRenewalSnapshot>[];
    final rawQueue = json['reserved_renewals'];
    if (rawQueue is List) {
      for (final raw in rawQueue.take(100)) {
        if (raw is! Map<String, dynamic>) continue;
        try {
          queued.add(ReservedRenewalSnapshot.fromJson(raw));
        } on FormatException {
          // Ignore malformed optional entries, preserve valid account data.
        }
      }
    } else if (nextRenewal != null) {
      queued.add(nextRenewal);
    }
    return AppAccountSnapshot(
      namespace: namespace.toUpperCase(),
      trafficLimitBytes: limit,
      trafficUsedBytes: used,
      expiresAt: parsedExpiry?.toUtc(),
      activationDurationDays: duration,
      status: status,
      reservedRenewal: queued.isNotEmpty ? queued.first : nextRenewal,
      reservedRenewals: List.unmodifiable(queued),
    );
  }
}
