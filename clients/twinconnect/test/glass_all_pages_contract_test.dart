import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('shared glass surfaces retain translucent gradient and backdrop blur', () {
    final glass = File('lib/interactive_glass_card.dart').readAsStringSync();
    expect(glass, contains('BackdropFilter('));
    expect(glass, contains('ImageFilter.blur('));
    expect(glass, contains('surface.withValues(alpha:'));
    expect(glass, contains('surface.withValues(alpha: bright ? .67 : .93)'));
  });

  test('connection dashboard, locations, account and settings use glass', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains('Widget powerCard({required Widget subscriptionContent}) => ClipRRect('));
    expect(dashboard, contains('Widget connectionStats() => glassCard('));
    expect(dashboard, contains('Widget settings() => Column('));
    expect(dashboard, contains("key: const Key('settingsSecurityStatus')"));
    expect(dashboard, contains("key: const Key('accountIdentityCard')"));
    expect(dashboard, contains("key: const Key('devLocationListingCard')"));
    expect(dashboard, isNot(contains('decoration: tile(radius:')));
  });

  test('dedicated VPN preferences and sharing cards use same glass', () {
    final settings = File('lib/vpn_settings.dart').readAsStringSync();
    final sharing = File('lib/share_vpn_preview.dart').readAsStringSync();
    expect(settings, contains('class GlassVpnSwitch'));
    expect(settings, contains('TwinConnectGlassCard('));
    expect(sharing, contains('TwinConnectGlassCard('));
  });
}
