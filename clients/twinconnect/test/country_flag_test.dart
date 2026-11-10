import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/country_flag.dart';

void main() {
  testWidgets('country flags render as graphics without emoji font support',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: Row(children: [
        CountryFlag('DE'), CountryFlag('NL'), CountryFlag('GB'),
        CountryFlag('US'), CountryFlag('SG'),
        CountryFlag('TR'), CountryFlag('IR'), CountryFlag('FI'),
      ])),
    ));
    for (final code in ['DE', 'NL', 'GB', 'US', 'SG', 'TR', 'IR', 'FI']) {
      expect(find.byKey(Key('countryFlag_$code')), findsOneWidget);
    }
    expect(find.byType(CustomPaint), findsWidgets);
  });

  testWidgets('unknown ISO codes use graphical fallback, not missing emoji',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: CountryFlag('ZZ')),
    ));
    expect(find.byKey(const Key('countryFlag_ZZ')), findsOneWidget);
  });
}
