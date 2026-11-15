import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/brand_theme.dart';

void main() {
  test('light palette does not reuse a dark panel surface or background', () {
    final lightBackground = BrandTheme.backgroundColor(null, Brightness.light);
    final lightCard = BrandTheme.surface(null, Brightness.light);
    final darkBackground = BrandTheme.backgroundColor(null, Brightness.dark);
    final darkCard = BrandTheme.surface(null, Brightness.dark);
    expect(lightBackground.computeLuminance(), greaterThan(0.80));
    expect(lightCard.computeLuminance(), greaterThan(0.75));
    expect(darkBackground.computeLuminance(), lessThan(0.08));
    expect(darkCard.computeLuminance(), lessThan(0.08));
    expect(BrandTheme.make(null, Brightness.light).brightness,
        Brightness.light);
  });

  test('sidebar reads the authenticated tenant links, not vendor hardcodes', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains('widget.brand.telegramUrl'));
    expect(dashboard, contains('widget.brand.renewalUrl'));
    expect(dashboard, contains('widget.brand.websiteUrl'));
    expect(dashboard, contains('LaunchMode.externalApplication'));
    expect(dashboard, contains("url.scheme == 'https'"));
    expect(dashboard, contains("tenantLink_"));
  });
}
