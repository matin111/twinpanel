import 'dart:io' show Platform, Process;

import 'package:flutter/material.dart';

import 'interactive_glass_card.dart';

/// Desktop Share VPN presentation. Native Wi-Fi hotspot, routing and
/// VPN egress sharing are NOT enabled until a privileged, verified adapter
/// reports that they are implemented. Never simulate an active hotspot.
class ShareVpnPreview extends StatefulWidget {
  const ShareVpnPreview({
    required this.dark,
    required this.persian,
    super.key,
  });

  final bool dark;
  final bool persian;

  @override
  State<ShareVpnPreview> createState() => _ShareVpnPreviewState();
}

class _ShareVpnPreviewState extends State<ShareVpnPreview> {
  static const accent = Color(0xFFA46AFF);

  String tr(String fa, String en) => widget.persian ? fa : en;

  Future<void> _editWifi() async {
    // Open the real Windows hotspot settings rather than storing a
    // deceptive Wi-Fi/password preview that never configures an adapter.
    if (!Platform.isWindows) {
      _guide();
      return;
    }
    try {
      await Process.start(
        'explorer.exe', ['ms-settings:network-mobilehotspot'],
        runInShell: false,
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(tr('تنظیمات هات‌اسپات ویندوز باز نشد.',
          'Could not open Windows Mobile hotspot settings.')),
      ));
    }
  }

  void _guide() {
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        key: const Key('devShareVpnGuide'),
        title: Text(tr('راهنمای اشتراک‌گذاری VPN', 'Share VPN guide')),
        content: Text(tr(
          'ابتدا اتصال واقعی VPN و سپس اشتراک‌گذاری شبکه در ویندوز باید '
          'توسط موتور بومی تأیید شوند. تا آن زمان هیچ دستگاهی به VPN '
          'اشتراکی متصل نمی‌شود و گزینه روشن‌کردن غیرفعال می‌ماند.',
          'A verified native VPN tunnel and Windows network-sharing adapter '
          'are both required. Sharing remains disabled until those capabilities '
          'are installed and verified.',
        )),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: Text(tr('بستن', 'Close')),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final secondary = widget.dark
        ? const Color(0xFFB8C7DD)
        : const Color(0xFF5E657B);
    final color = Theme.of(context).colorScheme.onSurface;
    final small = TextStyle(fontSize: 12, color: secondary, height: 1.65);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TwinConnectGlassCard(
          key: const Key('devShareVpnCard'),
          dark: widget.dark,
          radius: 24,
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(children: [
                Container(
                  height: 46, width: 46,
                  decoration: BoxDecoration(
                    color: accent.withValues(alpha: .18),
                    borderRadius: BorderRadius.circular(15),
                  ),
                  child: const Icon(Icons.wifi_tethering_rounded,
                      size: 25, color: accent),
                ),
                const SizedBox(width: 13),
                Expanded(child: Text(
                  tr('اشتراک‌گذاری VPN', 'Share VPN'),
                  style: TextStyle(color: color, fontSize: 18,
                      fontWeight: FontWeight.bold),
                )),
                const Switch(
                  key: Key('devShareVpnSwitch'),
                  value: false,
                  onChanged: null,
                ),
              ]),
              const SizedBox(height: 15),
              Container(
                height: 128,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(20),
                  gradient: LinearGradient(colors: [
                    accent.withValues(alpha: .17),
                    const Color(0xFF26BCBE).withValues(alpha: .09),
                  ]),
                ),
                child: Stack(alignment: Alignment.center, children: [
                  Container(
                    height: 106, width: 106,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: accent.withValues(alpha: .35)),
                    ),
                  ),
                  Container(
                    height: 77, width: 77,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: accent.withValues(alpha: .5)),
                    ),
                  ),
                  const Icon(Icons.wifi_tethering_rounded,
                      size: 43, color: accent),
                  const Positioned(
                    top: 15, right: 28,
                    child: Icon(Icons.laptop_windows_rounded,
                        size: 26, color: Color(0xFF85CDE0)),
                  ),
                  const Positioned(
                    bottom: 17, left: 34,
                    child: Icon(Icons.phone_android_rounded,
                        size: 23, color: Color(0xFF85CDE0)),
                  ),
                ]),
              ),
              const SizedBox(height: 13),
              Text(
                tr('اشتراک VPN در این نسخه تأیید نشده',
                    'VPN sharing is not verified in this build'),
                style: TextStyle(
                  color: color, fontWeight: FontWeight.w700, fontSize: 14),
              ),
              const SizedBox(height: 6),
              Text(
                tr('برای اشتراک اتصال امن با دستگاه‌های دیگر، '
                   'ابتدا باید موتور VPN و قابلیت Hotspot ویندوز فعال و تأیید شوند.',
                   'Requires a verified VPN tunnel and Windows hotspot '
                   'capabilities before sharing with other devices.'),
                style: small,
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        TwinConnectGlassCard(
          key: const Key('devWifiSettingsCard'),
          dark: widget.dark,
          radius: 20,
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(children: [
                const Icon(Icons.router_outlined, color: accent),
                const SizedBox(width: 10),
                Expanded(child: Text(
                  tr('هات‌اسپات ویندوز', 'Windows Mobile hotspot'),
                  style: TextStyle(color: color, fontWeight: FontWeight.w700),
                )),
                TextButton(
                  key: const Key('devWifiEditButton'),
                  onPressed: _editWifi,
                  child: Text(tr('بازکردن تنظیمات', 'Open settings')),
                ),
              ]),
              Text(
                tr('تنظیم نام و رمز در ویندوز انجام می‌شود؛ فعال‌کردن هات‌اسپات به معنای اشتراک VPN نیست.',
                   'Configure Wi-Fi in Windows. Hotspot availability does not prove that VPN traffic is being shared.'),
                style: small,
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        TwinConnectGlassCard(
          key: const Key('devShareVpnGuideCard'),
          dark: widget.dark,
          radius: 20,
          padding: const EdgeInsets.all(10),
          child: Material(
            color: Colors.transparent,
            child: ListTile(
              leading: const Icon(Icons.menu_book_outlined, color: accent),
              title: Text(tr('راهنمای اشتراک‌گذاری',
                  'Share VPN guide')),
              subtitle: Text(tr('مراحل و پیش‌نیازهای اتصال',
                  'How it works and what is needed')),
              trailing: const Icon(Icons.chevron_right_rounded),
              onTap: _guide,
            ),
          ),
        ),
      ],
    );
  }
}
