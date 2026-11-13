import 'dart:math' as math;
import 'package:flutter/material.dart';

/// Samples are measured byte/second values from the active native tunnel.
/// Nothing is animated or drawn as simulated traffic when samples are empty.
class TunnelTrafficChart extends StatelessWidget {
  const TunnelTrafficChart({
    super.key,
    required this.samples,
    required this.color,
    required this.dark,
    this.height = 55,
  });
  final List<double> samples;
  final Color color;
  final bool dark;
  final double height;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: height,
    child: samples.isEmpty
        ? Center(child: Text('—', style: TextStyle(
            fontSize: 19, color: color.withValues(alpha: .45))))
        : CustomPaint(
            key: const Key('liveTrafficChartCanvas'),
            painter: _TrafficChartPainter(samples, color, dark),
            size: Size.infinite,
          ),
  );
}

class _TrafficChartPainter extends CustomPainter {
  const _TrafficChartPainter(this.values, this.color, this.dark);
  final List<double> values;
  final Color color;
  final bool dark;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.width <= 2 || size.height <= 2 || values.isEmpty) return;
    final maxValue = values.reduce(math.max);
    final scale = maxValue <= 0 ? 1.0 : maxValue * 1.18;
    final line = Path();
    final fill = Path();
    const bottomPad = 5.0;
    final base = size.height - bottomPad;
    final step = values.length < 2 ? 0.0 :
        size.width / (values.length - 1);
    for (var i = 0; i < values.length; i++) {
      final x = values.length == 1 ? size.width / 2 : i * step;
      final y = base - (values[i].clamp(0, scale) / scale) *
          (size.height - 11);
      if (i == 0) {
        line.moveTo(x, y);
        fill.moveTo(x, base);
        fill.lineTo(x, y);
      } else {
        line.lineTo(x, y);
        fill.lineTo(x, y);
      }
    }
    final lastX = values.length == 1 ? size.width / 2 : size.width;
    fill.lineTo(lastX, base);
    fill.close();

    canvas.drawPath(fill, Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [color.withValues(alpha: dark ? .26 : .19),
          color.withValues(alpha: 0)],
      ).createShader(Offset.zero & size));
    canvas.drawPath(line, Paint()
      ..style = PaintingStyle.stroke
      ..color = color.withValues(alpha: .22)
      ..strokeWidth = 6
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 5));
    canvas.drawPath(line, Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..strokeWidth = 2.2
      ..color = color);
  }

  @override
  bool shouldRepaint(covariant _TrafficChartPainter other) =>
      other.color != color || other.dark != dark ||
      !listEqualsDouble(other.values, values);
}

bool listEqualsDouble(List<double> a, List<double> b) {
  if (identical(a, b)) return true;
  if (a.length != b.length) return false;
  for (var i = 0; i < a.length; i++) {
    if (a[i] != b[i]) return false;
  }
  return true;
}
