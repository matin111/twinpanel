import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/main.dart';
import 'package:twinconnect/tenant_models.dart';

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
    await tester.binding.setSurfaceSize(const Size(1536, 1024));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    SharedPreferences.setMockInitialValues({'twinconnect_ui_language_v1': 'en'});
    await tester.pumpWidget(const TwinConnectApp());
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('referenceDesktopShell')), findsOneWidget);
    await tester.tap(find.byKey(const Key('referenceNav3')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('referenceLoginAction')));
    await tester.pumpAndSettle();
    expect(find.text('TwinConnect'), findsOneWidget);
    expect(find.byKey(const Key('accountUsername')), findsOneWidget);
    expect(find.byKey(const Key('subscriptionLink')), findsOneWidget);
    expect(find.byKey(const Key('identifyButton')), findsOneWidget);
    expect(find.text('One app, many brands'), findsOneWidget);
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
