import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/connection_choice_store.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('manual Cisco node survives app reopen and is not an index', () async {
    final key = ConnectionChoiceStore.key(
        namespace: 'panelA', username: 'ali');
    const saved = ConnectionChoice(protocolCode: 'cisco', nodeId: 'germany-2');
    await ConnectionChoiceStore.save(key, saved);
    final restored = await ConnectionChoiceStore.load(key);
    expect(restored?.protocolCode, 'cisco');
    expect(restored?.nodeId, 'germany-2');
    final reorderedIds = ['turkey-1', 'germany-2', 'france-3'];
    expect(reorderedIds.indexOf(restored!.nodeId!), 1);
  });

  test('accounts and tenants are isolated even when domains rotate',
      () async {
    String key(String user, String ns) =>
        ConnectionChoiceStore.key(namespace: ns, username: user);
    final a = key('ali', 'panelA');
    await ConnectionChoiceStore.save(
        a, const ConnectionChoice(protocolCode: 'openvpn', nodeId: 'de-1'));
    expect((await ConnectionChoiceStore.load(a))?.nodeId, 'de-1');
    expect(await ConnectionChoiceStore.load(
        key('reza', 'panelA')), isNull);
    expect(await ConnectionChoiceStore.load(
        key('ali', 'panelB')), isNull);
    // Changing an external domain does not alter the stable tenant key.
    expect(key('ali', 'panelA'), a);
  });

  test('Xray inbound is kept with the exact manually chosen node',
      () async {
    final key = ConnectionChoiceStore.key(
        namespace: 'n', username: 'u');
    await ConnectionChoiceStore.save(
        key, const ConnectionChoice(
            protocolCode: 'v2ray', nodeId: 'node-19',
            xrayInboundId: 'websocket_tls'));
    final restored = await ConnectionChoiceStore.load(key);
    expect(restored?.nodeId, 'node-19');
    expect(restored?.xrayInboundId, 'websocket_tls');
  });

  test('invalid or corrupted preferences never choose a random protocol',
      () async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('broken', '{not-json');
    expect(await ConnectionChoiceStore.load('broken'), isNull);
    await prefs.setString('broken', jsonEncode({
      'protocol': 'rogue', 'node_id': 'x',
    }));
    expect(await ConnectionChoiceStore.load('broken'), isNull);
    expect(const ConnectionChoice(
        protocolCode: 'cisco', nodeId: '\nunsafe').isValid, isFalse);
  });
}
