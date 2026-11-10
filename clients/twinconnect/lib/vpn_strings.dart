import 'app_strings.dart';

extension VpnStrings on AppStrings {
  String get vpnSettingsTitle => pick('تنظیمات VPN', 'VPN settings');
  String get vpnPolicyOnly => pick(
    'موتور اتصال هنوز فعال نیست.',
    'Connection engine is not active.',
  );
  String get vpnPlatformStatus => pick('وضعیت موتور', 'Engine status');
  String get vpnEngineUnavailable => pick(
    'نصب نیست',
    'Not installed',
  );
  String get vpnEngineAvailable => pick(
    'آماده',
    'Ready',
  );
  String get vpnFullTunnel => pick('تمام دستگاه', 'Entire device');
  String get vpnFullTunnelHint => pick(
    'ترافیک دستگاه از VPN عبور می‌کند.',
    'Route traffic through VPN.',
  );
  String get vpnOnlyApps => pick('فقط برنامه‌های انتخابی', 'Only selected apps');
  String get vpnOnlyAppsHint => pick(
    'برنامه‌های دیگر از شبکه معمولی استفاده می‌کنند؛ در حالت قفل سراسری ممکن است اینترنتشان قطع شود.',
    'Other apps use the normal network; system lockdown may block them instead.',
  );
  String get vpnExceptApps => pick('همه به‌جز برنامه‌های انتخابی', 'All except selected apps');
  String get vpnExceptAppsHint => pick(
    'برنامه‌های استثناشده از VPN خارج می‌شوند و ممکن است IP واقعی را ببینند.',
    'Excluded apps bypass the VPN and may reveal your regular IP.',
  );
  String get vpnRoutingTitle => pick('مسیر عبور ترافیک', 'Traffic routing');
  String get vpnAppSelectionUnavailable => pick(
    'فعلاً پشتیبانی نمی‌شود',
    'Not supported yet',
  );
  String get vpnAppIds => pick('برنامه‌های انتخابی', 'Selected apps');
  String get vpnAppIdLabel => pick('شناسه برنامه', 'App identifier');
  String get vpnAndroidHint => pick('مثال: org.telegram.messenger', 'Example: org.telegram.messenger');
  String get vpnWindowsHint => pick(
    'مثال: مسیر کامل فایل EXE',
    'Example: full EXE application path',
  );
  String get vpnAddApp => pick('افزودن برنامه', 'Add app');
  String get vpnRemoveApp => pick('حذف از فهرست', 'Remove from list');
  String get vpnAppPickerNote => pick(
    'شناسه برنامه را وارد کنید.',
    'Enter app identifier.',
  );
  String get vpnSecurityTitle => pick('امنیت', 'Security');
  String get vpnKillSwitch => pick('Kill Switch', 'Kill switch');
  String get vpnKillSwitchSubtitle => pick(
    'قطع اینترنت هنگام قطع VPN',
    'Blocks internet if VPN disconnects',
  );
  String get vpnKillSwitchOff => pick(
    'Kill Switch: غیرفعال',
    'Kill switch: Off',
  );
  String get vpnKillSwitchOn => pick(
    'Kill Switch: فعال',
    'Kill switch: On',
  );
  String get vpnDnsProtected => pick('حفاظت DNS', 'Protect DNS requests');
  String get vpnDnsHint => pick(
    'جلوگیری از نشت DNS',
    'Prevent DNS leaks',
  );
  String get vpnIpv6Protected => pick('حفاظت IPv6', 'IPv6 leak protection');
  String get vpnIpv6Hint => pick(
    'جلوگیری از نشت IPv6',
    'Prevent IPv6 leaks',
  );
  String get vpnAllowLan => pick('اجازه دسترسی به شبکه محلی', 'Allow local network access');
  String get vpnAllowLanHint => pick(
    'دسترسی به دستگاه‌های محلی',
    'Access local devices',
  );
  String get vpnAutomationTitle => pick('اتصال هوشمند', 'Smart connection');
  String get vpnAutoReconnect => pick('اتصال مجدد خودکار', 'Auto reconnect');
  String get vpnAutoConnect => pick('اتصال هنگام اجرای برنامه', 'Connect on launch');
  String get vpnAutoSelectServer => pick('انتخاب خودکار سرور', 'Auto-select server');
  String get vpnNotConfigured => pick(
    'ابتدا وارد شوید.',
    'Sign in first.',
  );
  String get vpnSave => pick('ذخیره تنظیمات', 'Save settings');
  String get vpnSaved => pick(
    'تنظیمات ذخیره شد',
    'Settings saved',
  );
  String get vpnSaveError => pick('ذخیره نشد', 'Could not save');
  String get vpnPlatformAndroid => 'Android';
  String get vpnPlatformWindows => 'Windows';
  String get vpnPlatformIos => 'iOS';
  String get vpnPlatformMacos => 'macOS';
  String get vpnPlatformOther => pick('پلتفرم آزمایشی', 'Preview platform');
  String get vpnDraftProblems => pick('موارد نیازمند اصلاح', 'Settings to correct');
  String vpnProblem(String code) {
    switch (code) {
      case 'PER_APP_REQUIRES_MANAGED_OR_UNAVAILABLE':
        return vpnAppSelectionUnavailable;
      case 'NO_SELECTED_APPS':
        return pick('حداقل یک برنامه انتخاب کنید.', 'Select at least one app.');
      case 'DUPLICATE_APPS':
        return pick('برنامه تکراری است.', 'Duplicate app identifier.');
      case 'TOO_MANY_APPS':
        return pick('حداکثر ۱۰۰ برنامه مجاز است.', 'Select at most 100 apps.');
      case 'INVALID_APP_IDENTIFIER':
        return pick('شناسه یکی از برنامه‌ها معتبر نیست.', 'An app identifier is invalid.');
      case 'STRICT_REQUIRES_PROTECTED_DNS':
        return pick('Kill Switch سخت‌گیرانه به حفاظت DNS نیاز دارد.', 'Strict kill switch requires DNS protection.');
      case 'STRICT_REQUIRES_IPV6_GUARD':
        return pick('Kill Switch سخت‌گیرانه به حفاظت IPv6 نیاز دارد.', 'Strict kill switch requires IPv6 protection.');
      default:
        return pick('تنظیمات نیاز به بررسی دارد.', 'Settings require review.');
    }
  }
}
