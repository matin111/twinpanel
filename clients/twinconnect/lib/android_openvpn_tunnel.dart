import 'dart:async';
import 'dart:io';

import 'package:openvpn_flutter/openvpn_flutter.dart';

import 'openvpn_profile_validator.dart';

/// Android OpenVPN engine. All profile material stays in process memory.
/// The plugin owns its own VpnService; WireGuard is never used as a fallback.
class AndroidOpenVpnTunnel {
  AndroidOpenVpnTunnel._();
  static final AndroidOpenVpnTunnel instance = AndroidOpenVpnTunnel._();

  OpenVPN? _engine;
  bool _initialized = false;
  bool _verified = false;

  bool get isConnected =>
      _initialized && _verified && _engine?.currentStage.isConnected == true;

  Future<void> initialize() async {
    if (!Platform.isAndroid) {
      throw const FormatException('OPENVPN_ANDROID_ONLY');
    }
    if (_initialized) return;
    final engine = OpenVPN();
    await engine.initialize(localizedDescription: 'TwinConnect');
    _engine = engine;
    _initialized = true;
  }

  Future<void> connect({required Map<String, dynamic> profile,
      required String name}) async {
    await initialize();
    final config = OpenVpnProfileValidator.validate(profile);
    // Log only static transport metadata, never endpoints, passwords,
    // certificates or user-supplied profile lines. This makes it possible
    // to compare Android and Windows transport/MTU without exposing secrets.
    // Engine owns tunnel configuration. Do not modify MTU, cipher or protocol
    // until a measured comparison with the Windows profile is available.
    final engine = _engine!;
    _verified = false;
    final username = profile['username'] ?? profile['user'];
    final password = profile['password'];
    // Never log, cache or persist raw profiles or credentials.
    try {
      final started = await engine.connect(
        config, name,
        username: username is String ? username : null,
        password: password is String ? password : null,
      );
      if (!started) throw const FormatException('OPENVPN_PERMISSION_DENIED');
      final stage = engine.currentStage.isConnected
          ? engine.currentStage
          : await engine.stageStream.firstWhere(
              (stage) => stage.isConnected || stage.isDisconnected,
            ).timeout(const Duration(seconds: 35));
      if (!stage.isConnected) {
        throw const FormatException('OPENVPN_SERVER_NOT_CONNECTED');
      }
      _verified = true; // Engine connected; internet verification is separate.
    } on TimeoutException {
      try { await engine.disconnect(); } catch (_) {}
      _verified = false;
      throw const FormatException('OPENVPN_CONNECTION_TIMEOUT');
    } catch (_) {
      try { await engine.disconnect(); } catch (_) {}
      _verified = false;
      rethrow;
    }
  }

  Future<(int?, int?)> counters() async {
    if (!isConnected) return (null, null);
    final status = await _engine!.status();
    int? parse(String? text) => text == null ? null :
        int.tryParse(text.replaceAll(RegExp(r'[^0-9]'), ''));
    return (parse(status.byteIn), parse(status.byteOut));
  }

