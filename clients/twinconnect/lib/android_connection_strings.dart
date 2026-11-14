import 'app_strings.dart';

extension AndroidConnectionStrings on AppStrings {
  String get wireGuardNativeTitle =>
      pick('اتصال بومی WireGuard اندروید', 'Android native WireGuard');
  String get wireGuardReady =>
      pick('موتور نصب شده؛ برای اتصال یک سرور انتخاب کنید.', 'Engine installed; choose a server to connect.');
  String get wireGuardUnavailable =>
      pick('موتور WireGuard این نسخه دستگاه هنوز آماده نیست.', 'WireGuard engine is not available in this build.');
  String get wireGuardConnect =>
      pick('اتصال آزمایشی WireGuard', 'Connect WireGuard (preview)');
  String get wireGuardDisconnect =>
      pick('قطع تونل WireGuard', 'Disconnect WireGuard');
  String get wireGuardChecking =>
      pick('در حال بررسی وضعیت...', 'Checking tunnel status...');
  String get wireGuardActiveUnverified => pick(
    'رابط VPN ایجاد شده، اما پاسخ سرور و امن‌بودن اینترنت هنوز تأیید نشده است.',
    'VPN tunnel interface is up; peer handshake and internet protection have not been verified.',
  );
  String get wireGuardDown =>
      pick('تونل غیرفعال است.', 'Tunnel is disconnected.');
  String get wireGuardChooseServer =>
      pick('سرور WireGuard را انتخاب کنید', 'Choose a WireGuard server');
  String get wireGuardNoConfigs =>
      pick('هیچ فایل WireGuard معتبری در اشتراک پیدا نشد.', 'No usable WireGuard configuration is available.');
  String get wireGuardConnectionFailed =>
      pick('راه‌اندازی تونل انجام نشد. تنظیمات امنیتی یا کانفیگ را بررسی کنید.', 'The tunnel could not start. Check VPN policy and configuration.');
  String get wireGuardPolicyBlocked => pick(
    'تنظیمات انتخابی هنوز روی اندروید قابل اجرا نیستند. در تنظیمات VPN حالت کل دستگاه و حفاظت DNS/IPv6 را انتخاب کنید و اتصال خودکار، انتخاب برنامه و استثناهای شبکه را غیرفعال کنید.',
    'This policy cannot yet run on Android. Choose full tunnel with DNS/IPv6 protection and disable auto-connect, auto-reconnect, per-app rules and LAN exceptions.',
  );
  String get wireGuardPermissionDenied =>
      pick('اجازه ساخت VPN در اندروید داده نشد.', 'Android VPN permission was denied.');
  String get wireGuardIpv6Required => pick(
    'کانفیگ فاقد مسیر کامل IPv6 است؛ برای جلوگیری از نشت اتصال رد شد.',
    'The profile lacks a full IPv6 route; connection was blocked to prevent leaks.',
  );
  String get wireGuardDnsRequired =>
      pick('کانفیگ DNS محافظت‌شده ندارد.', 'No protected DNS is configured in the profile.');
  String get wireGuardOsLockdown =>
      pick('برای Kill Switch سخت‌گیرانه، گزینه Block connections without VPN را در تنظیمات اندروید فعال کنید.', 'Enable Android "Block connections without VPN" to use strict Kill Switch.');
  String get ciscoNativeTitle =>
      pick('Cisco / OpenConnect', 'Cisco / OpenConnect');
  String get ciscoPending => pick(
    'موتور اختصاصی OpenConnect و انتقال بسته‌های VPN هنوز به اپ اضافه نشده؛ کانفیگ Cisco با WireGuard اجرا نمی‌شود.',
    'The OpenConnect engine and packet tunnel are not yet integrated. Cisco cannot run through WireGuard.',
  );
  String nativeError(String code) {
    switch (code) {
      case 'VPN_PERMISSION_DENIED':
      case 'VPN_PERMISSION_FAILED':
      case 'VPN_PERMISSION_REQUIRED':
        return wireGuardPermissionDenied;
      case 'WIREGUARD_CONFIG_PARSE_FAILED':
      case 'PROFILE_INVALID':
      case 'PRIVATE_KEY_MISSING':
      case 'VPN_ADDRESS_MISSING':
        return pick('کانفیگ دریافتی WireGuard معتبر نیست. کد خطا را برای پشتیبانی ارسال کنید.',
                    'WireGuard profile is invalid. Share the error code with support.');
      case 'WIREGUARD_NATIVE_START_FAILED':
      case 'TUNNEL_NOT_ESTABLISHED':
        return pick('موتور بومی WireGuard نتوانست تونل را فعال کند. کد خطا را بررسی کنید.',
                    'WireGuard native backend could not activate the tunnel. Check the error code.');
      case 'IPV4_DEFAULT_ROUTE_MISSING':
        return pick('مسیر پیش‌فرض IPv4 در کانفیگ WireGuard وجود ندارد.',
                    'WireGuard profile is missing the IPv4 default route.');
      case 'IPV6_DEFAULT_ROUTE_MISSING':
        return wireGuardIpv6Required;
      case 'VPN_DNS_MISSING':
        return wireGuardDnsRequired;
      case 'OS_LOCKDOWN_NOT_ENABLED':
      case 'KILL_SWITCH_NOT_ENFORCED':
        return wireGuardOsLockdown;
      case 'ENGINE_NOT_READY':
      case 'PROTOCOL_ENGINE_NOT_READY':
      case 'NATIVE_ENGINE_LINK_FAILED':
        return wireGuardUnavailable;
      case 'AUTO_RECONNECT_UNAVAILABLE':
      case 'AUTO_RECONNECT_NOT_VERIFIED':
      case 'PER_APP_ROUTING_NOT_IMPLEMENTED':
      case 'INCLUDE_APPS_UNSUPPORTED':
      case 'EXCLUDE_APPS_UNSUPPORTED':
      case 'DNS_PROTECTION_UNAVAILABLE':
      case 'IPV6_PROTECTION_UNAVAILABLE':
      case 'AUTO_CONNECT_UNAVAILABLE':
      case 'LAN_BYPASS_NOT_IMPLEMENTED':
        return wireGuardPolicyBlocked;
      default:
        return wireGuardConnectionFailed;
    }
  }
}
