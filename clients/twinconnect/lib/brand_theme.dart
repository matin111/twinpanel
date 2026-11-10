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

  static ThemeMode mode(BrandPreview? brand) => switch (brand?.themeMode) {
        'light' => ThemeMode.light,
        'system' => ThemeMode.system,
        _ => ThemeMode.dark,
      };

  static ThemeData make(BrandPreview? brand, Brightness brightness) {
    final primary = parse(brand?.primaryColor ?? '', '#7C3AED');
    final secondary = parse(brand?.secondaryColor ?? '', '#4F46E5');
    final button = parse(brand?.buttonColor ?? '', '#7C3AED');
    final bg = parse(brand?.backgroundColor ?? '', '#101018');
    final surface = parse(brand?.surfaceColor ?? '', '#20202A');
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

  static BoxDecoration background(BrandPreview? brand) {
    final base = parse(brand?.backgroundColor ?? '', '#101018');
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
      decoration: BrandTheme.background(brand),
      child: child,
    );
  }
}
