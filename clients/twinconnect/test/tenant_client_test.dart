import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/main.dart';
import 'package:twinconnect/tenant_models.dart';
import 'package:twinconnect/tenant_api.dart';
import 'package:twinconnect/interactive_glass_card.dart';

void main() {
  group('tenant routing', () {
    test('reseller account extracts the vendor namespace', () {
      expect(
        TenantIdentity.namespaceFromUsername(
          'TP0123456789ABCDEF_R2A_ali123',
        ),
        'TP0123456789ABCDEF',
      );
      expect(
        TenantIdentity.parseNamespace(
          'TP0123456789ABCDEF_R2A_ali123',
          '',
        ),
        'TP0123456789ABCDEF',
      );
    });

    test('short reseller account routes by its unique short panel alias', () {
      expect(
        TenantIdentity.namespaceFromUsername('TPA1B2C3_R2A_APP0123456789ABCDEF'),
        'TPA1B2C3',
      );
      expect(
        TenantIdentity.namespaceFromUsername('TPA1B2C3D4E5F60718_R2A_APP0123456789ABCDEF'),
        'TPA1B2C3D4E5F60718',
      );
      expect(
        TenantIdentity.parseNamespace('TPA1B2C3_R1_APP0123456789ABCDEF', ''),
        'TPA1B2C3',
      );
      expect(
        () => TenantIdentity.parseNamespace(
          'TPA1B2C3_R1_APP0123456789ABCDEF', 'TPB2C3D4'),
        throwsFormatException,
      );
    });

    test('admin account can use a separate tenant code', () {
      expect(
        TenantIdentity.parseNamespace('ordinary_admin_user', 'TP0123456789ABCDEF'),
        'TP0123456789ABCDEF',
      );
      expect(
        () => TenantIdentity.parseNamespace('ordinary_admin_user', ''),
        throwsFormatException,
      );
    });

    test('a mismatched namespace is refused', () {
      expect(
        () => TenantIdentity.parseNamespace(
          'TP0123456789ABCDEF_R2A_ali',
          'TPAAAAAAAAAAAAAAAA',
        ),
        throwsFormatException,
      );
    });

    test('share URL and standalone short token are parsed safely', () {
      expect(
        SubscriptionInput.tokenFromInput(
          'https://sub.example.com/v1/connect/test-token-123?source=app',
        ),
        'test-token-123',
      );
      expect(
        SubscriptionInput.tokenFromInput('test-token-123'),
        'test-token-123',
      );
      expect(
        () => SubscriptionInput.tokenFromInput('http://localhost/v1/connect/secret'),
        throwsFormatException,
      );
      expect(
        () => SubscriptionInput.tokenFromInput('https://host.example/anything/secret'),
        throwsFormatException,
      );
    });

    test('directory refuses insecure and private origins', () {
      expect(
        () => parseDirectoryOrigin('http://panel.example.com'),
        throwsFormatException,
      );
      expect(
        () => parseDirectoryOrigin('https://localhost'),
        throwsFormatException,
      );
      expect(
        () => parseDirectoryOrigin('https://127.0.0.1'),
        throwsFormatException,
      );
      expect(
        () => parseDirectoryOrigin('https://panel.example.com/path'),
        throwsFormatException,
      );
      expect(
        parseDirectoryOrigin('https://panel.example.com').toString(),
        'https://panel.example.com',
      );
    });

    test('license center supports ordered independent origins without tenant pinning', () {
      final origins = TenantApi.parseVendorOrigins(
          'https://license-a.example.com, https://license-b.example.com, '
          'https://license-a.example.com');
      expect(origins.map((uri) => uri.host).toList(),
          ['license-a.example.com', 'license-b.example.com']);
      expect(() => TenantApi.parseVendorOrigins(''), throwsFormatException);
      expect(() => TenantApi.parseVendorOrigins(
          'https://license-a.example.com,http://unsafe.example.com'),
          throwsFormatException);
    });

    test('thousands of licensed installations use isolated namespace routing', () {
      // Each registration is resolved independently; there must never be
      // one shared customer-panel origin baked into a universal app.
      final resolved = <String, Uri>{};
      for (var index = 0; index < 2000; index++) {
        final namespace = 'TP${index.toRadixString(16).toUpperCase().padLeft(16, '0')}';
        final origin = 'https://panel-$index.example.com';
        final entry = PanelDirectoryEntry.fromJson({
          'namespace': namespace,
          'api_origin': origin,
        });
        expect(entry.namespace, namespace);
        resolved[entry.namespace] = entry.apiOrigin;
      }
      expect(resolved.length, 2000);
      expect(resolved.values.toSet().length, 2000);
      expect(resolved['TP0000000000000000']?.host, 'panel-0.example.com');
      expect(resolved['TP00000000000007CF']?.host, 'panel-1999.example.com');
    });

    test('license directory can rotate a tenant origin without a client update', () {
      const namespace = 'TP0123456789ABCDEF';
      final before = PanelDirectoryEntry.fromJson({
        'namespace': namespace,
        'api_origin': 'https://old-domain.example.com',
      });
      final after = PanelDirectoryEntry.fromJson({
        'namespace': namespace,
        'api_origin': 'https://new-domain.example.com',
      });
      expect(before.namespace, after.namespace);
      expect(before.apiOrigin, isNot(after.apiOrigin));
      expect(after.apiOrigin.host, 'new-domain.example.com');
    });

    test('Android build requires more than a single reachable directory', () {
      final workflow = File('../../.github/workflows/twinconnect-android-native.yml')
          .readAsStringSync();
      expect(workflow, contains('TWINCONNECT_DIRECTORY_URLS'));
      expect(workflow, contains('--dart-define=TWINCONNECT_DIRECTORY_URLS='));
      expect(workflow, contains('At least two unique license-directory mirrors'));
    });

    test('login differentiates license-directory and tenant-panel outages', () {
      final main = File('lib/main.dart').readAsStringSync();
      final strings = File('lib/app_strings.dart').readAsStringSync();
      expect(main, contains("DIRECTORY_NETWORK_UNAVAILABLE"));
      expect(main, contains("PANEL_NETWORK_UNAVAILABLE"));
      expect(main, contains("refreshed.apiOrigin == panel.apiOrigin"));
      expect(main, contains("panel = refreshed;"));
      expect(strings, contains("case 'DIRECTORY_NETWORK_UNAVAILABLE':"));
      expect(strings, contains("case 'PANEL_NETWORK_UNAVAILABLE':"));
    });

    test('missing optional brand links stay hidden', () {
      final info = BrandPreview.fromJson({
        'namespace': 'TP0123456789ABCDEF',
        'brand_name': 'برند آزمایشی',
        'owner_type': 'reseller',
        'account_status': 'active',
        'app_username_prefix': 'TP0123456789ABCDEF_R2A_',
        'primary_color': 'untrusted',
      });
      expect(info.telegramUrl, isNull);
      expect(info.renewalUrl, isNull);
      expect(info.primaryColor, '#7C3AED');
    });
  });

  testWidgets('screen explains that VPN engine is not yet connected', (tester) async {
    SharedPreferences.setMockInitialValues({'twinconnect_ui_language_v1': 'en'});
    await tester.pumpWidget(const TwinConnectApp());
    await tester.pumpAndSettle();
    // Login remains neutral until the account is authenticated.
    expect(find.text('TwinConnect'), findsNothing);
    expect(find.text('Matin Vpn'), findsNothing);
    expect(find.byKey(const Key('accountUsername')), findsOneWidget);
    expect(find.byKey(const Key('appPassword')), findsOneWidget);
    expect(find.byKey(const Key('identifyButton')), findsOneWidget);
    expect(find.byKey(const Key('loginGlassCard')), findsOneWidget);
    expect(find.byKey(const Key('loginEntranceAnimation')), findsOneWidget);
    expect(find.byKey(const Key('devAnimatedBackground')), findsOneWidget);
    expect(find.byType(TwinConnectGlassCard), findsOneWidget);
    expect(find.byType(BackdropFilter), findsWidgets);
    expect(find.text('Sign in'), findsWidgets);
    // The connection engine is deliberately not mounted to any action.
    expect(find.byKey(const Key('brandCard')), findsNothing);
  });

  testWidgets('brand preview contains only reseller contact, not configs', (tester) async {
    final brand = BrandPreview.fromJson({
      'namespace': 'TP0123456789ABCDEF',
      'brand_name': 'آریا VPN',
      'owner_type': 'reseller',
      'account_status': 'active',
      'app_username_prefix': 'TP0123456789ABCDEF_R2A_',
      'telegram_url': 'https://t.me/aria_support',
      'renewal_url': 'https://renew.example.com',
    });
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: BrandDetails(brand: brand),
        ),
      ),
    ));
    expect(find.text('آریا VPN'), findsOneWidget);
    expect(find.text('https://t.me/aria_support'), findsOneWidget);
    expect(find.text('https://renew.example.com'), findsOneWidget);
    final connect = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Connect VPN (coming soon)'),
    );
    expect(connect.onPressed, isNull);
  });
}
