import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'protocols.dart';

/// A user's *explicit* connection choice, never a Fast Server suggestion.
/// Node IDs (not list indices) survive a changed inventory order. No access
/// token, VPN private key, username/password or tunnel configuration is saved.
class ConnectionChoice {
  const ConnectionChoice({
    required this.protocolCode,
    this.nodeId,
    this.xrayInboundId,
  });

  final String protocolCode;
  final String? nodeId;
  final String? xrayInboundId;

  bool get isValid =>
      (protocolCode == 'all' || VpnProtocols.byCode(protocolCode) != null) &&
      (nodeId == null ||
          (nodeId!.isNotEmpty && nodeId!.length <= 256 &&
              !RegExp(r'[\x00-\x1f\x7f]').hasMatch(nodeId!))) &&
      (xrayInboundId == null ||
          (protocolCode == 'v2ray' &&
              RegExp(r'^[a-zA-Z0-9_-]{1,128}$').hasMatch(xrayInboundId!)));

  Map<String, dynamic> toJson() => <String, dynamic>{
    'protocol': protocolCode,
    'node_id': nodeId,
    'inbound_id': xrayInboundId,
  };

  static ConnectionChoice? decode(String? raw) {
    if (raw == null) return null;
    try {
      final data = jsonDecode(raw);
      if (data is! Map<String, dynamic>) return null;
      if (data['protocol'] is! String ||
          (data['node_id'] != null && data['node_id'] is! String) ||
          (data['inbound_id'] != null && data['inbound_id'] is! String)) {
        return null;
      }
      final choice = ConnectionChoice(
        protocolCode: data['protocol'] as String,
        nodeId: data['node_id'] as String?,
        xrayInboundId: data['inbound_id'] as String?,
      );
      return choice.isValid ? choice : null;
    } catch (_) {
      return null;
    }
  }
}

class ConnectionChoiceStore {
  const ConnectionChoiceStore._();

  static String key({
    required String namespace,
    required String username,
  }) {
    // License/tenant namespace and account are stable when the panel domain
    // rotates. A different panel or username must not inherit this choice.
    final tuple = jsonEncode([namespace, username]);
    return 'twinconnect_manual_connection_v1:${base64UrlEncode(utf8.encode(tuple))}';
  }

  static Future<ConnectionChoice?> load(String accountKey) async {
    final prefs = await SharedPreferences.getInstance();
    return ConnectionChoice.decode(prefs.getString(accountKey));
  }

  static Future<void> save(
      String accountKey, ConnectionChoice choice) async {
    if (!choice.isValid) {
      throw const FormatException('INVALID_CONNECTION_CHOICE');
    }
    final prefs = await SharedPreferences.getInstance();
    if (!await prefs.setString(accountKey, jsonEncode(choice.toJson()))) {
      throw const FormatException('CONNECTION_CHOICE_NOT_SAVED');
    }
  }
}
