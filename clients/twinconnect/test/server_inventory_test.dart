import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/server_inventory.dart';

void main() {
  test('server inventory accepts only subscription-scoped metadata', () {
    final list = AppServerInventory.fromJson({
      'schema': 1,
      'namespace': 'TP123456',
      'servers': [
        {
          'id': '2', 'name': 'Germany',
          'country_code': 'DE', 'node_online': true, 'latency_ms': null,
        },
      ],
    });
    expect(list.namespace, 'TP123456');
    expect(list.servers.single.id, '2');
    expect(list.servers.single.latencyMs, isNull);
  });

  test('rejects duplicate or invented latency', () {
    const row = {
      'id': '2', 'name': 'Germany', 'country_code': 'DE',
      'node_online': true, 'latency_ms': null,
    };
    expect(() => AppServerInventory.fromJson({
      'schema': 1, 'namespace': 'TP123456', 'servers': [row, row],
    }), throwsFormatException);
    expect(() => AppServer.fromJson({
      ...row, 'latency_ms': -1,
    }), throwsFormatException);
  });
}
