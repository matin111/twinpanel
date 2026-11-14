import 'dart:io';

import 'package:shared_preferences/shared_preferences.dart';

/// Per-application routing for TwinConnect's Windows sing-box TUN.
/// This is separate from the WFP Kill Switch and from WinINET system proxy.
enum WindowsAppRoutingMode { fullTunnel, includeSelected, excludeSelected }

class WindowsAppRoutePolicy {
  const WindowsAppRoutePolicy({
    required this.mode,
    required this.applicationPaths,
  });

  static const modeKey = 'twinconnect_windows_app_routing_mode';
  static const appsKey = 'twinconnect_windows_app_routing_paths';

  final WindowsAppRoutingMode mode;
  final List<String> applicationPaths;

  static Future<WindowsAppRoutePolicy> load() async {
    final prefs = await SharedPreferences.getInstance();
    final value = prefs.getString(modeKey) ?? WindowsAppRoutingMode.fullTunnel.name;
    final mode = WindowsAppRoutingMode.values.firstWhere(
      (m) => m.name == value,
      orElse: () => WindowsAppRoutingMode.fullTunnel,
    );
    final paths = prefs.getStringList(appsKey) ?? <String>[];
    return WindowsAppRoutePolicy(mode: mode, applicationPaths: paths);
  }

  Future<void> persist() async {
    final prefs = await SharedPreferences.getInstance();
    if (mode != WindowsAppRoutingMode.fullTunnel && applicationPaths.isEmpty) {
      throw const FormatException('ROUTING_APPLICATION_REQUIRED');
    }
    validate();
    if (!await prefs.setStringList(appsKey, applicationPaths) ||
        !await prefs.setString(modeKey, mode.name)) {
      throw const FileSystemException('APP_ROUTING_SETTINGS_NOT_SAVED');
    }
  }

  void validate() {
    if (mode != WindowsAppRoutingMode.fullTunnel && applicationPaths.isEmpty) {
      throw const FormatException('ROUTING_APPLICATION_REQUIRED');
    }
    if (applicationPaths.length > 32 ||
        applicationPaths.toSet().length != applicationPaths.length) {
      throw const FormatException('APP_ROUTING_SELECTION_INVALID');
    }
    for (final path in applicationPaths) {
      if (path.isEmpty || !path.toLowerCase().endsWith('.exe') ||
          !RegExp(r'^[A-Za-z]:\\').hasMatch(path) ||
          path.contains('..') || path.contains('\n') || path.contains('\r')) {
        throw const FormatException('APP_ROUTING_PATH_INVALID');
      }
    }
  }

  /// Applied to a sing-box 1.14 Windows TUN configuration before its native
  /// engine parses and starts. Neither WFP policy nor global proxy is changed.
  /// Users must reconnect their TUN to apply an updated routing preference.
  void applyTo(Map<String, dynamic> config) {
    validate();
    if (mode == WindowsAppRoutingMode.fullTunnel) return;
    final route = config['route'];
    final outbound = config['outbounds'];
    if (route is! Map<String, dynamic> || outbound is! List ||
        !outbound.any((v) => v is Map && v['tag'] == 'proxy')) {
      throw const FormatException('APP_ROUTING_TUN_CONFIG_INVALID');
    }
    if (outbound.any((v) => v is Map && v['tag'] == 'direct')) {
      throw const FormatException('APP_ROUTING_DIRECT_TAG_CONFLICT');
    }
    final existingRules = route['rules'];
    if (existingRules is! List) {
      throw const FormatException('APP_ROUTING_RULES_MISSING');
    }
    outbound.add(<String, dynamic>{'type': 'direct', 'tag': 'direct'});
    // Must preserve DNS interception and IPv6 reject rules from the original
    // TUN config. Exact path matching avoids broad process-name collisions.
    final rule = <String, dynamic>{
      'process_path': applicationPaths,
      'action': 'route',
      'outbound': mode == WindowsAppRoutingMode.includeSelected
          ? 'proxy' : 'direct',
    };
    final index = existingRules.indexWhere((v) =>
        v is Map && v['action'] == 'sniff');
    existingRules.insert(index < 0 ? existingRules.length : index, rule);
    route['final'] = mode == WindowsAppRoutingMode.includeSelected
        ? 'direct' : 'proxy';
  }
}
