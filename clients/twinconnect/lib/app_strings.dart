import 'package:flutter/widgets.dart';

/// All static user-facing text is centralized so RTL/LTR UI stays consistent.
/// Names, contact details, and URLs from the reseller are not translated.
class AppStrings {
  const AppStrings(this.locale);

  final Locale locale;

  static AppStrings of(BuildContext context) =>
      AppStrings(Localizations.localeOf(context));

  bool get isFa => locale.languageCode.toLowerCase() == 'fa';

  static const Map<String, Map<String, String>> _translations = {
    "tr": <String, String>{
      "Sign in": "Giriş yap",
      "Username": "Kullanıcı adı",
      "Password": "Şifre",
      "Enter your app username and password.": "Uygulama kullanıcı adınızı ve şifrenizi girin.",
      "App language": "Uygulama dili",
      "Language": "Dil",
      "Quick connect": "Hızlı bağlantı",
      "Locations": "Konumlar",
      "Settings": "Ayarlar",
      "Account": "Hesap",
      "Support": "Destek",
      "Renew": "Yenile",
      "Website": "Web sitesi",
      "Network status": "Ağ durumu",
      "Server ping": "Sunucu gecikmesi",
      "Public IP": "Genel IP",
      "Download": "İndirme",
      "Upload": "Yükleme",
      "Connect now": "Bağlan",
      "Disconnect": "Bağlantıyı kes",
      "Connecting": "Bağlanıyor",
      "Connecting...": "Bağlanıyor...",
      "You are online": "Çevrimiçisiniz",
      "You are offline": "Çevrimdışısınız",
      "Connected for": "Bağlantı süresi",
      "Refresh connection status": "Bağlantı durumunu yenile",
      "Refresh": "Yenile",
      "Subscription details": "Abonelik bilgileri",
      "Data usage": "Veri kullanımı",
      "Expiry date": "Bitiş tarihi",
      "Time remaining": "Kalan süre",
      "Unlimited": "Sınırsız",
      "Disconnected": "Bağlantı yok",
      "Tunnel active": "Tünel etkin",
      "Handshake verified": "El sıkışma doğrulandı",
      "Interface active": "Arayüz etkin",
      "Ping all servers": "Tüm sunucuları test et",
      "Ping server": "Sunucu ping testi",
      "Ready to connect": "Bağlanmaya hazır",
      "Sign out": "Çıkış yap",
    },
    "ar": <String, String>{
      "Sign in": "تسجيل الدخول",
      "Username": "اسم المستخدم",
      "Password": "كلمة المرور",
      "Enter your app username and password.": "أدخل اسم المستخدم وكلمة المرور للتطبيق.",
      "App language": "لغة التطبيق",
      "Language": "اللغة",
      "Quick connect": "اتصال سريع",
      "Locations": "المواقع",
      "Settings": "الإعدادات",
      "Account": "الحساب",
      "Support": "الدعم",
      "Renew": "تجديد",
      "Website": "الموقع",
      "Network status": "حالة الشبكة",
      "Server ping": "زمن استجابة الخادم",
      "Public IP": "عنوان IP العام",
      "Download": "تنزيل",
      "Upload": "رفع",
      "Connect now": "اتصل الآن",
      "Disconnect": "قطع الاتصال",
      "Connecting": "جارٍ الاتصال",
      "Connecting...": "جارٍ الاتصال...",
      "You are online": "أنت متصل",
      "You are offline": "أنت غير متصل",
      "Connected for": "مدة الاتصال",
      "Refresh connection status": "تحديث حالة الاتصال",
      "Refresh": "تحديث",
      "Subscription details": "تفاصيل الاشتراك",
      "Data usage": "استهلاك البيانات",
      "Expiry date": "تاريخ الانتهاء",
      "Time remaining": "الوقت المتبقي",
      "Unlimited": "غير محدود",
      "Disconnected": "غير متصل",
      "Tunnel active": "النفق نشط",
      "Handshake verified": "تم التحقق من الاتصال",
      "Interface active": "الواجهة نشطة",
      "Ping all servers": "اختبار جميع الخوادم",
      "Ping server": "اختبار استجابة الخادم",
      "Ready to connect": "جاهز للاتصال",
      "Sign out": "تسجيل الخروج",
    },
    "de": <String, String>{
      "Sign in": "Anmelden",
      "Username": "Benutzername",
      "Password": "Passwort",
      "Enter your app username and password.": "Gib deinen App-Benutzernamen und dein Passwort ein.",
      "App language": "App-Sprache",
      "Language": "Sprache",
      "Quick connect": "Schnellverbindung",
      "Locations": "Standorte",
      "Settings": "Einstellungen",
      "Account": "Konto",
      "Support": "Support",
      "Renew": "Verlängern",
      "Website": "Website",
      "Network status": "Netzwerkstatus",
      "Server ping": "Server-Ping",
      "Public IP": "Öffentliche IP",
      "Download": "Download",
      "Upload": "Upload",
      "Connect now": "Jetzt verbinden",
      "Disconnect": "Trennen",
      "Connecting": "Verbindung wird hergestellt",
      "Connecting...": "Verbindung wird hergestellt...",
      "You are online": "Du bist online",
      "You are offline": "Du bist offline",
      "Connected for": "Verbunden seit",
      "Refresh connection status": "Verbindungsstatus aktualisieren",
      "Refresh": "Aktualisieren",
      "Subscription details": "Abonnementdetails",
      "Data usage": "Datenverbrauch",
      "Expiry date": "Ablaufdatum",
      "Time remaining": "Verbleibende Zeit",
      "Unlimited": "Unbegrenzt",
      "Disconnected": "Getrennt",
      "Tunnel active": "Tunnel aktiv",
      "Handshake verified": "Handshake bestätigt",
      "Interface active": "Schnittstelle aktiv",
      "Ping all servers": "Alle Server testen",
      "Ping server": "Server-Ping testen",
      "Ready to connect": "Bereit zum Verbinden",
      "Sign out": "Abmelden",
    },
    "fr": <String, String>{
      "Sign in": "Se connecter",
      "Username": "Nom d’utilisateur",
      "Password": "Mot de passe",
      "Enter your app username and password.": "Saisissez votre identifiant et votre mot de passe.",
      "App language": "Langue de l’application",
      "Language": "Langue",
      "Quick connect": "Connexion rapide",
      "Locations": "Emplacements",
      "Settings": "Paramètres",
      "Account": "Compte",
      "Support": "Assistance",
      "Renew": "Renouveler",
      "Website": "Site web",
      "Network status": "État du réseau",
      "Server ping": "Ping du serveur",
      "Public IP": "IP publique",
      "Download": "Téléchargement",
      "Upload": "Envoi",
      "Connect now": "Se connecter",
      "Disconnect": "Déconnecter",
      "Connecting": "Connexion en cours",
      "Connecting...": "Connexion en cours...",
      "You are online": "Vous êtes connecté",
      "You are offline": "Vous êtes hors ligne",
      "Connected for": "Durée de connexion",
      "Refresh connection status": "Actualiser la connexion",
      "Refresh": "Actualiser",
      "Subscription details": "Détails de l’abonnement",
      "Data usage": "Données utilisées",
      "Expiry date": "Date d’expiration",
      "Time remaining": "Temps restant",
      "Unlimited": "Illimité",
      "Disconnected": "Déconnecté",
      "Tunnel active": "Tunnel actif",
      "Handshake verified": "Négociation vérifiée",
      "Interface active": "Interface active",
      "Ping all servers": "Tester tous les serveurs",
      "Ping server": "Tester le ping",
      "Ready to connect": "Prêt à se connecter",
      "Sign out": "Se déconnecter",
    },
  };

