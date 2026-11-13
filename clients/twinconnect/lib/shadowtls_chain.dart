import 'dart:convert';
import 'dart:io';

/// Parses exactly the two-outbound ShadowTLS chain delivered by TwinPanel:
/// Shadowsocks user identity -> ShadowTLS v3 transport. Never run untrusted
/// remote inbounds, routes, experimental API, or an arbitrary outbound.
class ShadowTlsChain {
  const ShadowTlsChain({
    required this.shadowsocks,
    required this.transport,
    required this.endpoint,
  });

  final Map<String, dynamic> shadowsocks;
  final Map<String, dynamic> transport;
  final String endpoint;

  static ShadowTlsChain fromItem(Map<String, dynamic> item) {
    final raw = item['config'];
    if (raw is! String || raw.isEmpty || raw.length > 131072) {
      throw const FormatException('SHADOWTLS_CHAIN_MISSING');
    }
    dynamic decoded;
    try {
      decoded = jsonDecode(raw);
    } catch (_) {
      throw const FormatException('SHADOWTLS_CHAIN_INVALID');
    }
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('SHADOWTLS_CHAIN_INVALID');
    }
    final rows = decoded['outbounds'];
    if (rows is! List || rows.length != 2 ||
        rows.any((row) => row is! Map<String, dynamic>)) {
      throw const FormatException('SHADOWTLS_CHAIN_INVALID');
    }
    final list = rows.cast<Map<String, dynamic>>();
    final inner = list.where((row) => row['type'] == 'shadowsocks').toList();
    final outer = list.where((row) => row['type'] == 'shadowtls').toList();
    if (inner.length != 1 || outer.length != 1) {
      throw const FormatException('SHADOWTLS_CHAIN_INVALID');
    }
    final ss = Map<String, dynamic>.from(inner.single);
    final tls = Map<String, dynamic>.from(outer.single);
    final innerTag = ss['tag'];
    final outerTag = tls['tag'];
    if (innerTag is! String || innerTag.isEmpty ||
        outerTag is! String || outerTag.isEmpty ||
        innerTag == outerTag || ss['detour'] != outerTag ||
        (decoded['route'] is Map &&
          (decoded['route'] as Map)['final'] != innerTag)) {
      throw const FormatException('SHADOWTLS_DETOUR_INVALID');
    }
    final method = ss['method'];
    final innerPassword = ss['password'];
    if (method is! String || method.isEmpty ||
        innerPassword is! String || innerPassword.isEmpty ||
        ss.containsKey('server') || ss.containsKey('server_port') ||
        ss.containsKey('tls') || ss.containsKey('plugin')) {
      throw const FormatException('SHADOWTLS_INNER_INVALID');
    }
    final version = tls['version'];
    final server = tls['server'];
    final port = tls['server_port'];
    final outerPassword = tls['password'];
    final tlsOptions = tls['tls'];
    if (version != 3 || outerPassword is! String || outerPassword.isEmpty ||
        server is! String || server.isEmpty || server.length > 255 ||
        server.contains('/') || server.contains('\\\\') ||
        server.contains(' ') || server.contains('@') ||
        server.contains('?') || server.contains('#') ||
        port is! int || port < 1 || port > 65535 ||
        tlsOptions is! Map || tlsOptions['enabled'] != true ||
        tlsOptions['server_name'] is! String ||
        (tlsOptions['server_name'] as String).isEmpty ||
        tls.containsKey('detour')) {
      throw const FormatException('SHADOWTLS_TRANSPORT_INVALID');
    }
    // Only use the known endpoint fields. A subscription cannot inject
    // arbitrary direct routes, selectors or controller settings.
    for (final key in [...ss.keys, ...tls.keys]) {
      if (const {'inbounds','route','experimental','log','selector',
                 'outbounds','override_address','override_port'}
          .contains(key)) {
        throw const FormatException('SHADOWTLS_UNTRUSTED_CONFIG');
      }
    }
    return ShadowTlsChain(
      shadowsocks: ss, transport: tls, endpoint: server,
    );
  }

  List<Map<String, dynamic>> outbounds({String? resolvedServer}) {
    final outer = Map<String, dynamic>.from(transport);
    if (resolvedServer != null) {
      if (InternetAddress.tryParse(resolvedServer)?.type !=
          InternetAddressType.IPv4) {
        throw const FormatException('SINGBOX_BOOTSTRAP_IP_INVALID');
      }
      // Preserve panel-delivered TLS server_name for certificate validation.
      outer['server'] = resolvedServer;
    }
    outer['tag'] = 'shadowtls-transport';
    final inner = Map<String, dynamic>.from(shadowsocks)
      ..['tag'] = 'proxy'
      ..['detour'] = 'shadowtls-transport';
    return [inner, outer];
  }
}
