import 'server_inventory.dart';

/// Select the fastest *measured* node from the exact authenticated
/// subscription/protocol scope. A node with no profile, a stale panel hint,
/// an offline status or a failed ICMP probe can never win.
class FastServerSelection {
  const FastServerSelection._();

  static int? choose({
    required List<AppServer> servers,
    required Set<String> permittedNodeIds,
    required Map<String, int?> measuredRtts,
  }) {
    int? best;
    int? bestRtt;
    for (var i = 0; i < servers.length; i++) {
      final node = servers[i];
      if (!node.nodeOnline || !permittedNodeIds.contains(node.id)) continue;
      final rtt = measuredRtts[node.id];
      if (rtt == null || rtt <= 0 || rtt > 60000) continue;
      if (best == null || rtt < bestRtt! ||
          (rtt == bestRtt && node.id.compareTo(servers[best].id) < 0)) {
        best = i;
        bestRtt = rtt;
      }
    }
    return best;
  }

  /// Fallback only when no client-side ICMP measurements are available.
  /// This is the panel's *reported estimate*, NOT the user's actual ping
  /// and certainly not a throughput benchmark. Keep it separate from
  /// [choose] so a panel hint can never override live client RTT.
  static int? chooseReportedEstimate({
    required List<AppServer> servers,
    required Set<String> permittedNodeIds,
  }) {
    int? best;
    int? bestLatency;
    for (var i = 0; i < servers.length; i++) {
      final node = servers[i];
      if (!node.nodeOnline || !permittedNodeIds.contains(node.id)) continue;
      final reported = node.latencyMs;
      if (reported == null || reported <= 0 || reported > 60000) continue;
      if (best == null || reported < bestLatency! ||
          (reported == bestLatency &&
              node.id.compareTo(servers[best].id) < 0)) {
        best = i;
        bestLatency = reported;
      }
    }
    return best;
  }
}
