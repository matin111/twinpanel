import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// Discovery and config syntax validation for the bundled Windows engine.
///
/// This class DOES NOT run a tunnel, alter DNS, routes or Windows services.
/// It deliberately does not expose an enabled-protocol capability until a
/// separate supervised, leak-tested native TUN lifecycle is implemented.
class WindowsSingBoxPreflight {
  const WindowsSingBoxPreflight._();

  static const version = '1.14.4';

  static String enginePath(String appExecutable) {
    final base = File(appExecutable).parent.path;
    return '$base\\engines\\sing-box\\sing-box.exe';
  }

  // One version subprocess is enough per unchanged binary. Multiple parts
  // of the connect pipeline invoke this concurrently and sequentially.
  // Revalidate after 60s, or immediately when the executable changes.
  static Future<bool>? _versionCheck;
  static DateTime? _checkedAt;
  static DateTime? _binaryModified;
  static int? _binarySize;
  static String? _binaryPath;

  static Future<bool> enginePresent() async {
    if (!Platform.isWindows) return false;
    final binary = File(enginePath(Platform.resolvedExecutable));
    try {
      final stat = await binary.stat();
      if (stat.type != FileSystemEntityType.file) {
        _versionCheck = null;
        return false;
      }
      final now = DateTime.now();
      if (_versionCheck != null &&
          _binaryPath == binary.path &&
          _binaryModified == stat.modified &&
          _binarySize == stat.size &&
          _checkedAt != null &&
          now.difference(_checkedAt!) < const Duration(seconds: 60)) {
        return await _versionCheck!;
      }
      _binaryPath = binary.path;
      _binaryModified = stat.modified;
      _binarySize = stat.size;
      _checkedAt = now;
      _versionCheck = _verifyVersion(binary.path);
      return await _versionCheck!;
    } catch (_) {
      _versionCheck = null;
      return false;
    }
  }

  static Future<bool> _verifyVersion(String path) async {
    try {
      final result = await Process.run(path, ['version'],
          runInShell: false).timeout(const Duration(seconds: 6));
      return result.exitCode == 0 &&
          RegExp(r'\b1\.14\.4\b').hasMatch(result.stdout.toString());
    } catch (_) {
      return false;
    }
  }

  /// Sends credential-bearing config over stdin, never CLI arguments or disk.
  /// The engine itself is only asked to validate syntax; no routes are applied.
  /// No stdout/stderr content is returned or logged, to avoid secret exposure.
  static Future<bool> checkInMemory(Map<String, dynamic> config) async {
    if (!await enginePresent()) return false;
    final executable = enginePath(Platform.resolvedExecutable);
    Process? process;
    try {
      process = await Process.start(executable, ['check', '-c', 'stdin'],
        runInShell: false);
      // Drain outputs silently. Never serialize profile secrets to logs.
      final stdoutDrain = process.stdout.drain<void>();
      final stderrDrain = process.stderr.drain<void>();
      process.stdin.add(utf8.encode(jsonEncode(config)));
      await process.stdin.close();
      final exit = await process.exitCode.timeout(const Duration(seconds: 10));
      await Future.wait([stdoutDrain, stderrDrain]);
      return exit == 0;
    } catch (_) {
      process?.kill();
      return false;
    }
  }
}