  Future<void> disconnect() async {
    _verified = false;
    if (_initialized) await _engine!.disconnect();
  }
}
,
        multiLine: true, caseSensitive: false).firstMatch(config);
    final mtu = RegExp(r'^tun-mtu\\s+(\\d+)\\s*
    _verified = false;
    final username = profile['username'] ?? profile['user'];
    final password = profile['password'];
    // Never log, cache or persist raw profiles or credentials.
    try {
      final started = await engine.connect(
        config, name,
        username: username is String ? username : null,
        password: password is String ? password : null,
      );
      if (!started) throw const FormatException('OPENVPN_PERMISSION_DENIED');
      final stage = engine.currentStage.isConnected
          ? engine.currentStage
          : await engine.stageStream.firstWhere(
              (stage) => stage.isConnected || stage.isDisconnected,
            ).timeout(const Duration(seconds: 35));
      if (!stage.isConnected) {
        throw const FormatException('OPENVPN_SERVER_NOT_CONNECTED');
      }
      _verified = true; // Engine connected; internet verification is separate.
    } on TimeoutException {
      try { await engine.disconnect(); } catch (_) {}
      _verified = false;
      throw const FormatException('OPENVPN_CONNECTION_TIMEOUT');
    } catch (_) {
      try { await engine.disconnect(); } catch (_) {}
      _verified = false;
      rethrow;
    }
  }

  Future<(int?, int?)> counters() async {
    if (!isConnected) return (null, null);
    final status = await _engine!.status();
    int? parse(String? text) => text == null ? null :
        int.tryParse(text.replaceAll(RegExp(r'[^0-9]'), ''));
    return (parse(status.byteIn), parse(status.byteOut));
  }

  Future<void> disconnect() async {
    _verified = false;
    if (_initialized) await _engine!.disconnect();
  }
}
,
        multiLine: true, caseSensitive: false).firstMatch(config);
    final mss = RegExp(r'^mssfix\\s+(\\d+)\\s*
    _verified = false;
    final username = profile['username'] ?? profile['user'];
    final password = profile['password'];
    // Never log, cache or persist raw profiles or credentials.
    try {
      final started = await engine.connect(
        config, name,
        username: username is String ? username : null,
        password: password is String ? password : null,
      );
      if (!started) throw const FormatException('OPENVPN_PERMISSION_DENIED');
      final stage = engine.currentStage.isConnected
          ? engine.currentStage
          : await engine.stageStream.firstWhere(
              (stage) => stage.isConnected || stage.isDisconnected,
            ).timeout(const Duration(seconds: 35));
      if (!stage.isConnected) {
        throw const FormatException('OPENVPN_SERVER_NOT_CONNECTED');
      }
      _verified = true; // Engine connected; internet verification is separate.
    } on TimeoutException {
      try { await engine.disconnect(); } catch (_) {}
      _verified = false;
      throw const FormatException('OPENVPN_CONNECTION_TIMEOUT');
    } catch (_) {
      try { await engine.disconnect(); } catch (_) {}
      _verified = false;
      rethrow;
    }
  }

  Future<(int?, int?)> counters() async {
    if (!isConnected) return (null, null);
    final status = await _engine!.status();
    int? parse(String? text) => text == null ? null :
        int.tryParse(text.replaceAll(RegExp(r'[^0-9]'), ''));
    return (parse(status.byteIn), parse(status.byteOut));
  }

  Future<void> disconnect() async {
    _verified = false;
    if (_initialized) await _engine!.disconnect();
  }
}
,
        multiLine: true, caseSensitive: false).firstMatch(config);
    final transport = protocol?.group(1)?.toLowerCase() ?? 'unknown';
    final mtuValue = mtu?.group(1) ?? 'default';
    final mssValue = mss?.group(1) ?? 'default';
    // These are bounded numeric/preset fields validated above.
    developer.log('OPENVPN_PROFILE_TRANSPORT=$transport MTU=$mtuValue MSS=$mssValue',
        name: 'TwinOpenVpnDiagnostics');
    final engine = _engine!;
    _verified = false;
    final username = profile['username'] ?? profile['user'];
    final password = profile['password'];
    // Never log, cache or persist raw profiles or credentials.
    try {
      final started = await engine.connect(
        config, name,
        username: username is String ? username : null,
        password: password is String ? password : null,
      );
      if (!started) throw const FormatException('OPENVPN_PERMISSION_DENIED');
      final stage = engine.currentStage.isConnected
          ? engine.currentStage
          : await engine.stageStream.firstWhere(
              (stage) => stage.isConnected || stage.isDisconnected,
            ).timeout(const Duration(seconds: 35));
      if (!stage.isConnected) {
        throw const FormatException('OPENVPN_SERVER_NOT_CONNECTED');
      }
      _verified = true; // Engine connected; internet verification is separate.
    } on TimeoutException {
      try { await engine.disconnect(); } catch (_) {}
      _verified = false;
      throw const FormatException('OPENVPN_CONNECTION_TIMEOUT');
    } catch (_) {
      try { await engine.disconnect(); } catch (_) {}
      _verified = false;
      rethrow;
    }
  }

  Future<(int?, int?)> counters() async {
    if (!isConnected) return (null, null);
    final status = await _engine!.status();
    int? parse(String? text) => text == null ? null :
        int.tryParse(text.replaceAll(RegExp(r'[^0-9]'), ''));
    return (parse(status.byteIn), parse(status.byteOut));
  }

  Future<void> disconnect() async {
    _verified = false;
    if (_initialized) await _engine!.disconnect();
  }
}
