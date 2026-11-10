import 'dart:math' as math;
import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

/// Lightweight, finite ambient entrance animation for the Windows dashboard.
/// No looping ticker: widget tests settle, minimized windows consume no
/// animation frames, and nothing is painted on top of interactive controls.
class TwinConnectAmbientBackground extends StatefulWidget {
  const TwinConnectAmbientBackground({
    required this.dark,
    required this.child,
    super.key,
  });

  final bool dark;
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
    if (oldWidget.dark != widget.dark) {
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
    return AnimatedContainer(
      key: const Key('devAnimatedBackground'),
      duration: const Duration(milliseconds: 550),
      curve: Curves.easeInOutCubic,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          stops: const [0, .48, 1],
          colors: dark
              ? const [
                  Color(0xFF0A1024),
                  Color(0xFF181432),
                  Color(0xFF0C1A2B),
                ]
              : const [
                  Color(0xFFF6F1FF),
                  Color(0xFFEFF2FF),
                  Color(0xFFFBFAFF),
                ],
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
                        painter: _AmbientLines(dark: dark),
                      ),
                    ),
                    Positioned(
                      top: -195 + t * 88,
                      right: -160 + t * 44,
                      child: _glow(
                        diameter: 515,
                        color: const Color(0xFF8851FB),
                        strength: dark ? .28 : .19,
                      ),
                    ),
                    Positioned(
                      bottom: -205 + t * 85,
                      left: -180 + t * 72,
                      child: _glow(
                        diameter: 485,
                        color: const Color(0xFF26C8D5),
                        strength: dark ? .17 : .13,
                      ),
                    ),
                    Positioned(
                      top: 155 - t * 42,
                      left: 135 + t * 55,
                      child: _glow(
                        diameter: 320,
                        color: const Color(0xFFC268FF),
                        strength: dark ? .10 : .09,
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
  const _AmbientLines({required this.dark});
  final bool dark;

  @override
  void paint(Canvas canvas, Size size) {
    final color = (dark ? const Color(0xFFAAA2FF) : const Color(0xFF7463C6))
        .withValues(alpha: dark ? .065 : .068);
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
      dark != oldDelegate.dark;
}
