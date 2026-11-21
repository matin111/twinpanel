import 'dart:convert';
import 'dart:io';

import 'macos_standalone_panel_profile.dart';

/// Owns an app-scoped loopback SOCKS session. No system routing is modified.
/// This is separate from the one-shot probe used by the unsigned test card.
class MacStandaloneManagedProxy {
  MacStandaloneManagedProxy({required this.appContents});

  final Directory appContents;
  bool _ownsSession = false;

  File get _manager => File(
      '${appContents.path}/Resources/twinconnect-runtime/'
      'macos_native/standalone_connection_manager.py');

  Future<Map<String, dynamic>> _run(List<String> args) async {
    if (!Platform.isMacOS || !_manager.existsSync()) {
      throw const FormatException('MAC_PROXY_MANAGER_NOT_BUNDLED');
    }
    final response = await Process.run('/usr/bin/python3', [
      _manager.path, ...args,
    ], runInShell: false).timeout(const Duration(seconds: 25));
    if (response.exitCode != 0) {
      // Error payload is deliberately categorized; do not surface raw stderr,
      // which could be affected by a malicious or malformed engine.
      String reason = 'MAC_PROXY_MANAGER_COMMAND_FAILED';
      try {
        final value = jsonDecode(response.stderr.toString());
        if (value is Map && value['reason'] is String) {
          final candidate = value['reason'] as String;
          if (RegExp(r'^[A-Z][A-Z0-9_]{2,63}$').hasMatch(candidate)) {
            reason = candidate;
          }
        }
      } on FormatException {
        // Keep the generic safe error code.
      }
      throw FormatException(reason);
    }
    final value = jsonDecode(response.stdout.toString());
    if (value is! Map<String, dynamic>) {
      throw const FormatException('MAC_PROXY_MANAGER_RESPONSE_INVALID');
    }
    return value;
  }

  static Directory? packagedContents() {
    if (!Platform.isMacOS) return null;
    final executable = File(Platform.resolvedExecutable);
    if (executable.parent.uri.pathSegments
            .where((part) => part.isNotEmpty).lastOrNull != 'MacOS') {
      return null;
    }
    final contents = executable.parent.parent;
    return contents.uri.pathSegments
            .where((part) => part.isNotEmpty).lastOrNull == 'Contents'
        ? contents : null;
  }

  Future<String> connect(MacStandalonePreparedProfile profile) async {
    if (_ownsSession) {
      throw const FormatException('MAC_PROXY_ALREADY_CONNECTED');
    }
    final privateDir = await Directory.systemTemp
        .createTemp('twinconnect-managed-profile-');
    final config = File('${privateDir.path}/client.json');
    bool started = false;
    try {
      await config.writeAsString(profile.configJson, flush: true);
      final result = await _run([
        'start', profile.protocolCode, config.path,
        '--owner-pid', pid.toString(),
      ]);
      if (result['state'] != 'process_running_unverified' &&
          result['state'] != 'started') {
        throw const FormatException('MAC_PROXY_START_NOT_CONFIRMED');
      }
      started = true;
      _ownsSession = true;
      final verified = await _run(['probe']);
      final ip = verified['egress_ip'];
      if (verified['state'] != 'proxy_egress_reachable' ||
          ip is! String || InternetAddress.tryParse(ip) == null) {
        throw const FormatException('MAC_PROXY_EGRESS_NOT_VERIFIED');
      }
      return ip;
    } catch (_) {
      if (started) {
        try {
          await disconnect();
        } catch (_) {
          // Preserve ownership state if stop could not be confirmed.
        }
      }
      rethrow;
    } finally {
      // The manager copies credentials into its own controlled runtime
      // before returning, so never leave a second config in system temp.
      await privateDir.delete(recursive: true);
    }
  }

  Future<void> disconnect() async {
    if (!_ownsSession) return; // Do not stop another owner's proxy.
    final response = await _run(['stop']);
    if (response['state'] != 'stopped') {
      throw const FormatException('MAC_PROXY_STOP_UNVERIFIED');
    }
    _ownsSession = false;
  }

  bool get connectedLocally => _ownsSession;
  String get socksEndpoint => '127.0.0.1:17089';
  bool get systemWideVpn => false;
}
