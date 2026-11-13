import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/twin_language_picker.dart';

void main() {
  Future<void> openPicker(WidgetTester tester, {
    required bool dark,
    required bool rtl,
    required String selected,
    required ValueChanged<String?> onSelect,
  }) async {
    await tester.pumpWidget(MaterialApp(
      theme: ThemeData(brightness: dark ? Brightness.dark : Brightness.light),
      home: Scaffold(
        body: Builder(builder: (context) => ElevatedButton(
          onPressed: () async {
            final language = await showTwinLanguagePicker(
              context: context,
              selectedCode: selected,
              dark: dark,
              rtl: rtl,
              primary: const Color(0xFF6FA7B8),
              accent: const Color(0xFF62C1B4),
              title: 'Choose language',
              subtitle: 'Select your display language',
              note: 'Your choice is saved',
            );
            onSelect(language);
          },
          child: const Text('Open picker'),
        )),
      ),
    ));
    await tester.tap(find.text('Open picker'));
    await tester.pumpAndSettle();
  }

  testWidgets('dark dialog has six options and selects Arabic', (tester) async {
    String? result;
    await openPicker(tester,
      dark: true, rtl: false, selected: 'en',
      onSelect: (value) => result = value);
    expect(find.byKey(const Key('devLanguageDialog')), findsOneWidget);
    for (final language in ['fa', 'en', 'tr', 'ar', 'de', 'fr']) {
      expect(find.byKey(Key('languageChoice_' + language)), findsOneWidget);
    }
    expect(find.byIcon(Icons.check_circle_rounded), findsOneWidget);
    await tester.tap(find.byKey(const Key('languageChoice_ar')));
    await tester.pumpAndSettle();
    expect(result, 'ar');
  });

  testWidgets('light RTL dialog selects German without clipping', (tester) async {
    String? result;
    await openPicker(tester,
      dark: false, rtl: true, selected: 'fa',
      onSelect: (value) => result = value);
    final direction = tester.widget<Directionality>(
      find.ancestor(
        of: find.byKey(const Key('devLanguageDialog')),
        matching: find.byType(Directionality)).first,
    );
    expect(direction.textDirection, TextDirection.rtl);
    await tester.tap(find.byKey(const Key('languageChoice_de')));
    await tester.pumpAndSettle();
    expect(result, 'de');
    expect(tester.takeException(), isNull);
  });
}
