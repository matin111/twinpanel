import 'dart:math' as math;

import 'package:flutter/material.dart';

/// An aurora-style, live network fabric driven by observed RX and TX samples.
/// No synthetic transfer rates: ambient motion only runs for a verified tunnel
/// with measured traffic, and the disconnected appearance remains completely still.
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
    duration: const Duration(milliseconds: 3600),
  );
  bool get _trafficPresent =>
      widget.rxSamples.any((v) => v.isFinite && v > 0) ||
      widget.txSamples.any((v) => v.isFinite && v > 0);
  bool get _animate => widget.connected && _trafficPresent;

  @override
  void initState() {
    super.initState();
    if (_animate) _motion.repeat();
  }

  @override
  void didUpdateWidget(covariant TwinConnectWaveIndicator oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_animate && !_motion.isAnimating) _motion.repeat();
    if (!_animate && _motion.isAnimating) {
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
  Widget build(BuildContext context) => SizedBox(
        width: 342,
        height: 178,
        child: RepaintBoundary(
          child: AnimatedBuilder(
            animation: _motion,
            builder: (_, __) => CustomPaint(
              key: const Key('liveTrafficFlowPainter'),
              painter: _NetworkFabricPainter(
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

class _NetworkFabricPainter extends CustomPainter {
  const _NetworkFabricPainter({
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

  static const _mint = Color(0xFF61D9B5);
  static const _ice = Color(0xFF86C8EA);

  double _sample(List<double> history, double t) {
    if (history.isEmpty) return 0;
    final position = t.clamp(0.0, 1.0).toDouble() * (history.length - 1);
    final i = position.floor().clamp(0, history.length - 1);
    final next = math.min(i + 1, history.length - 1);
    final fraction = position - i;
    final a = history[i];
    final b = history[next];
    return math.max(0.0, (a.isFinite ? a : 0.0) * (1 - fraction) +
        (b.isFinite ? b : 0.0) * fraction);
  }

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final clip = RRect.fromRectAndRadius(
        rect.deflate(1.5), const Radius.circular(25));
    canvas.drawRRect(
      clip,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: dark
              ? const [Color(0xFF101E2A), Color(0xFF173543),
                  Color(0xFF112632)]
              : const [Color(0xFFF6FCFD), Color(0xFFEAF5F8),
                  Color(0xFFE5F4F2)],
        ).createShader(rect),
    );
    canvas.drawRRect(
      clip,
      Paint()
        ..color = (dark ? const Color(0xFF8BD2D5)
                : const Color(0xFF5C93A3))
            .withValues(alpha: dark ? .28 : .38)
        ..strokeWidth = 1
        ..style = PaintingStyle.stroke,
    );
    canvas.save();
    canvas.clipRRect(clip);

    // A soft, layered atmospheric light, not a rectangular chart grid.
    canvas.drawCircle(
      Offset(size.width * .50, size.height * .56),
      size.width * .42,
      Paint()
        ..shader = RadialGradient(colors: [
          _mint.withValues(alpha: dark ? .14 : .12),
          _ice.withValues(alpha: dark ? .055 : .04),
          _mint.withValues(alpha: 0),
        ]).createShader(rect),
    );

    final left = size.width * .065;
    final width = size.width * .87;
    final centerY = size.height * .52;
    final count = 45;
    final maxRx = rx.fold<double>(0, (m, v) => math.max(m, v.isFinite ? v : 0.0));
    final maxTx = tx.fold<double>(0, (m, v) => math.max(m, v.isFinite ? v : 0.0));
    final realActivity = maxRx > 0 || maxTx > 0;
    final active = connected && realActivity;
    final transitioning = connecting && !connected;

    // Fiber-optic network field: the arcs and halo signify connection state,
    // not measured byte counts. Rate numbers elsewhere remain real telemetry.
    final center = Offset(size.width * .50, size.height * .53);
    final left = size.width * .065;
    final right = size.width * .935;
    final reach = right - left;
    final maxRx = rx.fold<double>(0, (m, v) =>
        math.max(m, v.isFinite && v > 0 ? v : 0));
    final maxTx = tx.fold<double>(0, (m, v) =>
        math.max(m, v.isFinite && v > 0 ? v : 0));
    final realActivity = maxRx > 0 || maxTx > 0;
    final active = connected && realActivity;
    final luminous = connected || connecting;
    if (luminous) {
      canvas.drawCircle(center, size.height * .54,
        Paint()..shader = RadialGradient(colors: [
          _mint.withValues(alpha: connected ? .19 : .10),
          _ice.withValues(alpha: .05),
          _mint.withValues(alpha: 0),
        ]).createShader(Rect.fromCircle(
          center: center, radius: size.height * .54)));
      for (var ring = 0; ring < 3; ring++) {
        canvas.drawCircle(center, 30.0 + 17 * ring,
          Paint()
            ..color = (ring.isEven ? _mint : _ice)
                .withValues(alpha: .13 - ring * .028)
            ..strokeWidth = .9
            ..style = PaintingStyle.stroke);
      }
      // Each strand converges at the optical nexus, with two gently
      // separated banks. Unlike a chart, this looks full even at zero RX/TX.
      for (var strand = 0; strand < 19; strand++) {
        final offset = (strand - 9) / 9.0;
        final spread = offset * size.height * .31;
        final glow = strand % 4 == 0;
        final color = strand.isEven ? _mint : _ice;
        final path = Path()
          ..moveTo(left, center.dy + spread)
          ..cubicTo(
              left + reach * .24, center.dy + spread * .84,
              center.dx - reach * .18, center.dy + offset * 9,
              center.dx, center.dy + offset * 4)
          ..cubicTo(
              center.dx + reach * .18, center.dy - offset * 9,
              right - reach * .24, center.dy - spread * .78,
              right, center.dy - spread);
        if (glow) {
          canvas.drawPath(path, Paint()
            ..color = color.withValues(alpha: connected ? .22 : .10)
            ..strokeWidth = 7
            ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6)
            ..style = PaintingStyle.stroke);
        }
        canvas.drawPath(path, Paint()
          ..color = color.withValues(alpha:
              connected ? (.31 + (1-offset.abs())*.49) :
              (.10 + (1-offset.abs())*.22))
          ..strokeWidth = strand == 9 ? 2.2 : .9
          ..style = PaintingStyle.stroke);
        if (active && strand % 3 == 0) {
          // Optical highlights move over decoration only when traffic
          // is observed; the speed shown in cards is never fabricated.
          final t = (phase + strand / 19.0) % 1;
          final tangent = path.computeMetrics().first
              .getTangentForOffset(path.computeMetrics().first.length * t);
          if (tangent != null) {
            canvas.drawCircle(tangent.position, 2.9, Paint()
              ..color = color.withValues(alpha: .95));
            canvas.drawCircle(tangent.position, 8, Paint()
              ..color = color.withValues(alpha: .21)
              ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 5));
          }
        }
      }
      // Nexus is a slender data aperture, never a padlock or power orb.
      final aperture = RRect.fromRectAndRadius(
        Rect.fromCenter(center: center, width: 42, height: 62),
        const Radius.circular(19));
      canvas.drawRRect(aperture, Paint()
        ..color = (dark ? const Color(0xFF102D33)
          : const Color(0xFF163946)).withValues(alpha: .92));
      canvas.drawRRect(aperture, Paint()
        ..color = _mint.withValues(alpha: connected ? .72 : .30)
        ..strokeWidth = 1.2
        ..style = PaintingStyle.stroke);
      for (var i = 0; i < 4; i++) {
        canvas.drawLine(
          Offset(center.dx-10, center.dy-12 + i*8),
          Offset(center.dx+10, center.dy-12 + i*8),
          Paint()
            ..color = (i.isEven ? _mint : _ice)
                .withValues(alpha: connected ? .70 : .25)
            ..strokeWidth = 1.5
            ..strokeCap = StrokeCap.round);
      }
      // Real samples subtly modulate outer emitters, never the decorative
      // strand curvature or any displayed download/upload number.
      final signal = (maxRx + maxTx) > 0
          ? math.min(1.0, math.log(1 + maxRx + maxTx) / 18)
          : 0.0;
      for (final x in [left, right]) {
        canvas.drawCircle(Offset(x, center.dy), 4 + signal * 2.2,
            Paint()..color = _mint.withValues(alpha: .85));
        canvas.drawCircle(Offset(x, center.dy), 10 + signal * 2,
          Paint()..color = _mint.withValues(alpha: .24)
            ..style = PaintingStyle.stroke);
      }
    } else {
      // Disconnected: no optical traffic waves or moving indicators.
      canvas.drawLine(Offset(left, center.dy), Offset(right, center.dy),
        Paint()..color = _ice.withValues(alpha: .13)..strokeWidth = 1);
    }

    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _NetworkFabricPainter old) =>
      old.dark != dark || old.connected != connected ||
      old.connecting != connecting || old.phase != phase ||
      old.rx != rx || old.tx != tx;
}
