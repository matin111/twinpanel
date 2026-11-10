import 'dart:convert';

import 'protocols.dart';

/// The sing-box family uses one engine process. Profiles may be native
/// outbound JSON or a full native config; opaque links are deliberately not
/// converted without a protocol-specific, verified parser.
///
/// Validating a candidate NEVER implies that a native Windows TUN engine is
/// installed, started or connected.
class SingBoxProfileValidator {
  static const Set<String> familyCodes = {
    'hysteria2', 'tuic', 'anytls', 'naive',
    'shadowtls', 'snell', 'socks5',
  };

  static const Map<String, String> outboundTypes = {
    'hysteria2': 'hysteria2',
    'tuic': 'tuic',
    'anytls': 'anytls',
    'naive': 'naive',
    'shadowtls': 'shadowtls',
    'snell': 'snell',
    'socks5': 'socks',
  };

  static bool supportsFamily(String protocolCode) =>
      familyCodes.contains(protocolCode);

  /// Only JSON-native outbounds are accepted. No credentials or entire
  /// serialized payloads appear in thrown exceptions.
  static Map<String, dynamic> validateOutbound({
    required String protocolCode,
    required Map<String, dynamic> item,
  }) {
    final expected = outboundTypes[protocolCode];
    if (expected == null) {
      throw const FormatException('NOT_SINGBOX_PROTOCOL');
    }
    dynamic candidate = item['outbound'];
    if (candidate == null) candidate = item['singbox_outbound'];
    if (candidate == null) candidate = item['config'];
    if (candidate is String) {
      if (candidate.length > 131072) {
        throw const FormatException('SINGBOX_CONFIG_TOO_LARGE');
      }
      try {
        candidate = jsonDecode(candidate);
      } on FormatException {
        throw const FormatException('SINGBOX_CONFIG_INVALID');
      }
    }
    if (candidate is! Map) {
      throw const FormatException('SINGBOX_JSON_PROFILE_REQUIRED');
    }
    final object = Map<String, dynamic>.from(candidate);
    if (object.containsKey('inbounds') || object.containsKey('route') ||
        object.containsKey('experimental') || object.containsKey('log')) {
      // Never let a subscription profile override local routing/security.
      throw const FormatException('SINGBOX_UNTRUSTED_APP_CONFIG');
    }
    if (object['type'] != expected) {
      throw const FormatException('SINGBOX_PROTOCOL_MISMATCH');
    }
    final server = object['server'];
    final port = object['server_port'];
    if (server is! String || server.isEmpty || server.length > 255 ||
        server.contains('/') || server.contains(' ') ||
        port is! int || port < 1 || port > 65535) {
      throw const FormatException('SINGBOX_ENDPOINT_INVALID');
    }
    if ((protocolCode == 'hysteria2' || protocolCode == 'tuic' ||
         protocolCode == 'anytls' || protocolCode == 'naive') &&
        object['tls'] is! Map) {
      throw const FormatException('SINGBOX_TLS_REQUIRED');
    }
    // ShadowTLS detours cannot safely be flattened into one outbound.
    if (protocolCode == 'shadowtls') {
      throw const FormatException('SINGBOX_SHADOWTLS_CHAIN_REQUIRED');
    }
    // A copy keeps caller-owned profile data untouched.
    return object;
  }
}
