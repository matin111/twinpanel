import 'dart:convert';

import 'mieru_client_profile.dart';

/// Android-specific entry point for panel-issued Mieru profiles.
///
/// Reuses the production Windows validator instead of accepting arbitrary
/// JSON as a usable native configuration. A validated profile is not proof
/// that the Android Mieru engine or VpnService is installed.
class AndroidMieruProfile {
  const AndroidMieruProfile._();

  static MieruClientProfile validate(Map<String, dynamic> item) {
    final raw = item['config'];
    if (raw is String && raw.length > 262144) {
      throw const FormatException('MIERU_PROFILE_TOO_LARGE');
    }
    if (raw is Map) {
      final encoded = jsonEncode(raw);
      if (encoded.length > 262144) {
        throw const FormatException('MIERU_PROFILE_TOO_LARGE');
      }
      return MieruClientProfile.fromItem({
        ...item,
        'config': encoded,
      });
    }
    if (raw is! String) {
      throw const FormatException('MIERU_PROFILE_MISSING');
    }
    return MieruClientProfile.fromItem(item);
  }
}
