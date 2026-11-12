import 'dart:io' show Platform;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Small floating window actions; deliberately no header/title bar.
class TwinConnectFramelessControls extends StatelessWidget {
  const TwinConnectFramelessControls({super.key});

  static const _native = MethodChannel('com.twinpanel.twinconnect/vpn');

  Future<void> _action(String action) async {
    try {
      await _native.invokeMethod<bool>('windowControl', {'action': action});
    } on PlatformException {
      // Never terminate processes directly: native close is responsible
      // for disconnecting active VPN interfaces before leaving.
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!Platform.isWindows) return const SizedBox.shrink();
    final dark = Theme.of(context).brightness == Brightness.dark;
    final foreground = dark ? const Color(0xFFECEAFF) : const Color(0xFF23243C);
    final backdrop = dark ? const Color(0xFF111322) : Colors.white;
    return Stack(
      children: [
        // A thin invisible drag target, leaving the entire UI unobstructed.
        Positioned(
          top: 0, left: 0, right: 104, height: 9,
          child: GestureDetector(
            key: const Key('windowsFramelessDrag'),
            behavior: HitTestBehavior.opaque,
            onPanStart: (_) => _action('drag'),
          ),
        ),
        Positioned(
          top: 4, right: 6,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: backdrop.withValues(alpha: .24),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                _control(
                  key: const Key('windowsMinimize'),
                  icon: Icons.remove_rounded,
                  tooltip: 'Minimize',
                  foreground: foreground,
                  onPressed: () => _action('minimize'),
                ),
                _control(
                  key: const Key('windowsMaximize'),
                  icon: Icons.crop_square_rounded,
                  tooltip: 'Maximize / restore',
                  foreground: foreground,
                  onPressed: () => _action('maximize'),
                ),
                _control(
                  key: const Key('windowsClose'),
                  icon: Icons.close_rounded,
                  tooltip: 'Close TwinConnect',
                  foreground: foreground,
                  onPressed: () => _action('close'),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _control({
    required Key key,
    required IconData icon,
    required String tooltip,
    required Color foreground,
    required VoidCallback onPressed,
  }) {
    return IconButton(
      key: key,
      // This widget is drawn above Navigator by MaterialApp.builder.
      // Flutter's Tooltip requires an Overlay below it and would throw
      // on login and the authenticated screen. Expose semantics instead.
      tooltip: null,
      iconSize: 16,
      visualDensity: VisualDensity.compact,
      constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
      padding: const EdgeInsets.all(4),
      color: foreground,
      icon: Semantics(label: tooltip, button: true, child: Icon(icon)),
      onPressed: onPressed,
    );
  }
}
