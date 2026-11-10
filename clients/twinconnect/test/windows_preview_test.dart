import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/main.dart';
import 'package:twinconnect/windows_preview_fixture.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({
        'twinconnect_ui_language_v1': 'en',
      }));

  test('development sample has 16 protocols and no active engine', () {
    final brand = WindowsPreviewFixture.brand();
    final catalog = WindowsPreviewFixture.protocolCatalog();
    expect(brand.brandName, 'TwinConnect Demo');
    expect(catalog.entries.length, 16);
    expect(catalog.entries.every((e) => !e.clientEngineReady), true);
  });

  testWidgets('production login has only username, password and sign-in',
      (tester) async {
    await tester.pumpWidget(const TwinConnectApp());
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('accountUsername')), findsOneWidget);
    expect(find.byKey(const Key('appPassword')), findsOneWidget);
    expect(find.byKey(const Key('identifyButton')), findsOneWidget);
    expect(find.text('Sign in'), findsWidgets);
    expect(find.byKey(const Key('subscriptionLink')), findsNothing);
    expect(find.byKey(const Key('tenantCode')), findsNothing);
    expect(find.byKey(const Key('windowsDemoButton')), findsNothing);
    expect(find.byKey(const Key('offlineDemoBanner')), findsNothing);
    expect(find.textContaining('One app, many brands'), findsNothing);
  });

  testWidgets('app password is masked', (tester) async {
    await tester.pumpWidget(const TwinConnectApp());
    await tester.pumpAndSettle();
    final input = tester.widget<TextFormField>(
      find.byKey(const Key('appPassword')),
    );
    expect(input.obscureText, true);
  });
}
