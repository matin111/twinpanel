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

    // Guide rails and short ticks evoke a network fabric without faking data.
    final track = Paint()
      ..color = (dark ? _ice : const Color(0xFF568A9C))
          .withValues(alpha: dark ? .16 : .20)
      ..strokeWidth = 1;
    for (var lane = -2; lane <= 2; lane++) {
      final y = centerY + lane * 23;
      canvas.drawLine(Offset(left, y), Offset(left + width, y), track);
    }
    for (var i = 0; i < 13; i++) {
      final x = left + i * width / 12;
      canvas.drawLine(Offset(x, centerY - 5),
          Offset(x, centerY + 5), track);
    }

    // A continuous ribbon silhouette is driven by interpolated REAL traffic.
    // When the tunnel is disconnected there is no flowing ribbon or activity.
    if (connected || transitioning) {
      for (final lane in [0, 1]) {
        final color = lane == 0 ? _mint : _ice;
        final values = lane == 0 ? rx : tx;
        final maximum = lane == 0 ? maxRx : maxTx;
        final direction = lane == 0 ? -1.0 : 1.0;
        final outer = Path();
        final middle = Path();
        final base = centerY + direction * 11;
        for (var i = 0; i < count; i++) {
          final t = i / (count - 1);
          final value = maximum > 0
              ? _sample(values, t) / maximum
              : 0.0;
          final amplitude = (active ? 8 + value * 34 : 4.0);
          final taper = .48 + .52 * math.sin(math.pi * t);
          final spine = base + direction * amplitude * taper;
          final x = left + t * width;
          if (i == 0) {
            outer.moveTo(x, base);
            middle.moveTo(x, spine);
          } else {
            outer.lineTo(x, base);
            middle.lineTo(x, spine);
          }
        }
        for (var i = count - 1; i >= 0; i--) {
          final t = i / (count - 1);
          final value = maximum > 0
              ? _sample(values, t) / maximum
              : 0.0;
          final amplitude = (active ? 8 + value * 34 : 4.0);
          final taper = .48 + .52 * math.sin(math.pi * t);
          final x = left + t * width;
          outer.lineTo(x, base + direction * amplitude * taper);
        }
        outer.close();
        canvas.drawPath(outer, Paint()
          ..shader = LinearGradient(
            begin: Alignment.topCenter, end: Alignment.bottomCenter,
            colors: [
              color.withValues(alpha: dark ? .06 : .04),
              color.withValues(alpha: dark ? .25 : .19),
              color.withValues(alpha: dark ? .02 : .01),
            ],
          ).createShader(rect));
        canvas.drawPath(middle, Paint()
          ..color = color.withValues(alpha: dark ? .21 : .17)
          ..strokeWidth = 11
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 9)
          ..style = PaintingStyle.stroke);
        canvas.drawPath(middle, Paint()
          ..shader = LinearGradient(colors: [
            color.withValues(alpha: .16),
            color.withValues(alpha: dark ? .98 : .87),
            color.withValues(alpha: .36),
          ]).createShader(rect)
          ..strokeWidth = 2.3
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round
          ..style = PaintingStyle.stroke);

        // Moving packet glints are shown only when the tunnel really transfers.
        if (active && maximum > 0) {
          for (var packet = 0; packet < 5; packet++) {
            final t = (phase + packet / 5) % 1;
            final value = _sample(values, t) / maximum;
            final amp = (8 + value * 34) *
                (.48 + .52 * math.sin(math.pi * t));
            final point = Offset(left + t * width, base + direction * amp);
            canvas.drawCircle(point, 7.5, Paint()
              ..color = color.withValues(alpha: .19)
              ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6));
            canvas.drawCircle(point, 2.5, Paint()
              ..color = color.withValues(alpha: .86));
          }
        }
      }
    }

    // Subtle receiver/transmitter anchors (not a play/power/lock glyph).
    for (final anchor in [left, left + width]) {
      canvas.drawCircle(Offset(anchor, centerY), 3,
          Paint()..color = _mint.withValues(alpha: .62));
      canvas.drawCircle(Offset(anchor, centerY), 7,
          Paint()
            ..color = _mint.withValues(alpha: .21)
            ..strokeWidth = 1
            ..style = PaintingStyle.stroke);
    }

    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _NetworkFabricPainter old) =>
      old.dark != dark || old.connected != connected ||
      old.connecting != connecting || old.phase != phase ||
      old.rx != rx || old.tx != tx;
}
