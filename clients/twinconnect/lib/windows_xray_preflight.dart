import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// Verifies a separately installed Xray-core executable. This is a
/// credential-safe syntax check, NOT a successful tunnel or an engine install.
class WindowsXrayPreflight {
  const WindowsXrayPreflight._();

  static String enginePath(String appExecutable) {
    return '${File(appExecutable).parent.path}\\engines\\xray\\xray.exe';
  }

  // Version verification is a subprocess: reuse it for one minute ONLY if
  // the bundled executable path, size and modification time are unchanged.
  // Failed checks are cached briefly too, preventing repeated slow launches.
  static Future<bool>? _versionCheck;
  static DateTime? _checkedAt;
  static DateTime? _modified;
  static int? _size;
  static String? _binaryPath;

  static Future<bool> enginePresent() async {
    if (!Platform.isWindows) return false;
    final path = enginePath(Platform.resolvedExecutable);
    try {
      final info = await File(path).stat();
      if (info.type != FileSystemEntityType.file) {
        _versionCheck = null;
        return false;
      }
      final now = DateTime.now();
      if (_versionCheck != null &&
          _binaryPath == path &&
          _modified == info.modified &&
          _size == info.size &&
          _checkedAt != null &&
          now.difference(_checkedAt!) < const Duration(seconds: 60)) {
        return await _versionCheck!;
      }
      _binaryPath = path;
      _modified = info.modified;
      _size = info.size;
      _checkedAt = now;
      _versionCheck = _verifyVersion(path);
      return await _versionCheck!;
    } catch (_) {
      _versionCheck = null;
      return false;
    }
  }

  static Future<bool> _verifyVersion(String path) async {
    try {
      final result = await Process.run(
        path, ['version'], runInShell: false,
      ).timeout(const Duration(seconds: 6));
      final output = result.stdout.toString();
      return result.exitCode == 0 && output.startsWith('Xray ') &&
          RegExp(r'\\b26\\.11\\.9\\b').hasMatch(output);
    } catch (_) {
      return false;
    }
  }

  /// Xray-core validates its JSON from stdin. No credential-bearing temp
  /// files or command-line arguments; output is discarded without logging.
  static Future<bool> checkInMemory(Map<String, dynamic> config) async {
    if (!await enginePresent()) return false;
    Process? child;
    try {
      child = await Process.start(
        enginePath(Platform.resolvedExecutable),
        ['run', '-test', '-config', 'stdin:'],
        runInShell: false,
      ).timeout(const Duration(seconds: 8));
      final stdoutDrain = child.stdout.drain<void>();
      final stderrDrain = child.stderr.drain<void>();
      child.stdin.add(utf8.encode(jsonEncode(config)));
      await child.stdin.close();
      final exit = await child.exitCode.timeout(const Duration(seconds: 10));
      await Future.wait([stdoutDrain, stderrDrain]);
      return exit == 0;
    } catch (_) {
      child?.kill();
      return false;
    }
  }
}
