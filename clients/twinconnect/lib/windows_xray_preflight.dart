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

  static Future<bool> enginePresent() async {
    if (!Platform.isWindows) return false;
    final path = enginePath(Platform.resolvedExecutable);
    if (!await File(path).exists()) return false;
    try {
      final result = await Process.run(
        path, ['version'], runInShell: false,
      ).timeout(const Duration(seconds: 6));
      final output = result.stdout.toString();
      return result.exitCode == 0 && output.startsWith('Xray ');
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