  String pick(String fa, String en) {
    if (isFa) return fa;
    final lang = locale.languageCode.toLowerCase();
    return _translations[lang]?[en] ?? en;
  }

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
  String get appLoginTitle => pick('ورود به حساب', 'Sign in');
  String get appLoginGuide => pick(
    'نام کاربری و رمز مخصوص اپ را وارد کنید.',
    'Enter your app username and password.',
  );
  String get appUsername => pick('نام کاربری', 'Username');
  String get appPassword => pick('رمز عبور', 'Password');
  String get appLoginButton => pick('ورود', 'Sign in');
  String get appPasswordRequired => pick(
    'رمز عبور را وارد کنید.',
    'Enter your password.',
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
  String get previewButton => pick(
    'مشاهده نسخه آزمایشی ویندوز',
    'Explore Windows demo',
  );
  String get previewBanner => pick(
    'حالت نمایشی آفلاین — این اطلاعات واقعی نیستند و هیچ VPN متصل نشده است.',
    'OFFLINE DEMO — Sample data only. No VPN is connected.',
  );
  String get previewSubtitle => pick(
    'برای بررسی ظاهر، فارسی/انگلیسی، تنظیمات و فهرست ۱۶ پروتکل بدون ورود حساب.',
    'Preview layout, Persian/English, settings and all 16 protocols without an account.',
  );
  String get windowsEnginePending => pick(
    'موتور اتصال ویندوز و Cisco/OpenConnect هنوز آماده نیست. این خروجی فقط برای آزمایش رابط برنامه است.',
    'Windows VPN engines and Cisco/OpenConnect are not ready. This build is for interface testing only.',
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
      case 'APP_LOGIN_INVALID':
        return pick('نام کاربری یا رمز اپ اشتباه است.', 'Incorrect app username or password.');
      case 'APP_LOGIN_LOCKED':
        return pick('تلاش‌های ناموفق زیاد بوده؛ کمی بعد دوباره امتحان کنید.', 'Too many failed attempts. Try again later.');
      case 'APP_SESSION_REVOKED':
      case 'APP_SESSION_INVALID':
        return pick('نشست اپ پایان یافته؛ دوباره وارد شوید.', 'Session ended. Please sign in again.');
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
