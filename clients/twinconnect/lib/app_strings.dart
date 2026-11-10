import 'package:flutter/widgets.dart';

/// All static user-facing text is centralized so RTL/LTR UI stays consistent.
/// Names, contact details, and URLs from the reseller are not translated.
class AppStrings {
  const AppStrings(this.locale);

  final Locale locale;

  static AppStrings of(BuildContext context) =>
      AppStrings(Localizations.localeOf(context));

  bool get isFa => locale.languageCode.toLowerCase() == 'fa';

  String pick(String fa, String en) => isFa ? fa : en;

  String get language => pick('زبان', 'Language');
  String get systemLanguage => pick('خودکار (زبان دستگاه)', 'Automatic (device)');
  String get persianLanguage => 'فارسی';
  String get englishLanguage => 'English';
  String get appTitle => 'TwinConnect';
  String get appHeadline => pick(
    'اپلیکیشن مرکزی چندبرندی',
    'One app, many brands',
  );
  String get appIntroduction => pick(
    'برند و اطلاعات پشتیبانی مستقیماً از پنل دارای لایسنس شما دریافت می‌شود.',
    'Your brand and support details are retrieved directly from your licensed panel.',
  );
  String get identifyAccount => pick('شناسایی حساب', 'Identify your account');
  String get accountUsername => pick('نام کاربری کامل', 'Full username');
  String get accountUsernameHint => 'TP0123456789ABCDEF_R2A_ali';
  String get subscription => pick('لینک یا کد اشتراک', 'Subscription link or code');
  String get subscriptionHint => 'https://panel.example.com/v1/connect/…';
  String get tenantCode => pick(
    'شناسه پنل (برای حساب‌های بدون پیشوند)',
    'Panel code (if your username has no prefix)',
  );
  String get tenantCodeHint => 'TP0123456789ABCDEF';
  String get usernameRequired => pick('نام کاربری لازم است.', 'Enter your username.');
  String get subscriptionRequired => pick(
    'لینک اشتراک لازم است.',
    'Enter your subscription link or code.',
  );
  String get identifyButton => pick('دریافت اطلاعات برند', 'Load brand information');
  String get supportTelegram => pick('پشتیبانی تلگرام', 'Telegram support');
  String get renewalLink => pick('لینک تمدید', 'Renew subscription');
  String get supportPhone => pick('شماره تماس', 'Phone support');
  String get website => pick('وب‌سایت', 'Website');
  String get statusActive => pick('اشتراک فعال', 'Active subscription');
  String get statusExpired => pick('اشتراک منقضی', 'Expired subscription');
  String statusOther(String value) => pick('وضعیت: ', 'Status: ') + value;
  String get connectionDisabled => pick(
    'اتصال VPN (در دست توسعه)',
    'Connect VPN (coming soon)',
  );
  String get developmentNotice => pick(
    'این نسخه فقط شناسایی پنل و نمایش برند را انجام می‌دهد. '
    'اتصال واقعی VPN پس از تکمیل موتورهای بومی فعال خواهد شد.',
    'This preview only identifies your panel and shows your brand. '
    'VPN connections will become available after the native engines are implemented.',
  );
  String get engineNotReady => pick(
    'نسخه اولیه: بدون موتور اتصال VPN',
    'Preview: VPN engine is not yet available',
  );
  String copied(String label) => pick(
    '$label کپی شد.',
    '$label copied.',
  );
  String copyTooltip(String label) => pick(
    'کپی $label',
    'Copy $label',
  );
  String get genericError => pick(
    'امکان دریافت اطلاعات پنل وجود ندارد.',
    'Unable to retrieve panel information.',
  );

  String error(String code) {
    switch (code) {
      case 'INVALID_TENANT_CODE':
        return pick('شناسه پنل معتبر نیست.', 'Invalid panel code.');
      case 'TENANT_MISMATCH':
        return pick(
          'شناسه پنل با پیشوند نام کاربری مطابقت ندارد.',
          'Panel code does not match the username prefix.',
        );
      case 'TENANT_REQUIRED':
        return pick(
          'نام کاربری پیشوند ندارد؛ شناسه پنل را هم وارد کنید.',
          'Enter a panel code when your username has no tenant prefix.',
        );
      case 'SUBSCRIPTION_REQUIRED':
        return subscriptionRequired;
      case 'INVALID_SUBSCRIPTION_URL':
        return pick('لینک اشتراک HTTPS معتبر نیست.', 'Enter a valid HTTPS subscription link.');
      case 'INVALID_SUBSCRIPTION_TOKEN':
        return pick('کد اشتراک معتبر نیست.', 'Invalid subscription code.');
      case 'UNSAFE_PANEL_ORIGIN':
        return pick('آدرس امن پنل معتبر نیست.', 'Invalid secure panel address.');
      case 'INVALID_DIRECTORY_RESPONSE':
        return pick('پاسخ فهرست پنل‌ها معتبر نیست.', 'Invalid panel directory response.');
      case 'DIRECTORY_NOT_CONFIGURED':
        return pick(
          'آدرس سرویس مرکزی برای این نسخه تنظیم نشده است.',
          'The central directory is not configured for this app build.',
        );
      case 'NAMESPACE_MISMATCH':
        return pick(
          'شناسه پاسخ‌داده‌شده با پنل درخواستی متفاوت است.',
          'The returned panel does not match your panel code.',
        );
      case 'BRAND_MISMATCH':
        return pick(
          'برند پاسخ‌داده‌شده متعلق به این پنل نیست.',
          'Brand details do not belong to the selected panel.',
        );
      case 'RESELLER_PREFIX_MISMATCH':
        return pick(
          'پیشوند حساب با نماینده مطابقت ندارد.',
          'The username does not match this reseller.',
        );
      case 'INSECURE_CONNECTION':
        return pick(
          'ارتباط ناامن با سرور پذیرفته نیست.',
          'Insecure server connections are not allowed.',
        );
      case 'PANEL_NOT_FOUND':
        return pick('پنل یا اشتراک پیدا نشد.', 'Panel or subscription not found.');
      case 'APP_NOT_AUTHORIZED':
        return pick(
          'لایسنس اپ فعال نیست یا اطلاعات حساب معتبر نیست.',
          'App access is unavailable or account details are invalid.',
        );
      case 'SERVER_ERROR':
        return pick('درخواست به سرور ناموفق بود.', 'The server request failed.');
      case 'RESPONSE_TOO_LARGE':
        return pick('پاسخ سرور بیش از حد بزرگ است.', 'Server response is too large.');
      case 'INVALID_SERVER_RESPONSE':
        return pick('پاسخ سرویس معتبر نیست.', 'The server returned invalid data.');
      case 'NETWORK_UNAVAILABLE':
        return pick('اتصال به سرور برقرار نشد.', 'Unable to connect to the server.');
      case 'INVALID_TLS':
        return pick(
          'گواهی امنیتی HTTPS معتبر نیست.',
          'The HTTPS certificate could not be verified.',
        );
      default:
        return genericError;
    }
  }
}
