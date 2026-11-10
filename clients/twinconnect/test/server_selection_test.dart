import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/server_selection.dart';

void main() {
  test('no fake best server without real probes', () {
    expect(BestServerSelection.choose([]), isNull);
    expect(BestServerSelection.choose([
      const ServerProbe(id: 'a', protocol: 'wireguard', latencyMs: null,
          packetLossPercent: null, available: true),
    ]), isNull);
  });

  test('choose healthy low-loss candidate, not just the fastest ping', () {
    final best = BestServerSelection.choose([
      const ServerProbe(id: 'unreachable', protocol: 'v2ray', latencyMs: 5,
          packetLossPercent: 0, available: false),
      const ServerProbe(id: 'lossy', protocol: 'wireguard', latencyMs: 18,
          packetLossPercent: 22, available: true),
      const ServerProbe(id: 'good', protocol: 'openvpn', latencyMs: 46,
          packetLossPercent: 0.5, jitterMs: 7, available: true),
      const ServerProbe(id: 'no-metrics', protocol: 'cisco', latencyMs: null,
          packetLossPercent: null, available: true),
    ]);
    expect(best?.id, 'good');
  });

  test('stable tie-breaking prevents refresh oscillation', () {
    final result = BestServerSelection.choose([
      const ServerProbe(id: 'server-b', protocol: 'openvpn', latencyMs: 40,
          packetLossPercent: 0, available: true),
      const ServerProbe(id: 'server-a', protocol: 'openvpn', latencyMs: 40,
          packetLossPercent: 0, available: true),
    ]);
    expect(result?.id, 'server-a');
  });
}
