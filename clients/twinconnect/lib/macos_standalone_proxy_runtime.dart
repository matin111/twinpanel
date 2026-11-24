import 'dart:async';
import 'dart:io';

import 'macos_standalone_panel_profile.dart';

/// Debug-only, app-scoped SOCKS egress probe for unsigned macOS development.
///
/// Does not modify system DNS, routes or NetworkExtension state. An engine
/// process staying alive is not evidence of a usable connection. A real curl
/// request through a loopback-only SOCKS proxy is required for success.
///
/// macOS sandbox rules may forbid child process creation in production. That
/// failure is explicit and is never represented as a successful VPN.
class MacStandaloneProxyRuntime {
  MacStandaloneProxyRuntime({
    required this.engineRoot,
    this.curlExecutable = '/usr/bin/curl',
  });

  final Directory engineRoot;
  final String curlExecutable;

  /// Resolve engines from the installed app first, not the developer's
  /// ~/twinpanel checkout. The executable sits in Contents/MacOS while
  /// packaged runtimes live in Contents/Resources/twinconnect-runtime.
  static Directory? packagedEngineRoot({String? executablePath}) {
    if (!Platform.isMacOS) return null;
    final executable = File(executablePath ?? Platform.resolvedExecutable);
    final macOSDirectory = executable.parent;
    if (macOSDirectory.uri.pathSegments
        .where((segment) => segment.isNotEmpty).lastOrNull != 'MacOS') {
      return null;
    }
    final contentsDirectory = macOSDirectory.parent;
    if (contentsDirectory.uri.pathSegments
        .where((segment) => segment.isNotEmpty).lastOrNull != 'Contents') {
      return null;
    }
    final root = Directory(
      '${contentsDirectory.path}/Resources/twinconnect-runtime/macos_native/build',
    );
    return root.existsSync() ? root : null;
  }

  bool _busy = false;

  Future<MacStandaloneProbeResult> probe(
    MacStandalonePreparedProfile profile,
  ) async {
    if (!Platform.isMacOS) {
      throw const FormatException('MACOS_REQUIRED');
    }
    if (_busy) {
      throw const FormatException('MAC_STANDALONE_PROBE_ALREADY_RUNNING');
    }
    _busy = true;
    Directory? privateDirectory;
    Process? engine;
    try {
      final platformArch = await Process.run('/usr/bin/uname', ['-m'])
          .timeout(const Duration(seconds: 4));
      if (platformArch.exitCode != 0) {
        throw const FormatException('MAC_STANDALONE_ARCH_UNAVAILABLE');
      }
      final arch = platformArch.stdout.toString().trim() == 'x86_64'
          ? 'amd64' : 'arm64';
      final executableName = profile.protocolCode == 'v2ray'
          ? 'xray' : 'sing-box';
      final executable = File(
        '${engineRoot.path}/'
        '${executableName == 'xray' ? 'xray' : 'singbox'}/'
        '$arch/$executableName',
      );
      if (!executable.existsSync()) {
        throw const FormatException('MAC_STANDALONE_ENGINE_NOT_INSTALLED');
      }
      privateDirectory = await Directory.systemTemp
          .createTemp('twinconnect-private-proxy-');
      final config = File('${privateDirectory.path}/client.json');
      await config.writeAsString(profile.configJson, flush: true);
      final args = executableName == 'xray'
          ? ['run', '-config', config.path]
          : ['run', '-c', config.path];
      engine = await Process.start(executable.path, args,
          runInShell: false, mode: ProcessStartMode.normal);
      // Drain logs but never expose credentials, command lines or profiles.
      engine.stdout.listen((_) {});
      engine.stderr.listen((_) {});
      final earlyExit = await Future.any<bool>([
        engine.exitCode.then((_) => true),
        Future<bool>.delayed(const Duration(milliseconds: 900), () => false),
      ]);
      if (earlyExit) {
        throw const FormatException('MAC_STANDALONE_ENGINE_EXITED_EARLY');
      }
      final curl = await Process.run(curlExecutable, [
        '-4', '--silent', '--show-error', '--fail',
        '--connect-timeout', '5', '--max-time', '14',
        '--proxy', 'socks5h://127.0.0.1:${profile.localPort}',
        '--noproxy', '', 'https://api.ipify.org',
      ]).timeout(const Duration(seconds: 18));
      if (curl.exitCode != 0) {
        throw const FormatException('MAC_STANDALONE_PROXY_EGRESS_FAILED');
      }
      final rawIp = curl.stdout.toString().trim();
      final ip = InternetAddress.tryParse(rawIp);
      if (ip == null || ip.type != InternetAddressType.IPv4 ||
          ip.isLoopback || ip.isLinkLocal || ip.isMulticast) {
        throw const FormatException('MAC_STANDALONE_INVALID_EGRESS_IP');
      }
      return MacStandaloneProbeResult(
        protocolCode: profile.protocolCode,
        serverId: profile.serverId,
        egressIp: rawIp,
      );
    } on ProcessException {
      throw const FormatException('MAC_STANDALONE_PROCESS_NOT_ALLOWED');
    } on TimeoutException {
      throw const FormatException('MAC_STANDALONE_PROXY_TIMEOUT');
    } finally {
      engine?.kill(ProcessSignal.sigterm);
      try {
        if (privateDirectory != null) {
          await privateDirectory.delete(recursive: true);
        }
      } on FileSystemException {
        throw const FormatException('MAC_STANDALONE_PRIVATE_FILE_CLEANUP_FAILED');
      } finally {
        _busy = false;
      }
    }
  }
}

class MacStandaloneProbeResult {
  const MacStandaloneProbeResult({
    required this.protocolCode,
    required this.serverId,
    required this.egressIp,
  });

  final String protocolCode;
  final String serverId;
  final String egressIp;

  bool get systemWideVpn => false;
}
