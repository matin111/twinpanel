/// TwinPanel's 16 canonical protocols. Client engines are PLANNED families,
/// not proof the protocol currently connects in this Flutter app.
///
/// These IDs must agree with backend/app/central_app_protocols.py and the
/// panel's CANONICAL_PROTOCOLS. A protocol may be selected on the panel but
/// have no usable configuration or native engine on this device.
enum VpnEngineFamily {
  openconnect,
  openvpn,
  wireguard,
  nativeL2tp,
  xray,
  singbox,
  mieru,
  trusttunnel,
  amneziawg,
  sudoku,
}

class VpnProtocolDefinition {
  const VpnProtocolDefinition({
    required this.code,
    required this.name,
    required this.engine,
    required this.profileFormat,
  });

  final String code;
  final String name;
  final VpnEngineFamily engine;
  final String profileFormat;
}

class VpnProtocols {
  static const List<VpnProtocolDefinition> all = [
    VpnProtocolDefinition(
      code: 'cisco', name: 'Cisco / OpenConnect',
      engine: VpnEngineFamily.openconnect, profileFormat: 'username_password',
    ),
    VpnProtocolDefinition(
      code: 'openvpn', name: 'OpenVPN',
      engine: VpnEngineFamily.openvpn, profileFormat: 'ovpn',
    ),
    VpnProtocolDefinition(
      code: 'wireguard', name: 'WireGuard',
      engine: VpnEngineFamily.wireguard, profileFormat: 'wg_conf',
    ),
    VpnProtocolDefinition(
      code: 'l2tp', name: 'L2TP / IPsec',
      engine: VpnEngineFamily.nativeL2tp,
      profileFormat: 'username_password_psk',
    ),
    VpnProtocolDefinition(
      code: 'v2ray', name: 'V2Ray / Xray',
      engine: VpnEngineFamily.xray, profileFormat: 'xray_profiles',
    ),
    VpnProtocolDefinition(
      code: 'hysteria2', name: 'Hysteria2',
      engine: VpnEngineFamily.singbox, profileFormat: 'singbox_or_uri',
    ),
    VpnProtocolDefinition(
      code: 'tuic', name: 'TUIC',
      engine: VpnEngineFamily.singbox, profileFormat: 'singbox_or_uri',
    ),
    VpnProtocolDefinition(
      code: 'anytls', name: 'AnyTLS',
      engine: VpnEngineFamily.singbox, profileFormat: 'singbox_or_uri',
    ),
    VpnProtocolDefinition(
      code: 'naive', name: 'NaiveProxy',
      engine: VpnEngineFamily.singbox, profileFormat: 'singbox_or_uri',
    ),
    VpnProtocolDefinition(
      code: 'shadowtls', name: 'ShadowTLS',
      engine: VpnEngineFamily.singbox, profileFormat: 'singbox_chain',
    ),
    VpnProtocolDefinition(
      code: 'snell', name: 'Snell',
      engine: VpnEngineFamily.singbox, profileFormat: 'singbox_or_uri',
    ),
    VpnProtocolDefinition(
      code: 'socks5', name: 'SOCKS5',
      engine: VpnEngineFamily.singbox, profileFormat: 'singbox_or_uri',
    ),
    VpnProtocolDefinition(
      code: 'mieru', name: 'Mieru',
      engine: VpnEngineFamily.mieru, profileFormat: 'mieru_profile',
    ),
    VpnProtocolDefinition(
      code: 'trusttunnel', name: 'TrustTunnel',
      engine: VpnEngineFamily.trusttunnel,
      profileFormat: 'trusttunnel_profile',
    ),
    VpnProtocolDefinition(
      code: 'amneziawg', name: 'AmneziaWG',
      engine: VpnEngineFamily.amneziawg, profileFormat: 'awg_conf',
    ),
    VpnProtocolDefinition(
      code: 'sudoku', name: 'Sudoku',
      engine: VpnEngineFamily.sudoku, profileFormat: 'sudoku_profile',
    ),
  ];

  static VpnProtocolDefinition? byCode(String code) {
    final lower = code.trim().toLowerCase();
    final canonical = <String, String>{
      'xray': 'v2ray',
      'vless': 'v2ray',
      'openconnect': 'cisco',
      'anyconnect': 'cisco',
      'l2tp/ipsec': 'l2tp',
      'naiveproxy': 'naive',
      'hy2': 'hysteria2',
      'socks': 'socks5',
      'awg': 'amneziawg',
    }[lower] ?? lower;
    for (final candidate in all) {
      if (candidate.code == canonical) return candidate;
    }
    return null;
  }
}

class PanelProtocolStatus {
  const PanelProtocolStatus({
    required this.protocol,
    required this.selected,
    required this.configRecordPresent,
    required this.clientEngineReady,
  });

