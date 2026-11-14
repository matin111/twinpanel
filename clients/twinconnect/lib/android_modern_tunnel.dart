import 'dart:convert';
import 'dart:io';

import 'package:sing_box/sing_box.dart';

import 'protocols.dart';
import 'singbox_profile_validator.dart';
import 'vpn_policy.dart';

/// Embedded Android VpnService transport for the subset of Panel protocols
/// whose exact sing-box outbound formats are validated and built into libbox.
/// Does not claim Cisco/OpenVPN/L2TP, ShadowTLS chains, Naive or XHTTP support.
/// This experimental GPL core must not be shipped without license review.
class AndroidModernTunnel {
  AndroidModernTunnel._();
  static final AndroidModernTunnel instance = AndroidModernTunnel._();

  static const Set<String> protocolCodes = {
    'hysteria2', 'tuic', 'anytls', 'snell', 'socks5',
  };

  bool _initialized = false;
  bool _connecting = false;
  String? _activeProtocol;

  bool get available => Platform.isAndroid && _initialized;
  bool get connected =>
      available && SingBox.instance.status == SingBoxConnectionStatus.connected;
  String? get activeProtocol => connected ? _activeProtocol : null;

  Future<bool> initialize() async {
    if (!Platform.isAndroid) return false;
    if (_initialized) return true;
    try {
      await SingBox.instance.initialize(const SingBoxOptions(
        android: SingBoxAndroidOptions(notificationTitle: 'TwinConnect'),
      ));
      _initialized = true;
      return true;
    } catch (_) {
      _initialized = false;
      return false;
    }
  }

  static void ensureSupported(String protocol) {
    if (!protocolCodes.contains(protocol) ||
        !SingBoxProfileValidator.supportsFamily(protocol)) {
      throw const FormatException('ANDROID_MODERN_PROTOCOL_UNSUPPORTED');
    }
  }

  /// No client-side persistence of a raw subscription, and no conversion of
  /// opaque, unverified URI/ShadowTLS detours into broken VPN configurations.
  static Map<String, dynamic> validatedOutbound({
    required String protocol,
    required Map<String, dynamic> item,
  }) {
    ensureSupported(protocol);
    return SingBoxProfileValidator.validateOutbound(
      protocolCode: protocol, item: item,
    );
  }

  static void requireSafePolicy(VpnPolicy policy) {
    if (policy.routingMode != VpnRoutingMode.fullTunnel ||
        policy.dnsMode != VpnDnsMode.protected ||
        policy.ipv6Mode != VpnIpv6Mode.tunnelOrBlock ||
        policy.allowLan || policy.appIds.isNotEmpty ||
        policy.autoConnect || policy.autoReconnect ||
        policy.killSwitchRequested) {
      throw const FormatException('ANDROID_MODERN_POLICY_UNVERIFIED');
    }
  }

  /// The server config is fetched from this session's panel just before
  /// connecting. Nothing is invented and no profile data is logged.
  Future<void> connect({
    required String protocol,
    required Map<String, dynamic> item,
    required VpnPolicy policy,
  }) async {
    ensureSupported(protocol);
    if (!await initialize()) {
      throw const FormatException('ANDROID_MODERN_ENGINE_UNAVAILABLE');
    }
    requireSafePolicy(policy);
    if (_connecting || connected) {
      throw const FormatException('VPN_TUNNEL_ALREADY_ACTIVE');
    }
    final outbound = validatedOutbound(protocol: protocol, item: item);
    _connecting = true;
    try {
      // The plugin applies its own validated Android TUN config. A successful
      // call indicates engine startup, not independently verified egress.
      await SingBox.instance.connect(jsonEncode(outbound));
      if (SingBox.instance.status != SingBoxConnectionStatus.connected) {
        throw const FormatException('ANDROID_MODERN_TUNNEL_NOT_CONNECTED');
      }
      _activeProtocol = protocol;
    } finally {
      _connecting = false;
    }
  }

  Future<void> disconnect() async {
    if (!_initialized || !Platform.isAndroid) return;
    await SingBox.instance.disconnect();
    _activeProtocol = null;
  }
}
