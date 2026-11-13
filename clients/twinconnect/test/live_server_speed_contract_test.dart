import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('server speed badges reflect only active native tunnel counters', () {
    final source = File('lib/live_dashboard.dart').readAsStringSync();
    expect(source, contains("Key('activeServerDownload_\$nodeId')"));
    expect(source, contains("Key('activeServerUpload_\$nodeId')"));
    expect(source, contains('if (activeHere) ...['));
    expect(source, contains('_modernProtocol == _filter'));
    expect(source, contains('_activeNodeId == nodeId'));
    expect(source, contains('_recordTraffic(\'modern:\$activeProtocol\', rx, tx)'));
  });

  test('existing low-cost counter polling reports zero-rate intervals', () {
    final source = File('lib/live_dashboard.dart').readAsStringSync();
    expect(source, contains('const Duration(seconds: 2), (_) => _refreshModernTraffic()'));
    expect(source, contains('_rxBytesPerSecond = rxRate'));
    expect(source, contains('_txBytesPerSecond = txRate'));
    expect(source, contains("_recordTraffic('wireguard', nextRx, nextTx)"));
    expect(source, isNot(contains('speedtest-cli')));
  });
}
