import 'dart:convert';

/// Strict preflight for panel-issued Mieru profiles on Android.
///
/// This is deliberately separate from native engine readiness. A valid
/// profile does not imply that an Android VPN transport has been installed.
class AndroidMieruProfile {
  const AndroidMieruProfile._();

  static Map<String, dynamic> validate(Map<String, dynamic> item) {
    final raw = item['config'];
    Map<String, dynamic> config;
    if (raw is String) {
      if (raw.length > 262144) {
        throw const FormatException('MIERU_PROFILE_TOO_LARGE');
      }
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('MIERU_PROFILE_INVALID');
      }
      config = decoded;
    } else if (raw is Map<String, dynamic>) {
      config = Map<String, dynamic>.from(raw);
    } else {
      throw const FormatException('MIERU_PROFILE_MISSING');
    }

    // Only pass the Mieru-native profile to a future dedicated engine.
    // Never execute arbitrary app-level VPN routing from a panel payload.
    if (config.isEmpty || config.keys.any((key) =>
        const {'inbounds', 'outbounds', 'route', 'dns', 'experimental'}
            .contains(key))) {
      throw const FormatException('MIERU_PROFILE_INVALID');
    }
    return config;
  }
}
