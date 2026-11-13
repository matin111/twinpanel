import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Support, Renew and Website load from the active authenticated panel', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final api = File('lib/tenant_api.dart').readAsStringSync();
    final model = File('lib/tenant_models.dart').readAsStringSync();
    expect(api, contains("'/v1/central-app/session/brand'"));
    expect(model, contains("telegramUrl: optional('telegram_url')"));
    expect(model, contains("renewalUrl: optional('renewal_url')"));
    expect(model, contains("websiteUrl: optional('website_url')"));
    expect(dashboard, contains('loadSessionBrand('));
    expect(dashboard, contains('_tenantLinkFromBrand(brand, kind)'));
    expect(dashboard, contains("_openTenantLink('support'"));
    expect(dashboard, contains("_openTenantLink('renewal'"));
    expect(dashboard, contains("_openTenantLink('website'"));
    expect(dashboard, contains('item.id, tr(item.fa, item.en)'));
    expect(dashboard, contains('TENANT_BRAND_MISMATCH'));
    expect(dashboard, contains('LaunchMode.externalApplication'));
  });

  test('tenant links accept Telegram handles and show missing-link feedback', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("_safeTenantLink(String? raw, String kind)"));
    expect(dashboard, contains("candidate = 'https://t.me/"));
    expect(dashboard, contains('brand = fresh;'));
    expect(dashboard, contains("_tenantLinkFromBrand(brand, kind)"));
    expect(dashboard, contains('App Brand Studio'));
    expect(dashboard, contains('uri.scheme != \'https\''));
    expect(dashboard, contains('uri.userInfo.isNotEmpty'));
  });

  test('connecting screen keeps status, connection control and clock without redundant captions', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("Key('liveConnectionStatus')"));
    expect(dashboard, contains("Key('liveConnectionControlsButton')"));
    expect(dashboard, contains("Key('liveConnectionDuration')"));
    expect(dashboard, isNot(contains("tr('اتصال امن برقرار است', 'Secure connection active')")));
    expect(dashboard, isNot(contains("tr('دست‌دهی با سرور تأیید شد', 'Server handshake verified')")));
  });

  test('connection indicator waves only while connecting or verified', () {
    final wave = File('lib/twinconnect_wave_indicator.dart').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(wave, contains('if (_active)'));
    expect(wave, contains('if (!_active && _motion.isAnimating)'));
    expect(dashboard, contains('connected: _verifiedConnectionActive'));
    expect(dashboard, contains("Key('liveRefreshTunnelStatus')"));
  });

  test('Persian dashboard is RTL and English dashboard is LTR', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("textDirection: _rtl ? TextDirection.rtl : TextDirection.ltr"));
    expect(dashboard, contains("key: ValueKey<String>(_rtl ? 'dashboard-rtl' : 'dashboard-ltr')"));
    expect(dashboard.replaceAll('\r\n', '\n'),
        contains('child: Row(children: [\n          sideBar(),'));
    expect(dashboard, isNot(contains('textDirection: TextDirection.ltr,\n            child: Row(')));
    expect(dashboard, contains('textDirection: TextDirection.ltr,'));
  });

  test('six dashboard locales and Arabic right-to-left are supported', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final localizer = File('lib/app_strings.dart').readAsStringSync();
    for (final code in ['fa', 'en', 'tr', 'ar', 'de', 'fr']) {
      expect(dashboard, contains("'$code'"));
    }
    expect(dashboard, contains("_languageCode == 'ar'"));
    expect(localizer, contains('static const Map<String, Map<String, String>> _translations'));
  });

  test('network ping uses latency-colored neon lightning, not gauge', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("Key('livePingLightningIcon')"));
    expect(dashboard, contains('Icons.bolt_rounded'));
    expect(dashboard, contains('ServerLatency.color(_connectedServerRtt)'));
  });

  test('light mode has visible branded luminous geometry', () {
    final ambient = File('lib/ambient_background.dart').readAsStringSync();
    final theme = File('lib/brand_theme.dart').readAsStringSync();
    expect(ambient, contains('final bounds = Offset.zero & size;'));
    expect(ambient, contains('for (var i = 0; i < 39; i++)'));
    expect(ambient, contains('for (var i = 0; i < 13; i++)'));
    expect(ambient, contains('dark ? .10 : .075'));
    expect(theme, contains('Color(0xFFF3F7F8), 0.97'));
  });

  test('all server ping actions use lightning instead of the old network icon', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, isNot(contains('Icons.network_ping_rounded')));
    expect(dashboard, contains('Icons.bolt_rounded'));
    expect(dashboard, contains("tooltip: tr('تست پینگ', 'Ping server')"));
    expect(dashboard, contains("tr('تست پینگ همه سرورها', 'Ping all servers')"));
    expect(dashboard, contains("Key('livePingLightningIcon')"));
  });

  test('shared background takes real per-tenant primary and secondary colors', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final ambient = File('lib/ambient_background.dart').readAsStringSync();
    expect(dashboard, contains('primaryColor: purple'));
    expect(dashboard, contains('BrandTheme.secondaryAccent(widget.brand)'));
    expect(ambient, contains('final Color primaryColor'));
    expect(ambient, contains('final Color secondaryColor'));
    expect(ambient, contains('duration: const Duration(milliseconds: 1250)'));
  });
}
