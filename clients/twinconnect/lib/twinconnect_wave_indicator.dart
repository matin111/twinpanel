import 'dart:math' as math;
import 'package:flutter/material.dart';

/// Native connection indicator: idle stays still; real verified connection
/// produces subtle mint ripples. Connecting pulses in muted steel-blue.
class TwinConnectWaveIndicator extends StatefulWidget {
  const TwinConnectWaveIndicator({
    super.key, required this.connected, required this.connecting,
    required this.dark,
  });

  final bool connected;
  final bool connecting;
  final bool dark;

  @override
  State<TwinConnectWaveIndicator> createState() => _TwinConnectWaveIndicatorState();
}

class _TwinConnectWaveIndicatorState extends State<TwinConnectWaveIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse = AnimationController(
    vsync: this, duration: const Duration(milliseconds: 2600),
  );

  bool get _active => widget.connected || widget.connecting;

  @override
  void initState() {
    super.initState();
    if (_active) _pulse.repeat();
  }

  @override
  void didUpdateWidget(covariant TwinConnectWaveIndicator oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_active && !_pulse.isAnimating) _pulse.repeat();
    if (!_active && _pulse.isAnimating) {
      _pulse.stop();
      _pulse.value = 0;
    }
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final accent = widget.connected
        ? const Color(0xFF64C9A7) : const Color(0xFF78AFC1);
    return SizedBox(
      width: 158, height: 138,
      child: Stack(alignment: Alignment.center, children: [
        if (_active)
          AnimatedBuilder(
            animation: _pulse,
            builder: (context, child) => CustomPaint(
              size: const Size(158, 138),
              painter: _RipplePainter(progress: _pulse.value, color: accent),
            ),
          ),
        Container(
          width: 86, height: 86,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(27),
            gradient: LinearGradient(
              begin: Alignment.topLeft, end: Alignment.bottomRight,
              colors: widget.connected
                  ? [const Color(0xFF24594F), const Color(0xFF337869)]
                  : widget.connecting
                      ? [const Color(0xFF335769), const Color(0xFF466E81)]
                      : widget.dark
                          ? [const Color(0xFF29404D), const Color(0xFF22323E)]
                          : [const Color(0xFFE1ECF0), const Color(0xFFD4E4EA)],
            ),
            border: Border.all(color: accent.withValues(alpha: .40)),
            boxShadow: [
              BoxShadow(color: accent.withValues(
                alpha: widget.connected ? .18 : .07), blurRadius: 27),
            ],
          ),
          child: Icon(
            widget.connected ? Icons.lock_rounded
                : widget.connecting ? Icons.sync_rounded
                : Icons.power_settings_new_rounded,
            color: widget.connected || widget.connecting
                ? const Color(0xFFE3FFF4)
                : widget.dark ? const Color(0xFFB6CFD8)
                : const Color(0xFF3F6779),
            size: 37,
          ),
        ),
      ]),
    );
  }
}

class _RipplePainter extends CustomPainter {
  const _RipplePainter({required this.progress, required this.color});
  final double progress;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    for (var i = 0; i < 3; i++) {
      final t = (progress + i / 3) % 1;
      final radius = 43 + (t * 24);
      final opacity = math.pow(1 - t, 1.6).toDouble() * .48;
      canvas.drawCircle(center, radius, Paint()
        ..color = color.withValues(alpha: opacity)
        ..strokeWidth = 2 - t
        ..style = PaintingStyle.stroke);
    }
  }

  @override
  bool shouldRepaint(covariant _RipplePainter old) =>
      old.progress != progress || old.color != color;
}
