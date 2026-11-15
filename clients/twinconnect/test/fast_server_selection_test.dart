import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/fast_server_selection.dart';
import 'package:twinconnect/server_inventory.dart';

void main() {
  const nodes = [
    AppServer(id: '1', name: 'DE', countryCode: 'DE',
        nodeOnline: true, latencyMs: 9, probeIp: '198.51.100.1'),
    AppServer(id: '2', name: 'TR', countryCode: 'TR',
        nodeOnline: true, latencyMs: 90, probeIp: '198.51.100.2'),
    AppServer(id: '3', name: 'US', countryCode: 'US',
        nodeOnline: false, latencyMs: 1, probeIp: '198.51.100.3'),
  ];
  test('fastest respects authorized nodes for each individual protocol', () {
    final rtts = {'1': 5, '2': 48, '3': 1};
    expect(FastServerSelection.choose(
      servers: nodes,
      permittedNodeIds: {'2'},
      measuredRtts: rtts), 1);
    expect(FastServerSelection.choose(
      servers: nodes,
      permittedNodeIds: {'1'},
      measuredRtts: rtts), 0);
  });

  test('offline, unmeasured and unauthorized nodes never win', () {
    expect(FastServerSelection.choose(
      servers: nodes,
      permittedNodeIds: {'3'},
      measuredRtts: {'3': 1}), isNull);
    expect(FastServerSelection.choose(
      servers: nodes,
      permittedNodeIds: {'2'},
      measuredRtts: {'1': 5}), isNull);
    expect(FastServerSelection.choose(
      servers: nodes,
      permittedNodeIds: {'1', '2'},
      measuredRtts: {'1': 0, '2': 90}), 1);
  });

  test('panel latency hints cannot substitute for client measurements', () {
    expect(FastServerSelection.choose(
      servers: nodes,
      permittedNodeIds: {'1', '2'},
      measuredRtts: {}), isNull);
  });
}
