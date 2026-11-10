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

  static Future<bool> enginePresent() async {
    if (!Platform.isWindows) return false;
    final binary = File(enginePath(Platform.resolvedExecutable));
    if (!await binary.exists()) return false;
    try {
      final result = await Process.run(binary.path, ['version'],
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
