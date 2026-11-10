import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/main.dart';
import 'package:twinconnect/tenant_models.dart';
import 'package:twinconnect/interactive_glass_card.dart';
import 'package:twinconnect/authenticated_dashboard.dart';
import 'package:twinconnect/tenant_api.dart';
import 'package:twinconnect/protocols.dart';
import 'package:twinconnect/server_inventory.dart';

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

  testWidgets('authenticated dashboard replaces sign-in with the approved four pages',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1150, 850));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final panel = PanelDirectoryEntry.fromJson({
      'namespace': 'TP0123456789ABCDEF',
      'api_origin': 'https://panel.example.com',
    });
    final brand = BrandPreview.fromJson({
      'namespace': 'TP0123456789ABCDEF',
      'brand_name': 'آریا VPN',
      'owner_type': 'reseller',
      'account_status': 'active',
      'app_username_prefix': 'TP0123456789ABCDEF_R2A_',
    });
    final inventory = AppServerInventory.fromJson({
      'schema': 1,
      'namespace': 'TP0123456789ABCDEF',
      'servers': [
        {
          'id': '17', 'name': 'Germany - Frankfurt',
          'country_code': 'DE', 'node_online': true, 'latency_ms': null,
        },
      ],
    });
    await tester.pumpWidget(MaterialApp(
      home: AuthenticatedDashboard(
        panel: panel,
        username: 'TP0123456789ABCDEF_R2A_APP0123',
        sessionToken: 'test-token-not-for-network',
        brand: brand, servers: inventory, catalog: null,
        nativeProtocols: const NativeProtocolReadiness(supportedCodes: {}),
        refreshingServers: false,
        protocolCatalogUnavailable: false,
        refreshServers: () {},
        onLogout: () {},
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('liveQuickConnectCard')), findsOneWidget);
    expect(find.byKey(const Key('liveNetworkCard')), findsOneWidget);
    expect(find.byKey(const Key('loginGlassCard')), findsNothing);
    expect(find.text('Sign in'), findsNothing);
    expect(find.textContaining('coming soon'), findsNothing);
    expect(find.byKey(const Key('liveServer_17')), findsOneWidget);
    await tester.tap(find.byKey(const Key('liveNav_locations')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('liveServerSearch')), findsOneWidget);
    await tester.tap(find.byKey(const Key('liveNav_account')));
    await tester.pumpAndSettle();
    expect(find.text('آریا VPN'), findsOneWidget);
    expect(find.byKey(const Key('loginGlassCard')), findsNothing);
  });
}
