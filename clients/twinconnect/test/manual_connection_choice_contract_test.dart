import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  final source = File('lib/live_dashboard.dart').readAsStringSync()
      .replaceAll('\r\n', '\n');

  test('explicit server choice is persisted before engine availability gates',
      () {
    final start = source.indexOf('Future<void> _selectServerAndConnect(');
    final end = source.indexOf('final targetId = nodes[index].id;', start);
    expect(start, greaterThan(0));
    expect(end, greaterThan(start));
    final method = source.substring(start, end);
    expect(method, contains('_explicitNodeId = nodes[index].id;'));
    expect(method, contains('_persistManualConnectionChoice();'));
    expect(method, contains('if (!Platform.isWindows)'));
  });

  test('only manual protocol/inbound taps persist, not Fast Server', () {
    final chooser = source.substring(
        source.indexOf('Future<void> _enableFastestAndConnect()'),
        source.indexOf('void _resetNetworkStats()'));
    expect(chooser, isNot(contains('_persistManualConnectionChoice();')));
    expect(chooser, contains('_filter = previousFilter;'));
    expect(chooser, contains('_selected = previousSelected;'));
    expect(chooser, contains('_choiceRevision != manualRevision'));

    final protocolChoice = source.substring(
        source.indexOf(r"key: Key('devFilter_${entry.$1}')"),
        source.indexOf('Widget locations()'));
    expect(protocolChoice, contains('_persistManualConnectionChoice();'));

    final inbound = source.substring(
        source.indexOf('key: Key(\'connectXray_'));
    expect(inbound, contains('_explicitXrayInboundId = inbound.id;'));
    expect(inbound, contains('_persistManualConnectionChoice();'));
  });

  test('saved ID is remapped on inventory reorder without choosing a replacement',
      () {
    expect(source, contains('_alignSelectedNodeWithInventory();'));
    expect(source, contains(
        '_selected = nodes.indexWhere((node) => node.id == _explicitNodeId);'));
    expect(source, contains(
        'nodes.indexWhere((node) => node.id == restored.nodeId)'));
    expect(source, contains('++_choiceRevision;'));
    expect(source, contains('_choiceAccountKey != account'));
    expect(source, contains('unawaited(_restoreManualConnectionChoice());'));
  });

  test('ordinary connect never mutates manual protocol or stored node', () {
    final toggle = source.substring(
        source.indexOf('Future<void> _toggleVpn() async'),
        source.indexOf('String _languageCode ='));
    expect(toggle, contains('String? targetId = _selectedServerId;'));
    expect(toggle, contains('String? selectedId = _selectedServerId;'));
    expect(toggle, isNot(contains('setState(() => _selected = best)')));
    expect(toggle, isNot(contains("_filter = 'wireguard';")));
    expect(toggle, isNot(contains('_persistManualConnectionChoice();')));
  });
}
