import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

import 'cisco_openconnect_profile.dart';

/// Embedded Android Cisco AnyConnect / OpenConnect-compatible CSTP-over-TLS
/// VpnService, separate from WireGuard, OpenVPN and sing-box.
/// The vendored Java code requires either Android CA+hostname validation or a SHA-256 pin.
class AndroidCiscoTunnel {
  AndroidCiscoTunnel._();
  static final AndroidCiscoTunnel instance = AndroidCiscoTunnel._();

  static const _channel = MethodChannel(
      'com.axevpn.flutter.openconnect/vpncontrol');
  bool _initialized = false;
  bool _connected = false;

  bool get isConnected => _connected;

  /// Empty pin means the bundled Java service MUST validate the system
  /// CA chain plus the HTTPS peer hostname. An explicitly provided pin must
  /// always be a valid SHA-256 certificate or SPKI fingerprint.
  static String validatedServerTrust(CiscoOpenConnectProfile profile) {
    final pin = profile.serverCertificate;
    if (pin == null || pin.isEmpty) return '';
    if (RegExp(r'^sha256:[0-9a-fA-F]{64}$').hasMatch(pin)) {
      return pin.substring(7);
    }
    if (RegExp(r'^pin-sha256:[A-Za-z0-9+/]{43}=$').hasMatch(pin)) {
      return pin;
    }
    throw const FormatException('CISCO_SHA256_PIN_INVALID');
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
    final pin = validatedServerTrust(profile); // Must precede credential transfer.
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
      // Starting the Android foreground service is asynchronous. A snapshot
      // of "disconnected" immediately after connect() is normal and MUST NOT
      // be treated as a failed authentication or a stopped VPN.
      var observedStarting = false;
      for (var attempt = 0; attempt < 35; attempt++) {
        final stage = await _stage();
        final nativeStatus = await _status();
        final rawReason = nativeStatus['failure_code'];
        // Accept only explicit known categories, never surface server strings.
        const allowedFailures = <String>{
          'CISCO_AUTH_CONTEXT_REJECTED',
          'CISCO_AUTH_SESSION_REJECTED',
          'CISCO_AUTH_EXCHANGE_FAILED',
          'CISCO_AUTH_INIT_FAILED',
          'CISCO_AUTH_INIT_CONTEXT_MISSING',
          'CISCO_AUTH_USERNAME_EXCHANGE_FAILED',
          'CISCO_AUTH_PASSWORD_EXCHANGE_FAILED',
          'CISCO_TLS_OR_SOCKET_FAILED',
          'CISCO_SOCKET_PROTECTION_FAILED',
          'CISCO_SOCKET_IO_FAILED',
          'CISCO_CERT_PIN_INVALID',
          'CISCO_NATIVE_ENGINE_UNAVAILABLE',
          'CISCO_NATIVE_START_FAILED',
          'CISCO_NATIVE_AUTH_FAILED',
          'CISCO_NATIVE_CSTP_FAILED',
          'CISCO_NATIVE_TUN_FAILED',
          'CISCO_NATIVE_LOOP_FAILED',
          'CISCO_CSTP_HANDSHAKE_FAILED',
          'CISCO_CSTP_CONFIG_MISSING',
          'CISCO_TUN_INTERFACE_FAILED',
          'CISCO_TLS_HANDSHAKE_FAILED',
          'CISCO_SOCKET_TIMEOUT',
          'CISCO_DNS_RESOLUTION_FAILED',
          'CISCO_GATEWAY_UNREACHABLE',
          'CISCO_AUTH_RESPONSE_INCOMPLETE',
          'CISCO_AUTH_XML_CHALLENGE_UNSUPPORTED',
        };
        final reason = rawReason is String && allowedFailures.contains(rawReason)
            ? rawReason : null;
        if (stage == 'denied') {
          throw FormatException(reason ?? 'CISCO_AUTH_OR_VPN_PERMISSION_DENIED');
        }
        if (stage == 'error') {
          throw FormatException(reason ?? 'CISCO_NATIVE_TUNNEL_FAILED');
        }
        if (stage == 'preparing' || stage == 'connecting' ||
            stage == 'authenticating' || stage == 'connected') {
          observedStarting = true;
        }
        if (stage == 'disconnected' && observedStarting &&
            !(await _serviceRunning())) {
          throw FormatException(reason ?? 'CISCO_ENGINE_DISCONNECTED');
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
