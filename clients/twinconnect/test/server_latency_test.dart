import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/server_latency.dart';

void main() {
  test('ping colors: green through 300, yellow through 700, red above', () {
    expect(ServerLatency.color(0), ServerLatency.color(300));
    expect(ServerLatency.color(301), ServerLatency.color(700));
    expect(ServerLatency.color(701), ServerLatency.color(1500));
    expect(ServerLatency.color(300), isNot(ServerLatency.color(301)));
    expect(ServerLatency.color(700), isNot(ServerLatency.color(701)));
    expect(ServerLatency.color(null), isNot(ServerLatency.color(100)));
  });

  test('unknown ping is never displayed as successful', () {
    expect(ServerLatency.label(null), '— ms');
    expect(ServerLatency.label(-1), '— ms');
    expect(ServerLatency.label(250), '250 ms');
    expect(ServerLatency.label(250, approximate: true), '≈250 ms');
  });
}
