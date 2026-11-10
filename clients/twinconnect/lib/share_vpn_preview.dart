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
  String? _draftName;

  String tr(String fa, String en) => widget.persian ? fa : en;

  Future<void> _editWifi() async {
    final name = TextEditingController(text: _draftName ?? 'TwinConnect-Share');
    final password = TextEditingController();
    final form = GlobalKey<FormState>();
    try {
      final saved = await showDialog<String>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          key: const Key('devWifiEditDialog'),
          title: Text(tr('تنظیمات Wi-Fi', 'Wi-Fi settings')),
          content: Form(
            key: form,
            child: SizedBox(
              width: 360,
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Text(tr(
                  'این تنظیمات فقط پیش‌نمایش است و روی ویندوز اعمال نمی‌شود.',
                  'Preview only. No Wi-Fi or hotspot setting is applied.',
                )),
                const SizedBox(height: 15),
                TextFormField(
                  key: const Key('devWifiName'),
                  controller: name,
                  maxLength: 32,
                  decoration: InputDecoration(
                    labelText: tr('نام شبکه', 'Network name'),
                  ),
                  validator: (value) {
                    final text = value?.trim() ?? '';
                    return text.isEmpty || text.length > 32
                        ? tr('نام معتبر وارد کنید', 'Enter a valid name')
                        : null;
                  },
                ),
                TextFormField(
                  key: const Key('devWifiPassword'),
                  controller: password,
                  obscureText: true,
                  maxLength: 63,
                  decoration: InputDecoration(
                    labelText: tr('رمز Wi-Fi (آزمایشی)', 'Wi-Fi password (preview)'),
                    helperText: tr('رمز ذخیره نمی‌شود', 'Password is not stored'),
                  ),
                  validator: (value) {
                    final text = value ?? '';
                    return text.isEmpty || (text.length >= 8 && text.length <= 63)
                        ? null
                        : tr('رمز حداقل ۸ کاراکتر', 'Use at least 8 characters');
                  },
                ),
              ]),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(tr('انصراف', 'Cancel')),
            ),
            FilledButton(
              key: const Key('devWifiPreviewSave'),
              onPressed: () {
                if (form.currentState?.validate() == true) {
                  Navigator.of(dialogContext).pop(name.text.trim());
                }
              },
              child: Text(tr('ذخیره پیش‌نمایش', 'Save preview')),
            ),
          ],
        ),
      );
      if (saved != null && mounted) {
        setState(() => _draftName = saved);
      }
    } finally {
      // No passwords are retained or written to preferences.
      name.dispose();
      password.clear();
      password.dispose();
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
                tr('اشتراک‌گذاری هنوز فعال نیست',
                    'VPN sharing is not available yet'),
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
                  tr('نام و رمز شبکه Wi-Fi', 'Wi-Fi name & password'),
                  style: TextStyle(color: color, fontWeight: FontWeight.w700),
                )),
                TextButton(
                  key: const Key('devWifiEditButton'),
                  onPressed: _editWifi,
                  child: Text(tr('ویرایش', 'Edit')),
                ),
              ]),
              if (_draftName != null)
                Text(
                  tr('نام آزمایشی: $_draftName', 'Preview name: $_draftName'),
                  style: small,
                ),
              Text(
                tr('فقط پیش‌نمایش؛ تنظیمات شبکه ویندوز تغییر نمی‌کند.',
                   'Preview only. Windows network settings are unchanged.'),
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
