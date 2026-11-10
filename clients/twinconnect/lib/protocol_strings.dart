import 'app_strings.dart';

extension ProtocolStrings on AppStrings {
  String get protocolListTitle =>
      pick('پروتکل‌های اشتراک', 'Subscription protocols');
  String get protocolListSubtitle => pick(
    'این فهرست از پنل همان اشتراک دریافت می‌شود. وجود کانفیگ به‌معنای اتصال موفق نیست.',
    'These protocols come from your subscription panel. A stored config does not mean a working connection.',
  );
  String get protocolNotSelected =>
      pick('در اشتراک انتخاب نشده', 'Not included in subscription');
  String get protocolNotConfigured =>
      pick('کانفیگ هنوز ثبت نشده', 'Configuration still pending');
  String get protocolEnginePending =>
      pick('در انتظار موتور اتصال دستگاه', 'Native connection engine pending');
  String get protocolEngineReady => pick(
    'موتور شناسایی شده؛ اتصال هنوز آزمایش نشده',
    'Engine detected; connection not yet tested',
  );
  String get protocolCatalogUnavailable => pick(
    'دریافت فهرست پروتکل‌ها ممکن نشد. جزئیات برند همچنان در دسترس است.',
    'The protocol list could not be loaded. Brand details are still available.',
  );
  String get protocolPrivacy => pick(
    'کانفیگ خصوصی فقط هنگام درخواست اتصال و پس از تأیید موتور بومی دریافت می‌شود.',
    'Private profiles are retrieved only when a native engine is verified and a connection is requested.',
  );
}
