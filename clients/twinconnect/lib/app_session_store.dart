import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'tenant_models.dart';

/// Windows uses the OS-protected secure-storage plugin. Credentials and
/// session tokens are never placed in ordinary preferences or build artifacts.
/// This storage survives an in-place upgrade with the same app identity.
class PersistedAppSession {
  const PersistedAppSession({
    required this.username,
    required this.sessionToken,
    required this.brand,
    this.refreshToken,
  });

  final String username;
  final String sessionToken;
  final BrandPreview brand;
  final String? refreshToken;
}

class AppSessionStore {
  const AppSessionStore();
  static const _secure = FlutterSecureStorage();
  static const _sessionKey = 'twinconnect_app_session_v1';
  static const _usernameKey = 'twinconnect_last_username_v1';

  Future<PersistedAppSession?> read() async {
    try {
      final value = await _secure.read(key: _sessionKey);
      if (value == null) return null;
      final parsed = jsonDecode(value);
      if (parsed is! Map<String, dynamic>) return null;
      final username = parsed['username'];
      final token = parsed['token'];
      final brandData = parsed['brand'];
      if (username is! String || username.isEmpty ||
          token is! String || token.length < 40 ||
          brandData is! Map<String, dynamic>) { return null; }
      final brand = BrandPreview.fromJson(brandData);
      if (brand.namespace.isEmpty ||
          TenantIdentity.namespaceFromUsername(username) != brand.namespace) {
        return null;
      }
      final refresh = parsed['refresh_token'];
      return PersistedAppSession(
        username: username, sessionToken: token, brand: brand,
        refreshToken: refresh is String && refresh.length >= 40 ? refresh : null);
    } catch (_) {
      // A corrupted or unavailable OS vault must never bypass authentication.
      return null;
    }
  }

  Future<void> save({
    required String username,
    required String sessionToken,
    required BrandPreview brand,
    String? refreshToken,
  }) async {
    // Save username only in ordinary preferences, never secrets.
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_usernameKey, username);
    await _secure.write(
      key: _sessionKey,
      value: jsonEncode({
        'username': username,
        'token': sessionToken,
        if (refreshToken != null) 'refresh_token': refreshToken,
        'brand': brand.toJson(),
      }),
    );
  }

  Future<String?> lastUsername() async {
    try {
      return (await SharedPreferences.getInstance()).getString(_usernameKey);
    } catch (_) {
      return null;
    }
  }

  Future<void> clearSession() async {
    await _secure.delete(key: _sessionKey);
  }
}
