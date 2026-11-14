import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

import 'cisco_openconnect_profile.dart';

/// Embedded Android Cisco AnyConnect / OpenConnect-compatible CSTP-over-TLS
/// VpnService, separate from WireGuard, OpenVPN and sing-box.
/// The vendored Java code requires an administrator-provided SHA-256 pin.
class AndroidCiscoTunnel {
  AndroidCiscoTunnel._();
  static final AndroidCiscoTunnel instance = AndroidCiscoTunnel._();

  static const _channel = MethodChannel(
      'com.axevpn.flutter.openconnect/vpncontrol');
  bool _initialized = false;
  bool _connected = false;

  bool get isConnected => _connected;

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
    await _channel.invokeMethod<void>('initialize', {
      'localizedDescription': 'TwinConnect',
    });
    final stage = await _channel.invokeMethod<String>('stage');
    if (stage == null || stage == 'unknown') {
      throw const FormatException('CISCO_NATIVE_ENGINE_UNAVAILABLE');
    }
    _initialized = true;
  }

  Future<String> _stage() async =>
      await _channel.invokeMethod<String>('stage') ?? 'unknown';

  Future<bool> _serviceRunning() async =>
      await _channel.invokeMethod<bool>('isRunning') ?? false;

  Future<Map<String, dynamic>> _status() async {
    final raw = await _channel.invokeMethod<String>('status');
    if (raw == null || raw.isEmpty) return const {};
    final data = jsonDecode(raw);
    if (data is! Map) return const {};
    return Map<String, dynamic>.from(data);
  }

  Future<void> connect(CiscoOpenConnectProfile profile) async {
    final pin = requiredSha256Pin(profile); // Must precede credential transfer.
    await initialize();
    _connected = false;
    try {
      await _channel.invokeMethod<void>('connect', {
        'server_url': 'https://${profile.gateway}',
        'name': 'TwinConnect Cisco',
        'username': profile.username,
        'password': profile.password,
        'servercert': pin,
        'bypass_packages': <String>[],
      });
      // Native connect starts a foreground service, not an established tunnel.
      for (var attempt = 0; attempt < 35; attempt++) {
        final stage = await _stage();
        if (stage == 'denied' || stage == 'error' ||
            stage == 'disconnected') {
          throw const FormatException('CISCO_NATIVE_CONNECTION_FAILED');
        }
        if (stage == 'connected' && await _serviceRunning()) {
          final stats = await _status();
          if (stats['state'] == 'connected') {
            _connected = true;
            return;
          }
        }
        await Future<void>.delayed(const Duration(seconds: 1));
      }
      throw const FormatException('CISCO_CONNECTION_TIMEOUT');
    } catch (_) {
      _connected = false;
      try { await _channel.invokeMethod<void>('disconnect'); } catch (_) {}
      rethrow;
    }
  }

  Future<({bool connected, int? rx, int? tx})> status() async {
    if (!_initialized || !_connected) {
      return (connected: false, rx: null, tx: null);
    }
    final stage = await _stage();
    final running = await _serviceRunning();
    final stats = await _status();
    final active = stage == 'connected' && running &&
        stats['state'] == 'connected';
    _connected = active;
    int? count(dynamic v) {
      final n = v is int ? v : int.tryParse(v?.toString() ?? '');
      return n != null && n >= 0 ? n : null;
    }
    return (
      connected: active,
      rx: active ? count(stats['bytes_in']) : null,
      tx: active ? count(stats['bytes_out']) : null,
    );
  }

  Future<void> disconnect() async {
    _connected = false;
    if (_initialized) await _channel.invokeMethod<void>('disconnect');
  }
}
