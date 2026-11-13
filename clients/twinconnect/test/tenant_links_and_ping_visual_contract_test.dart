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

  test('network ping uses latency-colored neon lightning, not gauge', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("Key('livePingLightningIcon')"));
    expect(dashboard, contains('Icons.bolt_rounded'));
    expect(dashboard, contains('ServerLatency.color(_connectedServerRtt)'));
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
