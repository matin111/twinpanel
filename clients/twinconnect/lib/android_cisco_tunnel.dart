import 'dart:async';
import 'dart:io';

import 'package:axevpn_flutter/openconnect_flutter.dart';
import 'cisco_openconnect_profile.dart';

/// An independent Android AnyConnect/CSTP TLS tunnel. Never WireGuard.
/// This engine is permitted to authenticate only to an administrator-pinned
/// TLS peer: the upstream Java plugin otherwise accepts untrusted certificates.
class AndroidCiscoTunnel {
  AndroidCiscoTunnel._();
  static final AndroidCiscoTunnel instance = AndroidCiscoTunnel._();

  OpenConnect? _engine;
  bool _initialized = false;
  bool _connected = false;

  bool get isConnected => _connected;

  /// Reject absent, SHA-1, or malformed pins before exposing any credentials.
  /// The Java CSTP implementation accepts hex SHA-256 certificate pins without
  /// a prefix or base64-encoded SPKI hashes with the pin-sha256: prefix.
  static String requiredSha256Pin(CiscoOpenConnectProfile profile) {
    final pin = profile.serverCertificate;
    if (pin == null || pin.isEmpty) {
      throw const FormatException('CISCO_SHA256_PIN_REQUIRED');
    }
    if (RegExp(r'^sha256:[0-9a-fA-F]{64}$').hasMatch(pin)) {
      return pin.substring(7);
    }
    if (RegExp(r'^pin-sha256:[A-Za-z0-9+/]{43}=$').hasMatch(pin)) {
      return pin;
    }
    throw const FormatException('CISCO_SHA256_PIN_REQUIRED');
  }

  Future<void> initialize() async {
    if (!Platform.isAndroid) {
      throw const FormatException('CISCO_ANDROID_ONLY');
    }
    if (_initialized) return;
    final engine = OpenConnect();
    await engine.initialize(localizedDescription: 'TwinConnect');
    final status = await engine.stage();
    if (status == OCStage.unknown) {
      throw const FormatException('CISCO_NATIVE_ENGINE_UNAVAILABLE');
    }
    _engine = engine;
    _initialized = true;
  }

  Future<void> connect(CiscoOpenConnectProfile profile) async {
    // Check pin BEFORE connecting or sending username/password to any peer.
    final pin = requiredSha256Pin(profile);
    await initialize();
    final engine = _engine!;
    _connected = false;
    try {
      await engine.connect(
        serverUrl: 'https://${profile.gateway}',
        name: 'TwinConnect Cisco',
        username: profile.username,
        password: profile.password,
        servercert: pin,
      );
      // The native call only requests a VpnService; it is NOT a success ack.
      // The independent service must report an established CSTP/TUN tunnel.
      for (var attempt = 0; attempt < 35; attempt++) {
        final stage = await engine.stage();
        if (stage == OCStage.denied || stage == OCStage.error ||
            stage == OCStage.disconnected) {
          throw const FormatException('CISCO_NATIVE_CONNECTION_FAILED');
        }
        if (stage == OCStage.connected && await engine.isServiceRunning()) {
          final stats = await engine.status();
          if (stats.state == 'connected') {
            _connected = true;
            return;
          }
        }
        await Future<void>.delayed(const Duration(seconds: 1));
      }
      throw const FormatException('CISCO_CONNECTION_TIMEOUT');
    } catch (_) {
      _connected = false;
      try { await engine.disconnect(); } catch (_) {}
      rethrow;
    }
  }

  Future<({bool connected, int? rx, int? tx})> status() async {
    if (!_initialized || !_connected) {
      return (connected: false, rx: null, tx: null);
    }
    final engine = _engine!;
    final stage = await engine.stage();
    final running = await engine.isServiceRunning();
    final stats = await engine.status();
    final active = stage == OCStage.connected && running &&
        stats.state == 'connected';
    _connected = active;
    return (connected: active,
        rx: active ? stats.bytesIn : null,
        tx: active ? stats.bytesOut : null);
  }

  Future<void> disconnect() async {
    _connected = false;
    if (_initialized) await _engine!.disconnect();
  }
}
