import 'dart:convert';

/// Desired policy, never an assertion that traffic is currently protected.
/// A native engine must acknowledge every protection before a connection starts.
enum VpnRoutingMode { fullTunnel, onlySelectedApps, excludeSelectedApps }
enum VpnDnsMode { protected, system }
enum VpnIpv6Mode { tunnelOrBlock, unprotected }
enum VpnPlatform { android, windows, ios, macos, other }

class VpnPolicy {
  const VpnPolicy({
    this.routingMode = VpnRoutingMode.fullTunnel,
    this.appIds = const [],
    this.killSwitchRequested = false,
    this.dnsMode = VpnDnsMode.protected,
    this.ipv6Mode = VpnIpv6Mode.tunnelOrBlock,
    this.allowLan = false,
    this.autoReconnect = true,
    this.autoConnect = false,
    this.autoSelectServer = true,
  });

  final VpnRoutingMode routingMode;
  final List<String> appIds;
  final bool killSwitchRequested;
  final VpnDnsMode dnsMode;
  final VpnIpv6Mode ipv6Mode;
  final bool allowLan;
  final bool autoReconnect;
  final bool autoConnect;
  final bool autoSelectServer;

  VpnPolicy copyWith({
    VpnRoutingMode? routingMode,
    List<String>? appIds,
    bool? killSwitchRequested,
    VpnDnsMode? dnsMode,
    VpnIpv6Mode? ipv6Mode,
    bool? allowLan,
    bool? autoReconnect,
    bool? autoConnect,
    bool? autoSelectServer,
  }) {
    return VpnPolicy(
      routingMode: routingMode ?? this.routingMode,
      appIds: appIds ?? this.appIds,
      killSwitchRequested: killSwitchRequested ?? this.killSwitchRequested,
      dnsMode: dnsMode ?? this.dnsMode,
      ipv6Mode: ipv6Mode ?? this.ipv6Mode,
      allowLan: allowLan ?? this.allowLan,
      autoReconnect: autoReconnect ?? this.autoReconnect,
      autoConnect: autoConnect ?? this.autoConnect,
      autoSelectServer: autoSelectServer ?? this.autoSelectServer,
    );
  }

  Map<String, dynamic> toJson() => {
    'schema': 1,
    'routingMode': routingMode.name,
    'appIds': appIds,
    'killSwitchRequested': killSwitchRequested,
    'dnsMode': dnsMode.name,
    'ipv6Mode': ipv6Mode.name,
    'allowLan': allowLan,
    'autoReconnect': autoReconnect,
    'autoConnect': autoConnect,
    'autoSelectServer': autoSelectServer,
  };

  static VpnPolicy fromJson(Map<String, dynamic> value) {
    if (value['schema'] != 1) {
      throw const FormatException('POLICY_VERSION_UNSUPPORTED');
    }
    T readEnum<T extends Enum>(List<T> options, String key) {
      final choice = value[key];
      if (choice is! String) {
        throw FormatException('INVALID_POLICY_FIELD_$key');
      }
      for (final item in options) {
        if (item.name == choice) return item;
      }
      throw FormatException('INVALID_POLICY_FIELD_$key');
    }

    bool readBool(String key) {
      final choice = value[key];
      if (choice is! bool) {
        throw FormatException('INVALID_POLICY_FIELD_$key');
      }
      return choice;
    }

    final ids = value['appIds'];
    if (ids is! List || ids.any((item) => item is! String)) {
      throw const FormatException('INVALID_POLICY_APP_IDS');
    }
    final rawIds = ids.cast<String>();
    return VpnPolicy(
      routingMode: readEnum(VpnRoutingMode.values, 'routingMode'),
      appIds: List.unmodifiable(rawIds),
      killSwitchRequested: readBool('killSwitchRequested'),
      dnsMode: readEnum(VpnDnsMode.values, 'dnsMode'),
      ipv6Mode: readEnum(VpnIpv6Mode.values, 'ipv6Mode'),
      allowLan: readBool('allowLan'),
      autoReconnect: readBool('autoReconnect'),
      autoConnect: readBool('autoConnect'),
      autoSelectServer: readBool('autoSelectServer'),
    );
  }

  String encode() => jsonEncode(toJson());

  static VpnPolicy decode(String json) {
    final raw = jsonDecode(json);
    if (raw is! Map<String, dynamic>) {
      throw const FormatException('INVALID_POLICY');
    }
    return fromJson(raw);
  }

