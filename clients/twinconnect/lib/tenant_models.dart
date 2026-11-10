/// Pure Dart models and username routing for the shared TwinPanel client.
///
/// Namespace extracts routing information ONLY; it must never be treated as
/// proof that a user owns a subscription.
class TenantIdentity {
  static final RegExp _userPattern = RegExp(
    r'^(TP[A-F0-9]{16})_(?:R[0-9A-F]+|A)_[A-Za-z0-9_.-]+$',
  );
  static final RegExp _namespace = RegExp(r'^TP[A-F0-9]{16}$');

  static String? namespaceFromUsername(String username) {
    final match = _userPattern.firstMatch(username.trim().toUpperCase());
    return match?.group(1);
  }

  static String parseNamespace(String username, String enteredCode) {
    final inferred = namespaceFromUsername(username);
    final supplied = enteredCode.trim().toUpperCase();
    if (supplied.isNotEmpty && !_namespace.hasMatch(supplied)) {
      throw const FormatException('شناسه پنل معتبر نیست.');
    }
    if (inferred != null && supplied.isNotEmpty && inferred != supplied) {
      throw const FormatException('شناسه پنل با پیشوند نام کاربری مطابقت ندارد.');
    }
    final result = inferred ?? supplied;
    if (result.isEmpty) {
      throw const FormatException(
        'نام کاربری پیشوند ندارد؛ شناسه پنل را هم وارد کنید.',
      );
    }
    return result;
  }
}

class SubscriptionInput {
  static final RegExp _tokenPattern = RegExp(r'^[A-Za-z0-9._~-]{5,180}$');

  static String tokenFromInput(String input) {
    final value = input.trim();
    if (value.isEmpty) {
      throw const FormatException('لینک اشتراک را وارد کنید.');
    }
    String token;
    if (value.contains('://')) {
      final parsed = Uri.tryParse(value);
      if (parsed == null || parsed.scheme != 'https' ||
          parsed.host.isEmpty || parsed.userInfo.isNotEmpty) {
        throw const FormatException('لینک اشتراک باید HTTPS باشد.');
      }
      final parts = parsed.pathSegments;
      if (parts.length != 3 || parts[0] != 'v1' || parts[1] != 'connect') {
        throw const FormatException('ساختار لینک اشتراک معتبر نیست.');
      }
      token = parts[2];
    } else {
      token = value;
    }
    if (!_tokenPattern.hasMatch(token)) {
      throw const FormatException('کد اشتراک معتبر نیست.');
    }
    return token;
  }
}

class PanelDirectoryEntry {
  const PanelDirectoryEntry({
    required this.namespace,
    required this.apiOrigin,
  });

  final String namespace;
  final Uri apiOrigin;

  factory PanelDirectoryEntry.fromJson(Map<String, dynamic> json) {
    final namespace = json['namespace'];
    final originText = json['api_origin'];
    if (namespace is! String || originText is! String) {
      throw const FormatException('پاسخ فهرست پنل‌ها ناقص است.');
    }
    return PanelDirectoryEntry(
      namespace: namespace.toUpperCase(),
      apiOrigin: _parseSecureOrigin(originText),
    );
  }
}

Uri parseDirectoryOrigin(String value) => _parseSecureOrigin(value);

Uri _parseSecureOrigin(String value) {
  final uri = Uri.tryParse(value.trim());
  if (uri == null || uri.scheme != 'https' ||
      uri.host.isEmpty || uri.userInfo.isNotEmpty ||
      uri.hasQuery || uri.hasFragment ||
      (uri.path.isNotEmpty && uri.path != '/') ||
      (uri.hasPort && uri.port != 443)) {
    throw const FormatException('آدرس HTTPS پنل معتبر نیست.');
  }
  final host = uri.host.toLowerCase();
  // Do not accept localhost, private literals, or single-label hosts.
  if (host == 'localhost' || host.endsWith('.localhost') ||
      host.endsWith('.local') || !host.contains('.')) {
    throw const FormatException('آدرس پنل عمومی نیست.');
  }
  return Uri(scheme: 'https', host: host);
}

class BrandPreview {
  const BrandPreview({
    required this.namespace,
    required this.brandName,
    required this.ownerType,
    required this.accountStatus,
    required this.appUsernamePrefix,
    this.telegramUrl,
    this.renewalUrl,
    this.websiteUrl,
    this.phone,
    this.supportText,
    this.logoUrl,
    this.primaryColor = '#7C3AED',
    this.secondaryColor = '#4F46E5',
  });

  final String namespace;
  final String brandName;
  final String ownerType;
  final String accountStatus;
  final String appUsernamePrefix;
  final String? telegramUrl;
  final String? renewalUrl;
  final String? websiteUrl;
  final String? phone;
  final String? supportText;
  final String? logoUrl;
  final String primaryColor;
  final String secondaryColor;

  factory BrandPreview.fromJson(Map<String, dynamic> json) {
    String field(String key, [String fallback = '']) {
      final value = json[key];
      return value is String && value.trim().isNotEmpty
          ? value.trim()
          : fallback;
    }

    String? optional(String key) {
      final value = field(key);
      return value.isEmpty ? null : value;
    }

    String color(String key, String fallback) {
      final value = field(key);
      return RegExp(r'^#[A-Fa-f0-9]{6}$').hasMatch(value) ? value : fallback;
    }

    return BrandPreview(
      namespace: field('namespace'),
      brandName: field('brand_name', 'TwinPanel'),
      ownerType: field('owner_type'),
      accountStatus: field('account_status', 'unknown'),
      appUsernamePrefix: field('app_username_prefix'),
      telegramUrl: optional('telegram_url'),
      renewalUrl: optional('renewal_url'),
      websiteUrl: optional('website_url'),
      phone: optional('support_phone'),
      supportText: optional('support_text'),
      logoUrl: optional('logo_url'),
      primaryColor: color('primary_color', '#7C3AED'),
      secondaryColor: color('secondary_color', '#4F46E5'),
    );
  }
}