  final VpnProtocolDefinition protocol;
  final bool selected;
  /// The panel has a stored credential record, not a successful connection.
  final bool configRecordPresent;
  /// Vendor API cannot assert device readiness: always false in this phase.
  final bool clientEngineReady;

  factory PanelProtocolStatus.fromJson(Map<String, dynamic> input) {
    final raw = input['code'];
    final definition = raw is String ? VpnProtocols.byCode(raw) : null;
    if (definition == null || definition.code != raw) {
      throw const FormatException('UNKNOWN_PROTOCOL');
    }
    return PanelProtocolStatus(
      protocol: definition,
      selected: input['selected'] == true,
      configRecordPresent: input['config_record_present'] == true,
      clientEngineReady: false,
    );
  }
}

class PanelProtocolCatalog {
  const PanelProtocolCatalog({
    required this.namespace,
    required this.entries,
  });

  final String namespace;
  final List<PanelProtocolStatus> entries;

  factory PanelProtocolCatalog.fromJson(Map<String, dynamic> input) {
    if (input['schema'] != 1 ||
        input['namespace'] is! String ||
        input['protocols'] is! List) {
      throw const FormatException('INVALID_PROTOCOL_CATALOG');
    }
    final rows = input['protocols'] as List<dynamic>;
    if (rows.length != VpnProtocols.all.length) {
      throw const FormatException('INCOMPLETE_PROTOCOL_CATALOG');
    }
    final parsed = <String, PanelProtocolStatus>{};
    for (final row in rows) {
      if (row is! Map<String, dynamic>) {
        throw const FormatException('INVALID_PROTOCOL_CATALOG');
      }
      final status = PanelProtocolStatus.fromJson(row);
      if (parsed.containsKey(status.protocol.code)) {
        throw const FormatException('DUPLICATE_PROTOCOL');
      }
      parsed[status.protocol.code] = status;
    }
    if (parsed.length != VpnProtocols.all.length) {
      throw const FormatException('INCOMPLETE_PROTOCOL_CATALOG');
    }
    return PanelProtocolCatalog(
      namespace: (input['namespace'] as String).toUpperCase(),
      entries: [
        for (final def in VpnProtocols.all) parsed[def.code]!,
      ],
    );
  }
}

class NativeProtocolReadiness {
  const NativeProtocolReadiness({
    required this.supportedCodes,
    this.contractVersion = 1,
  });

  final Set<String> supportedCodes;
  final int contractVersion;

  factory NativeProtocolReadiness.fromNative(dynamic raw) {
    if (raw is! Map || raw['contractVersion'] != 1 ||
        raw['supportedProtocols'] is! List) {
      return const NativeProtocolReadiness(supportedCodes: {});
    }
    final codes = <String>{};
    for (final value in raw['supportedProtocols'] as List<dynamic>) {
      if (value is! String) {
        return const NativeProtocolReadiness(supportedCodes: {});
      }
      final definition = VpnProtocols.byCode(value);
      if (definition == null || definition.code != value) {
        return const NativeProtocolReadiness(supportedCodes: {});
      }
      codes.add(value);
    }
    return NativeProtocolReadiness(supportedCodes: Set.unmodifiable(codes));
  }

  bool supports(String code) => supportedCodes.contains(code);
}

/// One protocol at a time: profile information stays in memory, never prefs.
class ClientProtocolProfiles {
  const ClientProtocolProfiles({
    required this.namespace,
    required this.protocol,
    required this.items,
  });

  final String namespace;
  final VpnProtocolDefinition protocol;
  final List<Map<String, dynamic>> items;

  factory ClientProtocolProfiles.fromJson(Map<String, dynamic> input) {
    if (input['schema'] != 1 || input['namespace'] is! String ||
        input['protocol'] is! String || input['items'] is! List) {
      throw const FormatException('INVALID_PROTOCOL_PROFILES');
    }
    final definition = VpnProtocols.byCode(input['protocol'] as String);
    if (definition == null ||
        definition.code != input['protocol'] ||
        (input['items'] as List).isEmpty ||
        (input['items'] as List).length > 200) {
      throw const FormatException('INVALID_PROTOCOL_PROFILES');
    }
    final items = <Map<String, dynamic>>[];
    for (final raw in input['items'] as List) {
      if (raw is! Map<String, dynamic>) {
        throw const FormatException('INVALID_PROTOCOL_PROFILES');
      }
      // Deep-copy fields so nested Xray inbounds and ShadowTLS detour chains
      // remain intact; never convert one transport into another.
      items.add(Map<String, dynamic>.from(raw));
    }
    return ClientProtocolProfiles(
      namespace: (input['namespace'] as String).toUpperCase(),
      protocol: definition,
      items: items,
    );
  }
}
