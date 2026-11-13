import 'dart:async';
import 'dart:io';

import 'xray_inbound_profiles.dart';

/// TCP handshake latency to the EXACT Xray inbound endpoint and port.
/// Unlike an ICMP node ping, it tests that specific inbound's listener.
/// A reachable TCP port is not proof that TLS/REALITY/VLESS auth will work.
/// No credentials, HTTP requests or payloads are sent.
class XrayInboundLatency {
  const XrayInboundLatency._();

  static String key(XrayInboundProfile profile) =>
      '${profile.serverId}:${profile.id}';

  static Future<int?> probe(
    XrayInboundProfile profile, {
    Duration timeout = const Duration(milliseconds: 1800),
  }) async {
    if (!Platform.isWindows || profile.uri.port <= 0) return null;
    final clock = Stopwatch()..start();
    Socket? socket;
    try {
      socket = await Socket.connect(
        profile.uri.host,
        profile.uri.port,
        timeout: timeout,
      );
      clock.stop();
      return clock.elapsedMilliseconds.clamp(1, 60000).toInt();
    } on SocketException {
      return null;
    } on TimeoutException {
      return null;
    } catch (_) {
      return null;
    } finally {
      socket?.destroy();
    }
  }
}
