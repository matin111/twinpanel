import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Lightweight, finite ambient entrance animation for the Windows dashboard.
/// No looping ticker: widget tests settle, minimized windows consume no
/// animation frames, and nothing is painted on top of interactive controls.
class TwinConnectAmbientBackground extends StatefulWidget {
  const TwinConnectAmbientBackground({
    required this.dark,
    this.backgroundColor,
    this.primaryColor = const Color(0xFF9652FF),
    this.secondaryColor = const Color(0xFF00DCEB),
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
            ? const [Color(0xFF0A1024), Color(0xFF181432), Color(0xFF0C1A2B)]
            : const [Color(0xFFF6F1FF), Color(0xFFEFF2FF), Color(0xFFFBFAFF)])
        : [
            brandBackground,
            Color.lerp(brandBackground, widget.primaryColor, dark ? .19 : .08)!,
            Color.lerp(brandBackground, widget.secondaryColor,
                dark ? .14 : .055)!,
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
                        strength: dark ? .37 : .21,
                      ),
                    ),
                    Positioned(
                      bottom: -205 + t * 85,
                      left: -180 + t * 72,
                      child: _glow(
                        diameter: 485,
                        color: widget.secondaryColor,
                        strength: dark ? .27 : .15,
                      ),
                    ),
                    Positioned(
                      top: 155 - t * 42,
                      left: 135 + t * 55,
                      child: _glow(
                        diameter: 320,
                        color: Color.lerp(widget.primaryColor,
                            widget.secondaryColor, .25)!,
                        strength: dark ? .17 : .10,
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
    final color = Color.lerp(primary, secondary, .38)!
        .withValues(alpha: dark ? .085 : .072);
    final paint = Paint()
      ..color = color
      ..strokeWidth = .7
      ..style = PaintingStyle.stroke;
    const gap = 58.0;

    for (double x = 0; x <= size.width; x += gap) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (double y = 0; y <= size.height; y += gap) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }

    final arc = Paint()
      ..color = color.withValues(alpha: dark ? .45 : .55)
      ..strokeWidth = 1
      ..style = PaintingStyle.stroke;
    for (var i = 0; i < 3; i++) {
      canvas.drawArc(
        Rect.fromCircle(
          center: Offset(size.width * .83, size.height * .14),
          radius: 180 + i * 70,
        ),
        math.pi * .08,
        math.pi * 1.35,
        false,
        arc,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _AmbientLines oldDelegate) =>
      dark != oldDelegate.dark ||
      primary != oldDelegate.primary || secondary != oldDelegate.secondary;
}
