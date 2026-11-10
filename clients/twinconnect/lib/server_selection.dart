/// Safe selection: use only real measured metrics from an authorized panel's
/// server inventory. No latency estimate, sample fixture or saved policy can
/// assert that a connection has been established.
class ServerProbe {
  const ServerProbe({
    required this.id,
    required this.protocol,
    required this.latencyMs,
    required this.packetLossPercent,
    required this.available,
    this.jitterMs = 0,
  });

  final String id;
  final String protocol;
  final int? latencyMs;
  final double? packetLossPercent;
  final bool available;
  final int jitterMs;
}

class BestServerSelection {
  const BestServerSelection._();

  /// Choose among actual healthy probes. Unknown ping/loss never wins.
  /// A tied score is stable by ID and protocol so refreshes do not oscillate.
  static ServerProbe? choose(Iterable<ServerProbe> probes) {
    final candidates = probes.where((p) =>
        p.id.isNotEmpty &&
        p.protocol.isNotEmpty &&
        p.available &&
        p.latencyMs != null &&
        p.latencyMs! > 0 &&
        p.packetLossPercent != null &&
        p.packetLossPercent! >= 0 &&
        p.packetLossPercent! <= 100 &&
        p.jitterMs >= 0 &&
        p.packetLossPercent! < 100).toList();
    if (candidates.isEmpty) return null;
    double score(ServerProbe p) =>
        p.latencyMs! + p.jitterMs * 0.75 +
        p.packetLossPercent! * 20;
    candidates.sort((a, b) {
      final compare = score(a).compareTo(score(b));
      if (compare != 0) return compare;
      final id = a.id.compareTo(b.id);
      return id == 0 ? a.protocol.compareTo(b.protocol) : id;
    });
    return candidates.first;
  }
}
