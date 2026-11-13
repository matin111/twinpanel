import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Live traffic-flow visualization for the connection hero.
/// The plotted curves are based ONLY on actual sampled RX/TX rates.
/// No traffic values are synthesized, and no lock/orb is rendered.
class TwinConnectWaveIndicator extends StatefulWidget {
  const TwinConnectWaveIndicator({
    super.key,
    required this.connected,
    required this.connecting,
    required this.dark,
    this.rxSamples = const <double>[],
    this.txSamples = const <double>[],
  });

  final bool connected;
  final bool connecting;
  final bool dark;
  final List<double> rxSamples;
  final List<double> txSamples;

  @override
  State<TwinConnectWaveIndicator> createState() =>
      _TwinConnectWaveIndicatorState();
}

class _TwinConnectWaveIndicatorState extends State<TwinConnectWaveIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _motion = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 3000),
  );

  bool get _active => widget.connected || widget.connecting;

  @override
  void initState() {
    super.initState();
    if (_active) _motion.repeat();
  }

  @override
  void didUpdateWidget(covariant TwinConnectWaveIndicator oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_active && !_motion.isAnimating) _motion.repeat();
    if (!_active && _motion.isAnimating) {
      _motion.stop();
      _motion.value = 0;
    }
  }

  @override
  void dispose() {
    _motion.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 282,
      height: 138,
      child: RepaintBoundary(
        child: AnimatedBuilder(
          animation: _motion,
          builder: (_, __) => CustomPaint(
            key: const Key('liveTrafficFlowPainter'),
            painter: _LiveTrafficFlowPainter(
              dark: widget.dark,
              connected: widget.connected,
              connecting: widget.connecting,
              phase: _motion.value,
              rx: widget.rxSamples,
              tx: widget.txSamples,
            ),
          ),
        ),
      ),
    );
  }
}

class _LiveTrafficFlowPainter extends CustomPainter {
  const _LiveTrafficFlowPainter({
    required this.dark,
    required this.connected,
    required this.connecting,
    required this.phase,
    required this.rx,
    required this.tx,
  });

  final bool dark;
  final bool connected;
  final bool connecting;
  final double phase;
  final List<double> rx;
  final List<double> tx;

  @override
  void paint(Canvas canvas, Size size) {
    final bounds = Offset.zero & size;
    final background = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: dark
            ? [const Color(0xFF152F3B).withValues(alpha: .60),
               const Color(0xFF183D42).withValues(alpha: .22)]
            : [const Color(0xFFE5F3F4).withValues(alpha: .90),
               const Color(0xFFEDF6F7).withValues(alpha: .74)],
      ).createShader(bounds);
    final rounded = RRect.fromRectAndRadius(bounds.deflate(2),
        const Radius.circular(23));
    canvas.drawRRect(rounded, background);
    canvas.drawRRect(rounded,
        Paint()
          ..color = (dark ? const Color(0xFF729EAA) : const Color(0xFF8BBBC4))
              .withValues(alpha: .25)
          ..strokeWidth = 1
          ..style = PaintingStyle.stroke);

    canvas.save();
    canvas.clipRRect(rounded);

    // Technical mesh is static so an idle connection is completely still.
    final grid = Paint()
      ..color = (dark ? const Color(0xFF82AEB7) : const Color(0xFF609AAA))
          .withValues(alpha: .105)
      ..strokeWidth = .8;
    for (var x = 22.0; x < size.width; x += 26) {
      canvas.drawLine(Offset(x, 8), Offset(x, size.height - 8), grid);
    }
    for (var y = 20.0; y < size.height; y += 24) {
      canvas.drawLine(Offset(8, y), Offset(size.width - 8, y), grid);
    }

    if (!connected && !connecting) {
      // No waves or fabricated visual activity when disconnected.
      canvas.restore();
      return;
    }

    final rxColor = connected
        ? const Color(0xFF55D6A5) : const Color(0xFF78B9CA);
    final txColor = connected
        ? const Color(0xFF79BEC7) : const Color(0xFF819EBC);

    void drawStream(List<double> samples, Color color,
        double baseline, double direction) {
      final safe = samples.map((v) => v.isFinite && v > 0 ? v : 0.0)
          .toList(growable: false);
      final maxRate = safe.fold<double>(0, (maximum, value) => math.max(maximum, value));
      final path = Path();
      const left = 14.0;
      final width = size.width - 28;
      final display = safe.length > 1 ? safe : const <double>[0, 0];
      for (var i = 0; i < display.length; i++) {
        final x = left + width * i / (display.length - 1);
        final norm = maxRate > 0 ? display[i] / maxRate : 0.0;
        final y = baseline - direction * norm * 29;
        if (i == 0) {
          path.moveTo(x, y);
        } else {
          path.lineTo(x, y);
        }
      }
      canvas.drawPath(path, Paint()
        ..color = color.withValues(alpha: .12)
        ..strokeWidth = 8
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round
        ..style = PaintingStyle.stroke
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 7));
      canvas.drawPath(path, Paint()
        ..color = color.withValues(alpha: maxRate == 0 ? .28 : .90)
        ..strokeWidth = 2
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round
        ..style = PaintingStyle.stroke);

      if (maxRate > 0 && display.length >= 2) {
        final travel = phase * (display.length - 1);
        final index = travel.floor().clamp(0, display.length - 2);
        final mix = travel - index;
        final val = display[index] +
            (display[index + 1] - display[index]) * mix;
        final x = left + width * phase;
        final y = baseline - direction * (val / maxRate) * 29;
        canvas.drawCircle(Offset(x, y), 4.0, Paint()
          ..color = color.withValues(alpha: .35));
        canvas.drawCircle(Offset(x, y), 2.1, Paint()..color = color);
      }
    }

    drawStream(rx, rxColor, size.height * .43, 1);
    drawStream(tx, txColor, size.height * .72, -1);
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _LiveTrafficFlowPainter old) =>
      old.dark != dark || old.connected != connected ||
      old.connecting != connecting || old.phase != phase ||
      old.rx != rx || old.tx != tx;
}