  /// Validate a *draft* before persisting it. This does not enable any VPN.
  List<String> draftProblems(VpnPlatform platform) {
    final issues = <String>[];
    final selectedMode = routingMode != VpnRoutingMode.fullTunnel;
    if (selectedMode) {
      if (platform != VpnPlatform.android &&
          platform != VpnPlatform.windows) {
        issues.add('PER_APP_REQUIRES_MANAGED_OR_UNAVAILABLE');
      }
      if (appIds.isEmpty) issues.add('NO_SELECTED_APPS');
    }
    if (appIds.length > 100) issues.add('TOO_MANY_APPS');
    if (appIds.toSet().length != appIds.length) {
      issues.add('DUPLICATE_APPS');
    }
    if (appIds.any((id) =>
        id.isEmpty ||
        id.trim() != id ||
        id.length > 240 ||
        id.contains('\u0000') ||
        id.contains('\n') ||
        id.contains('\r'))) {
      issues.add('INVALID_APP_IDENTIFIER');
    }
    if (killSwitchRequested && dnsMode != VpnDnsMode.protected) {
      issues.add('STRICT_REQUIRES_PROTECTED_DNS');
    }
    if (killSwitchRequested && ipv6Mode != VpnIpv6Mode.tunnelOrBlock) {
      issues.add('STRICT_REQUIRES_IPV6_GUARD');
    }
    // Selected apps intentionally bypass VPN, which may conflict with an OS-wide
    // lockdown option. Require a native capability acknowledgment at connect.
    return issues;
  }

  /// Never report protection as active based on a saved toggle.
  /// Only platform-level verified capabilities can authorize future connect.
  List<String> connectionProblems(NativeVpnCapabilities native) {
    final issues = draftProblems(native.platform);
    if (!native.engineReady) issues.add('ENGINE_NOT_READY');
    if (!native.fullTunnel) issues.add('FULL_TUNNEL_UNSUPPORTED');
    if (routingMode == VpnRoutingMode.onlySelectedApps &&
        !native.includeApps) {
      issues.add('INCLUDE_APPS_UNSUPPORTED');
    }
    if (routingMode == VpnRoutingMode.excludeSelectedApps &&
        !native.excludeApps) {
      issues.add('EXCLUDE_APPS_UNSUPPORTED');
    }
    if (killSwitchRequested && !native.killSwitchEnforced) {
      issues.add('KILL_SWITCH_NOT_ENFORCED');
    }
    if (dnsMode == VpnDnsMode.protected && !native.dnsGuard) {
      issues.add('DNS_PROTECTION_UNAVAILABLE');
    }
    if (ipv6Mode == VpnIpv6Mode.tunnelOrBlock && !native.ipv6Guard) {
      issues.add('IPV6_PROTECTION_UNAVAILABLE');
    }
    if (allowLan && !native.localNetworkBypass) {
      issues.add('LAN_BYPASS_UNAVAILABLE');
    }
    if (autoConnect && !native.autoConnect) {
      issues.add('AUTO_CONNECT_UNAVAILABLE');
    }
    if (autoReconnect && !native.autoReconnect) {
      issues.add('AUTO_RECONNECT_UNAVAILABLE');
    }
    return issues;
  }
}

class NativeVpnCapabilities {
  const NativeVpnCapabilities({
    required this.platform,
    this.engineReady = false,
    this.fullTunnel = false,
    this.includeApps = false,
    this.excludeApps = false,
    this.killSwitchEnforced = false,
    this.dnsGuard = false,
    this.ipv6Guard = false,
    this.localNetworkBypass = false,
    this.autoConnect = false,
    this.autoReconnect = false,
    this.managedDevice = false,
  });

  final VpnPlatform platform;
  final bool engineReady;
  final bool fullTunnel;
  final bool includeApps;
  final bool excludeApps;
  /// True only after native OS lockdown/filter enforcement is confirmed.
  final bool killSwitchEnforced;
  final bool dnsGuard;
  final bool ipv6Guard;
  final bool localNetworkBypass;
  final bool autoConnect;
  final bool autoReconnect;
  final bool managedDevice;

  static NativeVpnCapabilities unavailable(VpnPlatform platform) =>
      NativeVpnCapabilities(platform: platform);

  static NativeVpnCapabilities fromNativeMap(
    VpnPlatform platform,
    Map<dynamic, dynamic> payload,
  ) {
    // A versioned native handshake makes accidental, partial plugin responses
    // fail closed instead of making the UI claim non-existent protection.
    if (payload['contractVersion'] != 1) {
      return unavailable(platform);
    }
    bool flag(String name) => payload[name] == true;
    final managed = flag('managedDevice');
    return NativeVpnCapabilities(
      platform: platform,
      engineReady: flag('engineReady'),
      fullTunnel: flag('fullTunnel'),
      includeApps: flag('includeApps') &&
          (platform == VpnPlatform.android ||
              platform == VpnPlatform.windows ||
              managed),
      excludeApps: flag('excludeApps') &&
          (platform == VpnPlatform.android ||
              platform == VpnPlatform.windows ||
              managed),
      killSwitchEnforced: flag('killSwitchEnforced'),
      dnsGuard: flag('dnsGuard'),
      ipv6Guard: flag('ipv6Guard'),
      localNetworkBypass: flag('localNetworkBypass'),
      autoConnect: flag('autoConnect'),
      autoReconnect: flag('autoReconnect'),
      managedDevice: managed,
    );
  }
}
