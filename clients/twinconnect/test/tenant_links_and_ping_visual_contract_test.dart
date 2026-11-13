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

  test('network ping uses latency-colored neon lightning, not gauge', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("Key('livePingLightningIcon')"));
    expect(dashboard, contains('Icons.bolt_rounded'));
    expect(dashboard, contains('ServerLatency.color(_connectedServerRtt)'));
  });

  test('light mode has visible branded luminous geometry', () {
    final ambient = File('lib/ambient_background.dart').readAsStringSync();
    final theme = File('lib/brand_theme.dart').readAsStringSync();
    expect(ambient, contains('final streak = Paint()'));
    expect(ambient, contains('final sparks = Paint()'));
    expect(ambient, contains('final sweep = Paint()'));
    expect(ambient, contains('dark ? .12 : .16'));
    expect(theme, contains('Color(0xFFF4F0FF), 0.90'));
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
    expect(dashboard, contains("widget.brand.secondaryColor, '#00DCEB'"));
    expect(ambient, contains('final Color primaryColor'));
    expect(ambient, contains('final Color secondaryColor'));
    expect(ambient, contains('duration: const Duration(milliseconds: 1250)'));
  });
}
