import 'dart:async';
import 'dart:io';

import 'package:openvpn_flutter/openvpn_flutter.dart';

import 'vpn_policy.dart';

/// Android OpenVPN 2.7 native VpnService, not Cisco/OpenConnect.
class AndroidOpenVpnTunnel {
  AndroidOpenVpnTunnel._();
  static final AndroidOpenVpnTunnel instance = AndroidOpenVpnTunnel._();

  OpenVPN? _engine;
  bool _initialized = false;
  bool _connecting = false;

  bool get available => Platform.isAndroid && _initialized;
  bool get connected =>
      available && _engine?.currentStage.isConnected == true;

  Future<bool> initialize() async {
    if (!Platform.isAndroid) return false;
    if (_initialized) return true;
    try {
      final engine = OpenVPN(
        onVpnStageChanged: (_, __) {},
        onVpnStatusChanged: (_) {},
      );
      await engine.initialize(
        localizedDescription: 'TwinConnect OpenVPN',
        showTrafficInNotification: true,
      );
      _engine = engine;
      _initialized = true;
      return true;
    } catch (_) {
      _engine = null;
      _initialized = false;
      return false;
    }
  }

  static void requireSafePolicy(VpnPolicy policy) {
    if (policy.routingMode != VpnRoutingMode.fullTunnel ||
        policy.dnsMode != VpnDnsMode.protected ||
        policy.ipv6Mode != VpnIpv6Mode.tunnelOrBlock ||
        policy.allowLan || policy.appIds.isNotEmpty ||
        policy.killSwitchRequested || policy.autoConnect ||
        policy.autoReconnect) {
      throw const FormatException('ANDROID_OPENVPN_POLICY_UNVERIFIED');
    }
  }

  /// Only existing .ovpn content received from the authorized tenant API.
  static String requireProfile(Map<String, dynamic> item) {
    final config = item['config'];
    if (config is! String || config.length < 70 ||
        config.length > 200000 ||
        !RegExp(r'^client\s*$', multiLine: true).hasMatch(config) ||
        !RegExp(r'^remote\s+\S+\s+\d+', multiLine: true).hasMatch(config)) {
      throw const FormatException('ANDROID_OPENVPN_CONFIG_INVALID');
    }
    return config;
  }

  Future<void> connect({
    required Map<String, dynamic> item,
    required String serverName,
    required VpnPolicy policy,
  }) async {
    requireSafePolicy(policy);
    if (!await initialize()) {
      throw const FormatException('ANDROID_OPENVPN_ENGINE_UNAVAILABLE');
    }
    if (_connecting || connected) {
      throw const FormatException('VPN_TUNNEL_ALREADY_ACTIVE');
    }
    final config = requireProfile(item);
    final engine = _engine!;
    _connecting = true;
    try {
      final finished = engine.stageStream
          .firstWhere((stage) => stage.isConnected || stage.isDisconnected);
      final result = await engine.connect(
        config, serverName,
        username: item['username'] is String ? item['username'] as String : null,
        password: item['password'] is String ? item['password'] as String : null,
      );
      if (!result) throw const FormatException('VPN_PERMISSION_DENIED');
      final stage = await finished.timeout(const Duration(seconds: 35));
      if (!stage.isConnected || !connected) {
        throw const FormatException('ANDROID_OPENVPN_CONNECT_FAILED');
      }
    } on TimeoutException {
      throw const FormatException('ANDROID_OPENVPN_CONNECT_TIMEOUT');
    } finally {
      _connecting = false;
    }
  }

  Future<void> disconnect() async {
    final engine = _engine;
    if (!Platform.isAndroid || engine == null) return;
    await engine.disconnect();
  }
}
