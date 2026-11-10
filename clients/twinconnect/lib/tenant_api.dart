import 'dart:convert';
import 'dart:io';

import 'tenant_models.dart';
import 'protocols.dart';

/// A fail-closed directory client. The vendor sees ONLY a tenant namespace.
/// Username and bearer share token go directly to the licensed installation.
class TenantApi {
  TenantApi({required this.vendorOrigin});

  final Uri vendorOrigin;

  static const String configuredVendor =
      String.fromEnvironment('TWINCONNECT_DIRECTORY_URL', defaultValue: '');

  factory TenantApi.fromBuildConfig() {
    if (configuredVendor.isEmpty) {
      throw const FormatException(
        'DIRECTORY_NOT_CONFIGURED',
      );
    }
    return TenantApi(vendorOrigin: parseDirectoryOrigin(configuredVendor));
  }

  Future<PanelDirectoryEntry> resolve(String namespace) async {
    final url = vendorOrigin.resolve(
      '/v1/app/resolve/${Uri.encodeComponent(namespace)}',
    );
    final map = await _requestJson(url);
    final entry = PanelDirectoryEntry.fromJson(map);
    if (entry.namespace != namespace) {
      throw const FormatException('NAMESPACE_MISMATCH');
    }
    return entry;
  }

  Future<BrandPreview> loadBrand({
    required PanelDirectoryEntry panel,
    required String username,
    required String shareToken,
  }) async {
    final url = panel.apiOrigin.resolve(
      '/v1/central-app/public/brand-preview',
    );
    final data = await _requestJson(
      url,
      payload: {
        'account_username': username.trim(),
        'share_token': shareToken,
      },
    );
    final brand = BrandPreview.fromJson(data);
    if (brand.namespace != panel.namespace) {
      throw const FormatException('BRAND_MISMATCH');
    }
    if (brand.ownerType == 'reseller' &&
        (brand.appUsernamePrefix.isEmpty ||
            !username.trim().startsWith(brand.appUsernamePrefix))) {
      throw const FormatException('RESELLER_PREFIX_MISMATCH');
    }
    return brand;
  }


  Future<PanelProtocolCatalog> loadProtocolCatalog({
    required PanelDirectoryEntry panel,
    required String username,
    required String shareToken,
  }) async {
    final url = panel.apiOrigin.resolve('/v1/central-app/public/protocols');
    final result = await _requestJson(
      url,
      payload: {
        'account_username': username.trim(),
        'share_token': shareToken,
      },
    );
    final catalog = PanelProtocolCatalog.fromJson(result);
    if (catalog.namespace != panel.namespace) {
      throw const FormatException('NAMESPACE_MISMATCH');
    }
    return catalog;
  }

  /// Returns credential-bearing profiles *only* after the OS native engine
  /// explicitly advertises that it supports the requested protocol.
  /// The current preview does not have these engines and will never fetch
  /// private profiles. Never put profiles in shared preferences or logs.
  Future<ClientProtocolProfiles> loadNativeProfiles({
    required PanelDirectoryEntry panel,
    required String username,
    required String shareToken,
    required VpnProtocolDefinition protocol,
    required NativeProtocolReadiness native,
  }) async {
    if (!native.supports(protocol.code)) {
      throw const TenantApiException('ENGINE_NOT_READY');
    }
    final url = panel.apiOrigin.resolve('/v1/central-app/public/profiles');
    final result = await _requestJson(
      url,
      maxBytes: 1024 * 1024,
      payload: {
        'account_username': username.trim(),
        'share_token': shareToken,
        'protocol': protocol.code,
      },
    );
    final profiles = ClientProtocolProfiles.fromJson(result);
    if (profiles.namespace != panel.namespace ||
        profiles.protocol.code != protocol.code) {
      throw const FormatException('PROFILE_PROTOCOL_MISMATCH');
    }
    return profiles;
  }

  Future<Map<String, dynamic>> _requestJson(
    Uri url, {
    Map<String, dynamic>? payload,
    int maxBytes = 32768,
  }) async {
    if (url.scheme != 'https') {
      throw const FormatException('INSECURE_CONNECTION');
    }
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 7);
    try {
      final request = payload == null
          ? await client.getUrl(url).timeout(const Duration(seconds: 10))
          : await client.postUrl(url).timeout(const Duration(seconds: 10));
      request.followRedirects = false;
      request.headers.set(HttpHeaders.acceptHeader, 'application/json');
      if (payload != null) {
        request.headers.contentType = ContentType.json;
        request.write(jsonEncode(payload));
      }
      final response = await request.close().timeout(
        const Duration(seconds: 15),
      );
      if (response.statusCode != HttpStatus.ok) {
        if (response.statusCode == HttpStatus.notFound) {
          throw const TenantApiException('PANEL_NOT_FOUND');
        }
        if (response.statusCode == HttpStatus.forbidden) {
          throw const TenantApiException(
            'APP_NOT_AUTHORIZED',
          );
        }
        throw TenantApiException(
          'SERVER_ERROR',
        );
      }
      final bytes = <int>[];
      await for (final chunk in response.timeout(const Duration(seconds: 15))) {
        if (bytes.length + chunk.length > maxBytes) {
          throw const TenantApiException('RESPONSE_TOO_LARGE');
        }
        bytes.addAll(chunk);
      }
      final decoded = jsonDecode(utf8.decode(bytes));
      if (decoded is! Map<String, dynamic>) {
        throw const TenantApiException('INVALID_SERVER_RESPONSE');
      }
      return decoded;
    } on SocketException {
      throw const TenantApiException('NETWORK_UNAVAILABLE');
    } on HandshakeException {
      throw const TenantApiException('INVALID_TLS');
    } finally {
      client.close(force: true);
    }
  }
}

class TenantApiException implements Exception {
  const TenantApiException(this.message);
  final String message;
  @override
  String toString() => message;
}
