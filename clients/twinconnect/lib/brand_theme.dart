import 'package:flutter/material.dart';

import 'tenant_models.dart';

/// One appearance renderer shared by Android, Windows, iOS and macOS.
/// Values come from the authenticated subscription owner's panel.
class BrandTheme {
  const BrandTheme._();

  static Color parse(String input, String fallback) {
    final value = RegExp(r'^#[0-9a-fA-F]{6}$').hasMatch(input)
        ? input : fallback;
    return Color(int.parse('FF${value.substring(1)}', radix: 16));
  }

  // Legacy default violet is not a customized reseller palette. Translate
  // that old default to the new low-saturation ocean/slate design. Explicit
  // tenant color choices other than these defaults remain unchanged.
  static bool legacyViolet(BrandPreview? brand) =>
      (brand?.primaryColor.toUpperCase() ?? '#7C3AED') == '#7C3AED' &&
      (brand?.secondaryColor.toUpperCase() ?? '#4F46E5') == '#4F46E5';

  static Color secondaryAccent(BrandPreview? brand) =>
      legacyViolet(brand)
          ? const Color(0xFF65B7B2)
          : parse(brand?.secondaryColor ?? '', '#65B7B2');

  static Color connectionButton(BrandPreview? brand) =>
      legacyViolet(brand)
          ? const Color(0xFF3F879B)
          : parse(brand?.buttonColor ?? '', '#3F879B');

  // The panel stores one tenant palette, generally authored for dark mode.
  // Derive *separate* readable light surfaces while keeping the owner hue.
  static Color surface(BrandPreview? brand, Brightness brightness) {
    final base = legacyViolet(brand) &&
            (brand?.surfaceColor.toUpperCase() ?? '#20202A') == '#20202A'
        ? const Color(0xFF203544)
        : parse(brand?.surfaceColor ?? '', '#203544');
    return brightness == Brightness.dark
        ? base
        : Color.lerp(base, Colors.white, 0.95)!;
  }

  static Color backgroundColor(BrandPreview? brand, Brightness brightness) {
    final base = legacyViolet(brand) &&
            (brand?.backgroundColor.toUpperCase() ?? '#101018') == '#101018'
        ? const Color(0xFF121F2B)
        : parse(brand?.backgroundColor ?? '', '#121F2B');
    return brightness == Brightness.dark
        ? base
        : // Avoid an almost pure-white field that washes away the light-mode art.
        Color.lerp(base, const Color(0xFFF9F6FF), 0.97)!;
  }

  static Color accent(BrandPreview? brand, Brightness brightness) {
    final base = legacyViolet(brand)
        ? const Color(0xFF548BA4)
        : parse(brand?.primaryColor ?? '', '#548BA4');
    return brightness == Brightness.dark || base.computeLuminance() < .18
        ? base
        : Color.lerp(base, const Color(0xFF23485A), .24)!;
  }

  static ThemeMode mode(BrandPreview? brand) => switch (brand?.themeMode) {
        'light' => ThemeMode.light,
        'system' => ThemeMode.system,
        _ => ThemeMode.dark,
      };

  static ThemeData make(BrandPreview? brand, Brightness brightness) {
    final primary = accent(brand, brightness);
    final secondary = secondaryAccent(brand);
    final button = connectionButton(brand);
    final bg = backgroundColor(brand, brightness);
    final surface = BrandTheme.surface(brand, brightness);
    final onSurface = ThemeData.estimateBrightnessForColor(surface) ==
            Brightness.dark ? Colors.white : const Color(0xFF101827);
    final buttonForeground = ThemeData.estimateBrightnessForColor(button) ==
            Brightness.dark ? Colors.white : const Color(0xFF101827);
    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: ColorScheme.fromSeed(
        seedColor: primary, brightness: brightness,
      ).copyWith(
        primary: primary,
        secondary: secondary,
        surface: surface,
        onSurface: onSurface,
      ),
      scaffoldBackgroundColor: bg,
      cardTheme: CardThemeData(
        color: surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
        ),
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: surface,
        foregroundColor: onSurface,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: ButtonStyle(
          backgroundColor: WidgetStatePropertyAll(button),
          foregroundColor: WidgetStatePropertyAll(buttonForeground),
        ),
      ),
    );
  }

  static BoxDecoration background(BrandPreview? brand,
      {Brightness brightness = Brightness.dark}) {
    final base = backgroundColor(brand, brightness);
    final secondary = parse(brand?.secondaryColor ?? '', '#4F46E5');
    final style = brand?.backgroundStyle ?? 'gradient';
    if (style == 'image' && brand?.backgroundImageUrl != null) {
      return BoxDecoration(
        color: base,
        image: DecorationImage(
          image: NetworkImage(brand!.backgroundImageUrl!),
          fit: BoxFit.cover,
          colorFilter: const ColorFilter.mode(
            Color(0x55000000), BlendMode.darken,
          ),
        ),
      );
    }
    if (style == 'gradient') {
      return BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            base,
            Color.lerp(base, secondary, 0.24)!,
            base,
          ],
        ),
      );
    }
    return BoxDecoration(color: base);
  }
}

class BrandBackground extends StatelessWidget {
  const BrandBackground({
    required this.child,
    this.brand,
    super.key,
  });

  final Widget child;
  final BrandPreview? brand;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BrandTheme.background(brand,
          brightness: Theme.of(context).brightness),
      child: child,
    );
  }
}
