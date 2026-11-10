import 'app_strings.dart';

extension VpnStrings on AppStrings {
  String get vpnSettingsTitle => pick('تنظیمات پیشرفته VPN', 'Advanced VPN settings');
  String get vpnPolicyOnly => pick(
    'این نسخه فقط تنظیمات را ذخیره می‌کند. هیچ تونل یا Kill Switch فعالی ایجاد نشده است.',
    'This preview only saves preferences. No VPN tunnel or kill switch is active.',
  );
  String get vpnPlatformStatus => pick('وضعیت موتور دستگاه', 'Device engine status');
  String get vpnEngineUnavailable => pick(
    'موتور VPN نصب یا تأیید نشده است؛ حفاظت غیرفعال است.',
    'The native VPN engine is not available or verified. Protection is OFF.',
  );
  String get vpnEngineAvailable => pick(
    'موتور شناسایی شد؛ هر قابلیت باید جداگانه تأیید شود.',
    'Native engine detected; individual protections require verification.',
  );
  String get vpnFullTunnel => pick('تمام دستگاه', 'Entire device');
  String get vpnFullTunnelHint => pick(
    'ترافیک دستگاه از تونل VPN عبور می‌کند.',
    'Route device traffic through the VPN tunnel.',
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
    'انتخاب برنامه در نسخه مصرف‌کننده این سیستم‌عامل پشتیبانی نمی‌شود؛ در دستگاه‌های مدیریت‌شده ممکن است به MDM نیاز باشد.',
    'Per-app selection is unavailable in this consumer build; managed devices may require MDM.',
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
    'فعلاً شناسه برنامه را دستی وارد کنید. فهرست برنامه‌های نصب‌شده پس از اتصال ماژول بومی افزوده می‌شود.',
    'Enter app identifiers manually for now. Installed-app picking needs a native module.',
  );
  String get vpnSecurityTitle => pick('امنیت و جلوگیری از نشت', 'Security and leak protection');
  String get vpnKillSwitch => pick('درخواست Kill Switch سخت‌گیرانه', 'Request strict kill switch');
  String get vpnKillSwitchSubtitle => pick(
    'تا تأیید قفل شبکه توسط سیستم‌عامل، این گزینه حفاظت فعالی ایجاد نمی‌کند.',
    'This cannot block traffic until OS-level lockdown is confirmed.',
  );
  String get vpnKillSwitchOff => pick(
    'وضعیت واقعی Kill Switch: غیرفعال',
    'Actual kill switch: NOT ACTIVE',
  );
  String get vpnKillSwitchOn => pick(
    'قفل شبکه توسط موتور بومی تأیید شده است.',
    'Network lockdown verified by the native engine.',
  );
  String get vpnDnsProtected => pick('حفاظت DNS', 'Protect DNS requests');
  String get vpnDnsHint => pick(
    'DNS فقط داخل تونل یا مسدود؛ جلوگیری از درخواست‌های مستقیم.',
    'DNS must travel inside the tunnel or be blocked.',
  );
  String get vpnIpv6Protected => pick('حفاظت IPv6', 'IPv6 leak protection');
  String get vpnIpv6Hint => pick(
    'IPv6 نیز تونل شود یا هنگام عدم پشتیبانی مسدود گردد.',
    'Tunnel IPv6 or block it when unsupported.',
  );
  String get vpnAllowLan => pick('اجازه دسترسی به شبکه محلی', 'Allow local network access');
  String get vpnAllowLanHint => pick(
    'برای پرینتر و دستگاه‌های محلی؛ یک استثنای شبکه محسوب می‌شود.',
    'Allow printers and LAN devices; creates a routing exception.',
  );
  String get vpnAutomationTitle => pick('اتصال هوشمند', 'Smart connection');
  String get vpnAutoReconnect => pick('اتصال مجدد خودکار', 'Auto reconnect');
  String get vpnAutoConnect => pick('اتصال خودکار هنگام اجرای برنامه', 'Auto connect on app start');
  String get vpnAutoSelectServer => pick('انتخاب خودکار سرور مناسب', 'Automatically select a suitable server');
  String get vpnNotConfigured => pick(
    'ابتدا حساب خود را شناسایی کنید تا تنظیمات اختصاصی آن ذخیره شود.',
    'Identify your account before saving account-specific settings.',
  );
  String get vpnSave => pick('ذخیره تنظیمات پیشنهادی', 'Save desired settings');
  String get vpnSaved => pick(
    'تنظیمات ذخیره شد؛ تا راه‌اندازی موتور بومی اجرا نمی‌شود.',
    'Preferences saved; they will not take effect until the native engine is ready.',
  );
  String get vpnSaveError => pick('ذخیره تنظیمات ناموفق بود.', 'Could not save preferences.');
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
