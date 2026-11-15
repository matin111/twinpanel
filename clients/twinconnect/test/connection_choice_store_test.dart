import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/connection_choice_store.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('manual Cisco node survives app reopen and is not an index', () async {
    final key = ConnectionChoiceStore.key(
        namespace: 'panelA', apiOrigin: 'https://panel.example',
        username: 'ali');
    const saved = ConnectionChoice(protocolCode: 'cisco', nodeId: 'germany-2');
    await ConnectionChoiceStore.save(key, saved);
    final restored = await ConnectionChoiceStore.load(key);
    expect(restored?.protocolCode, 'cisco');
    expect(restored?.nodeId, 'germany-2');
    final reorderedIds = ['turkey-1', 'germany-2', 'france-3'];
    expect(reorderedIds.indexOf(restored!.nodeId!), 1);
  });

  test('different account, tenant and origin have separate selections',
      () async {
    String key(String user, String ns, String origin) =>
        ConnectionChoiceStore.key(
            namespace: ns, apiOrigin: origin, username: user);
    final a = key('ali', 'panelA', 'https://a.example');
    await ConnectionChoiceStore.save(
        a, const ConnectionChoice(protocolCode: 'openvpn', nodeId: 'de-1'));
    expect((await ConnectionChoiceStore.load(a))?.nodeId, 'de-1');
    expect(await ConnectionChoiceStore.load(
        key('reza', 'panelA', 'https://a.example')), isNull);
    expect(await ConnectionChoiceStore.load(
        key('ali', 'panelB', 'https://a.example')), isNull);
    expect(await ConnectionChoiceStore.load(
        key('ali', 'panelA', 'https://b.example')), isNull);
  });

  test('Xray inbound is kept with the exact manually chosen node',
      () async {
    final key = ConnectionChoiceStore.key(
        namespace: 'n', apiOrigin: 'https://x.example', username: 'u');
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
    expect(() => ConnectionChoice(
        protocolCode: 'cisco', nodeId: '\nunsafe').isValid,
        returnsNormally);
    expect(const ConnectionChoice(
        protocolCode: 'cisco', nodeId: '\nunsafe').isValid, isFalse);
  });
}
