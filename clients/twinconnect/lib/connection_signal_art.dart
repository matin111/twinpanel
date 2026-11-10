import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Decorative offline signal sculpture, never an indication of a live tunnel.
/// Finite entrance animation means widget tests settle and the desktop app
/// does not consume continuous animation frames while idle.
class ConnectionSignalArt extends StatefulWidget {
  const ConnectionSignalArt({required this.dark, super.key});
  final bool dark;

  @override
  State<ConnectionSignalArt> createState() => _ConnectionSignalArtState();
}

class _ConnectionSignalArtState extends State<ConnectionSignalArt>
    with SingleTickerProviderStateMixin {
  late final AnimationController _intro = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1500),
  )..forward();
  bool _hovered = false;

  @override
  void dispose() {
    _intro.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: AnimatedContainer(
        key: const Key('devSignalAnimation'),
        height: 48,
        width: 238,
        duration: const Duration(milliseconds: 260),
        curve: Curves.easeOutCubic,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(17),
          gradient: LinearGradient(
            colors: [
              const Color(0xFFA46AFF).withValues(alpha: _hovered ? .21 : .12),
              const Color(0xFF34C5CB).withValues(alpha: _hovered ? .14 : .06),
              const Color(0xFFA46AFF).withValues(alpha: _hovered ? .21 : .12),
            ],
          ),
          border: Border.all(
            color: const Color(0xFFA46AFF)
                .withValues(alpha: _hovered ? .57 : .23),
          ),
        ),
        child: AnimatedBuilder(
          animation: _intro,
          builder: (context, _) => CustomPaint(
            key: const Key('devSignalWave'),
            painter: _SignalPainter(
              progress: Curves.easeOutCubic.transform(_intro.value),
              hovered: _hovered,
              dark: widget.dark,
            ),
          ),
        ),
      ),
    );
  }
}

class _SignalPainter extends CustomPainter {
  const _SignalPainter({
    required this.progress,
    required this.hovered,
    required this.dark,
  });

  final double progress;
  final bool hovered;
  final bool dark;

  @override
  void paint(Canvas canvas, Size size) {
    final centerX = size.width / 2;
    final centerY = size.height / 2;
    final power = Paint()
      ..color = const Color(0xFFC6A1FF).withValues(alpha: dark ? .88 : .93)
      ..strokeWidth = 2.6
      ..strokeCap = StrokeCap.round;
    final cyan = Paint()
      ..color = const Color(0xFF69DBDC).withValues(alpha: dark ? .84 : .93)
      ..strokeWidth = 2.2
      ..strokeCap = StrokeCap.round;

    // Concentric static paths evoke a signal without pretending to measure it.
    for (var j = 0; j < 3; j++) {
      final glow = Paint()
        ..color = const Color(0xFFA46AFF)
            .withValues(alpha: (hovered ? .16 : .085) * progress)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.0;
      canvas.drawArc(
        Rect.fromCircle(center: Offset(centerX, centerY),
            radius: 12 + j * 8 + progress * 2),
        -math.pi * .76, math.pi * .53, false, glow,
      );
      canvas.drawArc(
        Rect.fromCircle(center: Offset(centerX, centerY),
            radius: 12 + j * 8 + progress * 2),
        math.pi * .24, math.pi * .53, false, glow,
      );
    }

    for (var i = 0; i < 23; i++) {
      final distance = (i - 11).abs() / 11;
      final envelope = math.pow(1 - distance, 1.75).toDouble();
      final harmonic = math.sin(i * .73).abs() * .35;
      final height = (3.5 + (13 + harmonic * 9) * envelope) * progress;
      final x = centerX + (i - 11) * 8.7;
      final color = i < 11 ? power : cyan;
      color.strokeWidth = hovered ? 3 : 2.4;
      canvas.drawLine(Offset(x, centerY - height / 2),
          Offset(x, centerY + height / 2), color);
    }

    final center = Paint()
      ..color = const Color(0xFFF6E9FF).withValues(alpha: progress)
      ..style = PaintingStyle.fill;
    canvas.drawCircle(Offset(centerX, centerY), 3.3 * progress, center);
    canvas.drawCircle(Offset(centerX, centerY), 5.7 * progress,
      Paint()
        ..color = const Color(0xFFB584FF).withValues(alpha: .70 * progress)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2);
  }

  @override
  bool shouldRepaint(covariant _SignalPainter oldDelegate) =>
      oldDelegate.progress != progress ||
      oldDelegate.hovered != hovered ||
      oldDelegate.dark != dark;
}
