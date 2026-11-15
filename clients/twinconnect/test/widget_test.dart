import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/app_strings.dart';
import 'package:twinconnect/main.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('Persian and English strings including errors have distinct translations', () {
    const fa = AppStrings(Locale('fa'));
    const en = AppStrings(Locale('en'));

    expect(fa.identifyAccount, 'شناسایی حساب');
    expect(en.identifyAccount, 'Identify your account');
    expect(fa.statusExpired, 'اشتراک منقضی');
    expect(en.statusExpired, 'Expired subscription');
    expect(fa.error('TENANT_MISMATCH'), contains('شناسه'));
    expect(en.error('TENANT_MISMATCH'), contains('Panel code'));
    expect(fa.error('APP_NOT_AUTHORIZED'), isNot(en.error('APP_NOT_AUTHORIZED')));
  });

  testWidgets('restores Persian preference and switches to English with LTR',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(1536, 1024));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    SharedPreferences.setMockInitialValues({
      'twinconnect_ui_language_v1': 'fa',
    });

    await tester.pumpWidget(const TwinConnectApp());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('referenceNav3')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('referenceLoginAction')));
    await tester.pumpAndSettle();

    expect(find.text('شناسایی حساب'), findsOneWidget);
    expect(
      Directionality.of(tester.element(find.byKey(const Key('accountUsername')))),
      TextDirection.rtl,
    );

    await tester.tap(find.byKey(const Key('languagePicker')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('English').last);
    await tester.pumpAndSettle();

    expect(find.text('Identify your account'), findsOneWidget);
    expect(
      Directionality.of(tester.element(find.byKey(const Key('accountUsername')))),
      TextDirection.ltr,
    );

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('twinconnect_ui_language_v1'), 'en');

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpWidget(const TwinConnectApp());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('referenceNav3')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('referenceLoginAction')));
    await tester.pumpAndSettle();
    expect(find.text('Identify your account'), findsOneWidget);
  });

  testWidgets('Persian selection is saved from English UI', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1536, 1024));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    SharedPreferences.setMockInitialValues({
      'twinconnect_ui_language_v1': 'en',
    });
    await tester.pumpWidget(const TwinConnectApp());
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('referenceNav3')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('referenceLoginAction')));
    await tester.pumpAndSettle();
    expect(find.text('Identify your account'), findsOneWidget);

    await tester.tap(find.byKey(const Key('languagePicker')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('فارسی').last);
    await tester.pumpAndSettle();

    expect(find.text('شناسایی حساب'), findsOneWidget);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('twinconnect_ui_language_v1'), 'fa');
  });
}
