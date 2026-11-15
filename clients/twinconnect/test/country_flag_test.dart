import 'package:country_flags/country_flags.dart' as iso_flags;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/country_flag.dart' as twin;

void main() {
  testWidgets('bundled SVG flags render on Windows without Unicode emoji',
      (tester) async {
    const codes = [
      'DE', 'NL', 'GB', 'US', 'SG', 'TR', 'IR', 'FI',
      'HK', 'JP', 'AE', 'CA', 'SE', 'CH', 'ES',
    ];
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: Wrap(children: [
        for (final code in codes) twin.CountryFlag(code),
      ])),
    ));
    await tester.pump();
    for (final code in codes) {
      final parent = find.byKey(Key('countryFlag_$code'));
      expect(parent, findsOneWidget, reason: '$code should be present');
      expect(find.descendant(
        of: parent, matching: find.byType(iso_flags.CountryFlag),
      ), findsOneWidget, reason: '$code must use the packaged SVG flag');
    }
    expect(iso_flags.FlagCode.fromCountryCode('HK'), isNotNull);
  });

  testWidgets('legacy and lowercase country aliases use canonical flag',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: Row(children: [
        twin.CountryFlag('uk'),
        twin.CountryFlag('el'),
        twin.CountryFlag('hk'),
      ])),
    ));
    for (final raw in ['UK', 'EL', 'HK']) {
      expect(find.byKey(Key('countryFlag_$raw')), findsOneWidget);
    }
    expect(twin.CountryFlag.normalizedCode('uk'), 'GB');
    expect(twin.CountryFlag.normalizedCode('el'), 'GR');
    expect(twin.CountryFlag.normalizedCode('hk'), 'HK');
    expect(find.byType(iso_flags.CountryFlag), findsNWidgets(3));
  });

  testWidgets('invalid country codes retain neutral graphical fallback',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: twin.CountryFlag('ZZ')),
    ));
    final parent = find.byKey(const Key('countryFlag_ZZ'));
    expect(parent, findsOneWidget);
    expect(find.descendant(
      of: parent, matching: find.byType(iso_flags.CountryFlag),
    ), findsNothing);
    expect(find.descendant(
      of: parent, matching: find.byType(CustomPaint),
    ), findsOneWidget);
  });
}
