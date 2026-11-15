import 'package:flutter/material.dart';

/// ICMP round-trip time to an assigned node, not HTTP request duration
/// or a bandwidth/speed test.
class ServerLatency {
  const ServerLatency._();

  static Color color(int? rttMs) {
    if (rttMs == null || rttMs < 0) return const Color(0xFFABB3CB);
    if (rttMs <= 300) return const Color(0xFF36D9A5);
    if (rttMs <= 700) return const Color(0xFFFFC266);
    return const Color(0xFFFF697A);
  }

  static String label(int? rttMs, {bool approximate = false}) {
    if (rttMs == null || rttMs < 0) return '— ms';
    return '${approximate ? '≈' : ''}$rttMs ms';
  }
}
