import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/brand_theme.dart';
import 'package:twinconnect/tenant_models.dart';
import 'package:twinconnect/windows_preview_fixture.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({
      'twinconnect_ui_language_v1': 'en',
    });
  });

  test('brand appearance parses valid fields and rejects invalid theme values', () {
    final branded = BrandPreview.fromJson({
      'namespace': 'TP0123456789ABCDEF',
      'brand_name': 'Reseller A',
      'owner_type': 'reseller',
      'account_status': 'active',
      'app_username_prefix': 'TP0123456789ABCDEF_R1_',
      'primary_color': '#009977',
      'secondary_color': '#2563EB',
      'button_color': '#F97316',
      'background_color': '#090B14',
      'surface_color': '#162434',
      'background_style': 'gradient',
      'theme_mode': 'light',
    });
    expect(branded.buttonColor, '#F97316');
    expect(branded.backgroundColor, '#090B14');
    expect(branded.surfaceColor, '#162434');
    expect(BrandTheme.mode(branded), ThemeMode.light);
    // Light mode keeps the tenant hue but darkens bright accents for legible
    // controls on frosted white cards; dark mode retains the configured color.
    expect(BrandTheme.make(branded, Brightness.light).colorScheme.primary,
        BrandTheme.accent(branded, Brightness.light));
    expect(BrandTheme.make(branded, Brightness.light).colorScheme.primary,
        isNot(const Color(0xFF009977)));
    expect(BrandTheme.make(branded, Brightness.dark).colorScheme.primary,
        const Color(0xFF009977));
    expect(BrandTheme.make(branded, Brightness.dark).cardTheme.color,
        const Color(0xFF162434));
    expect(BrandTheme.background(branded).gradient, isNotNull);

    final invalid = BrandPreview.fromJson({
      'namespace': 'TP0123456789ABCDEF',
      'brand_name': 'Reseller B',
      'owner_type': 'reseller',
      'account_status': 'active',
      'app_username_prefix': 'TP0123456789ABCDEF_R2_',
      'primary_color': 'javascript:alert(1)',
      'button_color': 'red',
      'background_style': 'invalid',
      'theme_mode': 'purple',
      'background_image_url': 'file:///etc/secrets',
    });
    expect(invalid.primaryColor, '#7C3AED');
    expect(invalid.buttonColor, '#7C3AED');
    expect(invalid.backgroundStyle, 'gradient');
    expect(invalid.backgroundImageUrl, isNull);
    expect(BrandTheme.mode(invalid), ThemeMode.dark);
  });

  test('two resellers can supply different appearances on one app binary', () {
    BrandPreview getBrand(String primary, String background) =>
        BrandPreview.fromJson({
          'namespace': 'TP0123456789ABCDEF',
          'brand_name': 'Brand',
          'owner_type': 'reseller',
          'account_status': 'active',
          'app_username_prefix': 'TP0123456789ABCDEF_R1_',
          'primary_color': primary,
          'background_color': background,
        });
    final a = getBrand('#D946EF', '#101018');
    final b = getBrand('#0F9B6A', '#FFFFFF');
    expect(BrandTheme.make(a, Brightness.dark).colorScheme.primary,
        isNot(BrandTheme.make(b, Brightness.dark).colorScheme.primary));
    expect(BrandTheme.background(a).gradient, isNotNull);
  });

  testWidgets('brand theme renderer uses the same palette on every platform',
      (tester) async {
    final brand = WindowsPreviewFixture.brand();
    await tester.pumpWidget(MaterialApp(
      theme: BrandTheme.make(brand, Brightness.dark),
      home: Scaffold(
        body: BrandBackground(
          brand: brand,
          child: const Text('Shared brand'),
        ),
      ),
    ));
    final theme = Theme.of(tester.element(find.text('Shared brand')));
    expect(theme.colorScheme.primary,
        BrandTheme.accent(brand, Brightness.dark));
    expect(theme.scaffoldBackgroundColor,
        BrandTheme.backgroundColor(brand, Brightness.dark));
  });
}
