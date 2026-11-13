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
    this.secondaryColor,
    this.radius = 20,
    this.padding = EdgeInsets.zero,
    this.selected = false,
    super.key,
  });

  final Widget child;
  final bool dark;
  final Color? surfaceColor;
  final Color? accentColor;
  final Color? secondaryColor;
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
    final accent = widget.accentColor ?? const Color(0xFF6FA7B8);
    // Respect the reseller palette, with a subtle electric cyan reflection
    // for depth. The secondary stays tenant-derived, never replaces branding.
    final secondary = widget.secondaryColor ?? const Color(0xFF62C1B4);
    final reflection = Color.lerp(secondary, const Color(0xFF9CD9D0),
        widget.dark ? .24 : .10)!;
    final surface = widget.surfaceColor ??
        (bright ? const Color(0xFF1B2B36) : Colors.white);
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
            filter: ImageFilter.blur(sigmaX: 15, sigmaY: 15),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 240),
              curve: Curves.easeOutCubic,
              padding: widget.padding,
              decoration: BoxDecoration(
                color: surface.withValues(alpha: bright ? .24 : .39),
                borderRadius: radius,
                border: Border.all(
                  color: active
                      ? accent.withValues(alpha: .88)
                      : (bright ? Colors.white : accent)
                          .withValues(alpha: bright ? .24 : .18),
                  width: active ? 1.3 : 1,
                ),
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  stops: const [0, .46, 1],
                  colors: [
                    Color.lerp(surface, accent, active ? .29 : .16)!
                        .withValues(alpha: bright ? .31 : .43),
                    surface.withValues(alpha: bright ? .19 : .37),
                    Color.lerp(surface, reflection, active ? .25 : .13)!
                        .withValues(alpha: bright ? .31 : .41),
                  ],
                ),
                boxShadow: [
                  BoxShadow(
                    color: (active ? accent : Colors.black).withValues(
                      alpha: active ? .28 : (bright ? .13 : .06)),
                    blurRadius: active ? 30 : 17,
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
                              reflection.withValues(alpha: bright ? .24 : .13),
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
