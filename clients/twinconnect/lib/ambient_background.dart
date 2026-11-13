import 'package:flutter/material.dart';

/// Lightweight, finite ambient entrance animation for the Windows dashboard.
/// No looping ticker: widget tests settle, minimized windows consume no
/// animation frames, and nothing is painted on top of interactive controls.
class TwinConnectAmbientBackground extends StatefulWidget {
  const TwinConnectAmbientBackground({
    required this.dark,
    this.backgroundColor,
    this.primaryColor = const Color(0xFF548BA4),
    this.secondaryColor = const Color(0xFF65B7B2),
    required this.child,
    super.key,
  });

  final bool dark;
  final Color? backgroundColor;
  final Color primaryColor;
  final Color secondaryColor;
  final Widget child;

  @override
  State<TwinConnectAmbientBackground> createState() =>
      _TwinConnectAmbientBackgroundState();
}

class _TwinConnectAmbientBackgroundState
    extends State<TwinConnectAmbientBackground>
    with SingleTickerProviderStateMixin {
  late final AnimationController _intro = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1250),
  )..forward();
  late final Animation<double> _progress = CurvedAnimation(
    parent: _intro,
    curve: Curves.easeOutCubic,
  );

  @override
  void didUpdateWidget(covariant TwinConnectAmbientBackground oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.dark != widget.dark || oldWidget.backgroundColor != widget.backgroundColor ||
        oldWidget.primaryColor != widget.primaryColor ||
        oldWidget.secondaryColor != widget.secondaryColor) {
      _intro.forward(from: 0.0);
    }
  }

  @override
  void dispose() {
    _intro.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final dark = widget.dark;
    final brandBackground = widget.backgroundColor;
    final gradientColors = brandBackground == null
        ? (dark
            ? const [Color(0xFF0F1720), Color(0xFF132532), Color(0xFF17323B)]
            : const [Color(0xFFF3F7F8), Color(0xFFEAF1F3), Color(0xFFF5FAFA)])
        : [
            brandBackground,
            Color.lerp(brandBackground, widget.primaryColor, dark ? .29 : .22)!,
            Color.lerp(brandBackground, widget.secondaryColor,
                dark ? .23 : .17)!,
          ];
    return AnimatedContainer(
      key: const Key('devAnimatedBackground'),
      duration: const Duration(milliseconds: 550),
      curve: Curves.easeInOutCubic,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          stops: const [0, .48, 1],
          colors: gradientColors,
        ),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: [
          IgnorePointer(
            child: AnimatedBuilder(
              animation: _progress,
              builder: (context, _) {
                final t = _progress.value;
                return Stack(
                  fit: StackFit.expand,
                  children: [
                    RepaintBoundary(
                      child: CustomPaint(
                        key: const Key('devAmbientGrid'),
                        painter: _AmbientLines(
                          dark: dark,
                          primary: widget.primaryColor,
                          secondary: widget.secondaryColor),
                      ),
                    ),
                    Positioned(
                      top: -195 + t * 88,
                      right: -160 + t * 44,
                      child: _glow(
                        diameter: 515,
                        color: widget.primaryColor,
                        strength: dark ? .43 : .33,
                      ),
                    ),
                    Positioned(
                      bottom: -205 + t * 85,
                      left: -180 + t * 72,
                      child: _glow(
                        diameter: 485,
                        color: widget.secondaryColor,
                        strength: dark ? .34 : .28,
                      ),
                    ),
                    Positioned(
                      top: 155 - t * 42,
                      left: 135 + t * 55,
                      child: _glow(
                        diameter: 320,
                        color: Color.lerp(widget.primaryColor,
                            widget.secondaryColor, .25)!,
                        strength: dark ? .21 : .19,
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
          widget.child,
        ],
      ),
    );
  }

  Widget _glow({
    required double diameter,
    required Color color,
    required double strength,
  }) {
    return SizedBox.square(
      dimension: diameter,
      child: DecoratedBox(
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [
              color.withValues(alpha: strength),
              color.withValues(alpha: strength * .37),
              color.withValues(alpha: 0),
            ],
            stops: const [0, .36, 1],
          ),
        ),
      ),
    );
  }
}

class _AmbientLines extends CustomPainter {
  const _AmbientLines({required this.dark,
      required this.primary, required this.secondary});
  final bool dark;
  final Color primary;
  final Color secondary;

  @override
  void paint(Canvas canvas, Size size) {
    // Native vector wallpaper: fluid fiber-optic streams and low-saturation
    // soft lights. This replaces the former grid and concentric violet arcs.
    final bounds = Offset.zero & size;
    canvas.drawRect(bounds, Paint()
      ..shader = RadialGradient(
        center: const Alignment(.67, -.44),
        radius: 1.10,
        colors: [
          primary.withValues(alpha: dark ? .30 : .13),
          secondary.withValues(alpha: dark ? .10 : .06),
          primary.withValues(alpha: 0),
        ],
      ).createShader(bounds));

    canvas.drawRect(bounds, Paint()
      ..shader = RadialGradient(
        center: const Alignment(-.80, .92),
        radius: 1.15,
        colors: [
          secondary.withValues(alpha: dark ? .24 : .12),
          secondary.withValues(alpha: 0),
        ],
      ).createShader(bounds));

    // Curved data-stream ribbons, with differentiated depth and low contrast.
    for (var i = 0; i < 13; i++) {
      final band = i / 12.0;
      final curve = Path()
        ..moveTo(-size.width * .12, size.height * (.22 + band * .60))
        ..cubicTo(
          size.width * .18, size.height * (-.08 + band * .75),
          size.width * .48, size.height * (.83 + band * .16),
          size.width * 1.12, size.height * (.19 + band * .66),
        );
      final hue = Color.lerp(primary, secondary, band)!;
      canvas.drawPath(curve, Paint()
        ..color = hue.withValues(alpha: (dark ? .11 : .15) * (1 - band * .42))
        ..strokeWidth = i % 4 == 0 ? 1.7 : .8
        ..style = PaintingStyle.stroke);
    }

    // Distant particles reinforce the flow without endless animations.
    for (var i = 0; i < 39; i++) {
      final fx = ((i * 47 + 11) % 101) / 101.0;
      final fy = ((i * 29 + 17) % 97) / 97.0;
      final p = Offset(size.width * fx, size.height * fy);
      canvas.drawCircle(p, i % 6 == 0 ? 1.65 : .75, Paint()
        ..color = (i.isEven ? primary : secondary)
            .withValues(alpha: dark ? .24 : .32));
    }

    // Minimal understated diagonal light streaks.
    for (var i = 0; i < 4; i++) {
      final y = size.height * (.12 + i * .23);
      final path = Path()
        ..moveTo(size.width * .61, y - 80)
        ..quadraticBezierTo(size.width * .88, y + 20,
            size.width * 1.1, y - 30);
      canvas.drawPath(path, Paint()
        ..color = secondary.withValues(alpha: dark ? .14 : .11)
        ..strokeWidth = 1.3
        ..style = PaintingStyle.stroke);
    }
  }

  @override
  bool shouldRepaint(covariant _AmbientLines oldDelegate) =>
      dark != oldDelegate.dark ||
      primary != oldDelegate.primary || secondary != oldDelegate.secondary;
}
