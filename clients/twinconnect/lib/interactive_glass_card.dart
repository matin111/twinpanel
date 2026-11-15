import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';

/// A restrained desktop glass surface with mouse-responsive lighting.
///
/// Animations run only on entrance / pointer changes (no permanent ticker).
/// The content remains fully interactive and accessibility friendly.
class TwinConnectGlassCard extends StatefulWidget {
  const TwinConnectGlassCard({
    required this.child,
    required this.dark,
    this.surfaceColor,
    this.accentColor,
    this.radius = 20,
    this.padding = EdgeInsets.zero,
    this.selected = false,
    super.key,
  });

  final Widget child;
  final bool dark;
  final Color? surfaceColor;
  final Color? accentColor;
  final double radius;
  final EdgeInsetsGeometry padding;
  final bool selected;

  @override
  State<TwinConnectGlassCard> createState() => _TwinConnectGlassCardState();
}

class _TwinConnectGlassCardState extends State<TwinConnectGlassCard> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final bright = widget.dark;
    final accent = widget.accentColor ?? const Color(0xFFA46AFF);
    final surface = widget.surfaceColor ??
        (bright ? const Color(0xFF273753) : Colors.white);
    final active = widget.selected || _hovered;
    final radius = BorderRadius.circular(widget.radius);
    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: AnimatedScale(
        key: const Key('glassHoverMotion'),
        scale: _hovered ? 1.008 : 1,
        curve: Curves.easeOutCubic,
        duration: const Duration(milliseconds: 220),
        alignment: Alignment.center,
        child: ClipRRect(
          borderRadius: radius,
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 240),
              curve: Curves.easeOutCubic,
              padding: widget.padding,
              decoration: BoxDecoration(
                color: surface.withValues(alpha: bright ? .55 : .68),
                borderRadius: radius,
                border: Border.all(
                  color: active
                      ? accent.withValues(alpha: .68)
                      : (bright ? Colors.white : const Color(0xFF6575AB))
                          .withValues(alpha: bright ? .20 : .16),
                  width: active ? 1.15 : .9,
                ),
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  stops: const [0, .42, 1],
                  colors: [
                    Color.lerp(surface, accent, active ? .18 : .075)!
                        .withValues(alpha: bright ? .64 : .73),
                    surface.withValues(alpha: bright ? .51 : .64),
                    Color.lerp(surface, bright ? Colors.black : Colors.white,
                        bright ? .12 : .045)!
                        .withValues(alpha: bright ? .59 : .70),
                  ],
                ),
                boxShadow: [
                  BoxShadow(
                    color: (active ? accent : Colors.black).withValues(
                      alpha: active ? .11 : (bright ? .06 : .03)),
                    blurRadius: active ? 28 : 15,
                    offset: const Offset(0, 8),
                  ),
                ],
              ),
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  Positioned(
                    top: -55, right: -58,
                    child: IgnorePointer(
                      child: AnimatedOpacity(
                        duration: const Duration(milliseconds: 260),
                        opacity: active ? 1 : .42,
                        child: Container(
                          width: 140, height: 140,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            gradient: RadialGradient(colors: [
                              accent.withValues(alpha: bright ? .16 : .11),
                              accent.withValues(alpha: 0),
                            ]),
                          ),
                        ),
                      ),
                    ),
                  ),
                  widget.child,
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
