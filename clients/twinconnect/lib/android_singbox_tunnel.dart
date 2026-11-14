import 'dart:convert';
import 'dart:io';

import 'package:sing_box/sing_box.dart';

import 'singbox_profile_validator.dart';

/// Independent Android VpnService engine for the supported sing-box family.
/// This is never routed through WireGuard's native MethodChannel.
/// Only authenticated panel-issued native outbound JSON is accepted.
class AndroidSingBoxTunnel {
  AndroidSingBoxTunnel._();

  static final AndroidSingBoxTunnel instance = AndroidSingBoxTunnel._();
  bool _initialized = false;

  static const supported = <String>{
    'hysteria2', 'tuic', 'anytls', 'socks5',
  };

  Future<void> initialize() async {
    if (!Platform.isAndroid) {
      throw const FormatException('SINGBOX_ANDROID_ONLY');
    }
    if (_initialized) return;
    await SingBox.instance.initialize(const SingBoxOptions(
      android: SingBoxAndroidOptions(notificationTitle: 'TwinConnect'),
    ));
    _initialized = true;
  }

  Future<void> connect({
    required String protocol,
    required Map<String, dynamic> profile,
  }) async {
    if (!supported.contains(protocol)) {
      throw const FormatException('SINGBOX_PROTOCOL_UNSUPPORTED');
    }
    final outbound = SingBoxProfileValidator.validateOutbound(
      protocolCode: protocol,
      item: profile,
    );
    await initialize();
    // The plugin builds the local TUN/DNS/routing config; never accept
    // untrusted subscription-provided inbounds, routes or app settings.
    // Do not persist profiles in TwinConnect's own preferences.
    await SingBox.instance.connect(jsonEncode(outbound));
    if (SingBox.instance.status != SingBoxConnectionStatus.connected) {
      throw const FormatException('SINGBOX_TUNNEL_NOT_VERIFIED');
    }
  }

  bool get isConnected => _initialized &&
      SingBox.instance.status == SingBoxConnectionStatus.connected;

  Future<void> disconnect() async {
    if (!_initialized) return;
    await SingBox.instance.disconnect();
  }
}
