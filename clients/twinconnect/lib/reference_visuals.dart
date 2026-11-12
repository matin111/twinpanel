import 'dart:math' as math;
import 'package:flutter/material.dart';

/// Purely decorative, low-cost reference artwork. Never represents measured data.
class NeonRing extends StatelessWidget {
  const NeonRing({super.key, required this.child, required this.active});
  final Widget child;
  final bool active;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: 292,
    height: 292,
    child: CustomPaint(
      painter: _NeonRingPainter(active: active),
      child: Center(child: child),
    ),
  );
}

class _NeonRingPainter extends CustomPainter {
  _NeonRingPainter({required this.active});
  final bool active;
  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) / 2;
    final soft = Paint()..style = PaintingStyle.stroke..strokeWidth = 1;
    for (var i = 0; i < 3; i++) {
      soft.color = (i.isEven ? const Color(0xFF00E5F2) : const Color(0xFF9F43FF))
          .withValues(alpha: active ? .3 : .16);
      canvas.drawCircle(center, radius - 3 - i * 17, soft);
    }
    final ticks = Paint()..strokeCap = StrokeCap.round;
    for (var i = 0; i < 56; i++) {
      final a = 2 * math.pi * i / 56 - math.pi / 2;
      final inner = radius - 28;
      final outer = inner + (i % 7 == 0 ? 5 : 2.2);
      ticks
        ..color = Color.lerp(const Color(0xFF00E5F2),
            const Color(0xFFEA48FF), i / 56)!.withValues(alpha: active ? 1 : .65)
        ..strokeWidth = i % 7 == 0 ? 3 : 2;
      canvas.drawLine(center + Offset(math.cos(a) * inner, math.sin(a) * inner),
          center + Offset(math.cos(a) * outer, math.sin(a) * outer), ticks);
    }
  }

  @override
  bool shouldRepaint(covariant _NeonRingPainter old) => active != old.active;
}

class AmbientWave extends StatelessWidget {
  const AmbientWave({super.key, this.height = 160});
  final double height;
  @override
  Widget build(BuildContext context) => IgnorePointer(
    child: SizedBox(height: height,
      width: double.infinity, child: CustomPaint(painter: _AmbientWavePainter())),
  );
}

class _AmbientWavePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    for (var j = 0; j < 23; j++) {
      final path = Path();
      final base = size.height * (.53 + (j - 11) * .011);
      for (double x = 0; x <= size.width; x += 3) {
        final y = base + math.sin((x / size.width * 2.4 * math.pi) + j * .063)
            * (size.height * .23)
            + math.sin(x / size.width * 5.5 * math.pi) * size.height * .055;
        if (x == 0) {path.moveTo(x, y);} else {path.lineTo(x, y);}
      }
      canvas.drawPath(path, Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = .8
        ..color = Color.lerp(const Color(0xFF00E5F2),
           const Color(0xFFB34CFF), j / 23)!.withValues(alpha: .13 + j / 160));
    }
  }
  @override
  bool shouldRepaint(covariant _AmbientWavePainter old) => false;
}

class ReferenceSparkline extends StatelessWidget {
  const ReferenceSparkline({super.key, required this.color});
  final Color color;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: 22,
    child: CustomPaint(painter: _SparklinePainter(color), size: const Size(double.infinity, 22)),
  );
}

class _SparklinePainter extends CustomPainter {
  _SparklinePainter(this.color);
  final Color color;
  @override
  void paint(Canvas canvas, Size size) {
    final path = Path();
    for (double x = 0; x <= size.width; x += 2) {
      final y = size.height * .65
          - math.sin(x / math.max(1, size.width) * math.pi * 3.5)
              * size.height * .18
          - x / math.max(1, size.width) * size.height * .23;
      if (x == 0) {path.moveTo(x, y);} else {path.lineTo(x, y);}
    }
    canvas.drawPath(path, Paint()..style = PaintingStyle.stroke
      ..strokeWidth = 2..strokeCap = StrokeCap.round
      ..color = color);
  }
  @override
  bool shouldRepaint(covariant _SparklinePainter old) => old.color != color;
}

class RingGauge extends StatelessWidget {
  const RingGauge({super.key, required this.color, required this.icon,
      required this.label, required this.value});
  final Color color;
  final IconData icon;
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      SizedBox(height: 55, width: 112, child: CustomPaint(
        painter: _RingGaugePainter(color))),
      Row(children: [
        Icon(icon, size: 23, color: color),
        const SizedBox(width: 7),
        Expanded(child: Text(label, maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(color: Color(0xFFADB4D8), fontSize: 13))),
      ]),
      const SizedBox(height: 7),
      Text(value, overflow: TextOverflow.ellipsis, maxLines: 1,
          style: const TextStyle(fontSize: 20,
            fontWeight: FontWeight.bold, color: Colors.white)),
    ],
  );
}
class _RingGaugePainter extends CustomPainter {
  _RingGaugePainter(this.color);
  final Color color;
  @override
  void paint(Canvas canvas, Size size) {
    const start = math.pi * 1.08;
    const sweep = math.pi * .85;
    final rect = Rect.fromLTWH(9, 10, size.width - 18, size.width - 18);
    final background = Paint()..style = PaintingStyle.stroke
      ..strokeWidth = 8..strokeCap = StrokeCap.round
      ..color = const Color(0xFF33376B);
    canvas.drawArc(rect, start, sweep, false, background);
    // Decorative arc only: intentionally NOT a fabricated live speed percentage.
    canvas.drawArc(rect, start, sweep * .55, false,
        Paint()..style = PaintingStyle.stroke..strokeWidth = 8
          ..strokeCap = StrokeCap.round..color = color);
  }
  @override
  bool shouldRepaint(covariant _RingGaugePainter old) => old.color != color;
}
