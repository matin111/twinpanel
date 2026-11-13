import 'package:flutter/material.dart';

import 'app_strings.dart';
import 'brand_theme.dart';
import 'interactive_glass_card.dart';
import 'native_vpn_bridge.dart';
import 'vpn_policy.dart';
import 'tenant_models.dart';

/// One-page, fail-closed network settings. A saved preference is not proof of
/// enforcement; no unsupported switch is shown as working.
class VpnSettingsScreen extends StatefulWidget {
  const VpnSettingsScreen({
    required this.tenant,
    required this.account,
    this.brand,
    this.embedded = false,
    super.key,
  });

  final String tenant;
  final String account;
  final BrandPreview? brand;
  final bool embedded;

  @override
  State<VpnSettingsScreen> createState() => _VpnSettingsScreenState();
}

class _VpnSettingsScreenState extends State<VpnSettingsScreen> {
  NativeVpnCapabilities _capabilities =
      NativeVpnCapabilities.unavailable(NativeVpnBridge.platform);
  Map<String, dynamic> _guard = const {};
  bool _checking = false;

  @override
  void initState() {
    super.initState();
    _check();
  }

  Future<void> _check() async {
    if (_checking) return;
    setState(() => _checking = true);
    NativeVpnCapabilities capabilities =
        NativeVpnCapabilities.unavailable(NativeVpnBridge.platform);
    Map<String, dynamic> guard = const {};
    try {
      // Native status probes can stall on unhealthy Windows services.
      // The page must recover rather than remain in a loading state.
      final results = await Future.wait<Object>([
        NativeVpnBridge.probe().timeout(const Duration(seconds: 5)),
        NativeVpnBridge.globalKillSwitchStatus()
            .timeout(const Duration(seconds: 5)),
      ]);
      capabilities = results[0] as NativeVpnCapabilities;
      guard = results[1] as Map<String, dynamic>;
    } catch (_) {
      // Never turn a timed-out or failed check into a 'protected' state.
    }
    if (!mounted) return;
    setState(() {
      _capabilities = capabilities;
      _guard = guard;
      _checking = false;
    });
  }

  bool get _guardActive =>
      _guard['serviceInstalled'] == true &&
      _guard['armed'] == true &&
      _guard['enforcedV4'] == true &&
      _guard['enforcedV6'] == true &&
      _guard['recoveryVerified'] == true;

  void _explain(String title, String description) {
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: Theme.of(ctx).colorScheme.surface.withValues(alpha: .97),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(22),
          side: BorderSide(
            color: Theme.of(ctx).colorScheme.primary.withValues(alpha: .27),
          ),
        ),
        title: Row(children: [
          Container(
            padding: const EdgeInsets.all(9),
            decoration: BoxDecoration(
              color: Theme.of(ctx).colorScheme.primary.withValues(alpha: .13),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(Icons.help_outline_rounded,
                color: Theme.of(ctx).colorScheme.primary, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(child: Text(title, style: const TextStyle(
            fontSize: 17, fontWeight: FontWeight.w700,
          ))),
        ]),
        content: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 400),
          child: Text(description, style: const TextStyle(
            fontSize: 14, height: 1.55,
          )),
        ),
        actionsPadding: const EdgeInsets.fromLTRB(18, 0, 18, 14),
        actions: [
          FilledButton.tonal(
            onPressed: () => Navigator.of(ctx).pop(),
            child: Text(AppStrings.of(ctx).pick('متوجه شدم', 'Got it')),
          ),
        ],
      ),
    );
  }

  Widget _help(String title, String description) => IconButton(
    key: Key('vpnHelp_${title.hashCode}'),
    tooltip: AppStrings.of(context).pick('توضیحات', 'Details'),
    icon: const Icon(Icons.help_outline_rounded, size: 19),
    onPressed: () => _explain(title, description),
  );

  Widget _glass(Widget child, {Key? key}) => TwinConnectGlassCard(
    key: key,
    dark: Theme.of(context).brightness == Brightness.dark,
    surfaceColor: Theme.of(context).colorScheme.surface,
    accentColor: Theme.of(context).colorScheme.primary,
    radius: 18,
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
    child: Material(type: MaterialType.transparency, child: child),
  );

  Widget _routingOption({
    required String label,
    required String help,
    required bool selected,
    required bool enabled,
    required Key key,
  }) => Row(key: key, children: [
    Icon(selected ? Icons.radio_button_checked_rounded
                  : Icons.radio_button_unchecked_rounded,
      color: selected ? Theme.of(context).colorScheme.primary
          : Theme.of(context).disabledColor, size: 20),
    const SizedBox(width: 12),
    Expanded(child: Text(label, style: TextStyle(
      fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
      color: enabled ? null : Theme.of(context).disabledColor,
    ))),
    _help(label, help),
    if (!enabled) const Icon(Icons.lock_outline_rounded, size: 17),
  ]);

  Widget _statusItem({
    required String title,
    required String help,
    required IconData icon,
    required String value,
    required bool ready,
    Key? key,
  }) => _glass(
    Row(children: [
      Container(
        width: 36, height: 36,
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.primary.withValues(alpha: .13),
          borderRadius: BorderRadius.circular(11),
        ),
        child: Icon(icon, size: 19),
      ),
      const SizedBox(width: 10),
      Expanded(child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
          Text(value, style: TextStyle(
            fontSize: 11,
            color: ready ? const Color(0xFF47CBA8)
                : Theme.of(context).colorScheme.onSurface.withValues(alpha: .60),
          )),
        ],
      )),
      _help(title, help),
    ]),
    key: key,
  );

  Widget _section(String title) => Padding(
    padding: const EdgeInsets.only(top: 14, bottom: 9),
    child: Text(title, style: Theme.of(context).textTheme.titleMedium?.copyWith(
      fontWeight: FontWeight.w700,
    )),
  );

  @override
  Widget build(BuildContext context) {
    final s = AppStrings.of(context);
    String tr(String fa, String en) => s.pick(fa, en);
    final globalReady = _guard['wfpAvailable'] == true;
    final content = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _section(tr('امنیت سیستم', 'System security')),
        _glass(
          Row(children: [
            const Icon(Icons.shield_rounded, size: 25),
            const SizedBox(width: 13),
            Expanded(child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Kill Switch', style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.bold)),
                Text(_guardActive
                    ? tr('محافظت سیستم تأیید شده', 'System protection verified')
                    : globalReady
                        ? tr('سرویس محافظت هنوز آماده نیست', 'Protection service not ready')
                        : tr('محافظت سراسری در دسترس نیست', 'System protection unavailable'),
                    style: Theme.of(context).textTheme.bodySmall),
              ],
            )),
            _help('Kill Switch', tr(
              'این قابلیت باید هنگام قطع VPN، ترافیک مستقیم IPv4 و IPv6 کل سیستم را مسدود کند. صرف آماده‌بودن WFP به معنی فعال‌بودن محافظت نیست. تا نصب و آزمایش سرویس مستقل ویندوز نمی‌توان آن را روشن کرد.',
              'Blocks direct system-wide IPv4/IPv6 traffic when the VPN drops. WFP availability alone does not mean protection is active. It cannot be enabled until the independent Windows service is installed and tested.',
            )),
            Switch.adaptive(
              key: const Key('vpnKillSwitch'),
              value: _guardActive,
              onChanged: null, // Never allow cosmetic activation.
            ),
          ]),
          key: const Key('vpnKillSwitchCard'),
        ),
        const SizedBox(height: 8),
        _glass(
          Row(children: [
            const Icon(Icons.fact_check_outlined, size: 21),
            const SizedBox(width: 12),
            Expanded(child: Text(
              tr('بررسی وضعیت امنیت', 'Check security status'),
              style: const TextStyle(fontWeight: FontWeight.w600),
            )),
            _help(tr('بررسی امنیت', 'Security diagnostics'), tr(
              'وضعیت موتور اتصال و محافظ ویندوز را دوباره بررسی می‌کند و هیچ تغییری در شبکه ایجاد نمی‌کند.',
              'Rechecks the VPN engine and Windows guard without changing network configuration.',
            )),
            IconButton(
              key: const Key('vpnCapabilityRefresh'),
              tooltip: tr('بررسی مجدد', 'Recheck'),
              onPressed: _checking ? null : _check,
              icon: _checking
                  ? const SizedBox(width: 18, height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.refresh_rounded),
            ),
          ]),
        ),
        _section(tr('حالت اتصال', 'Connection mode')),
        _glass(Row(children: [
          const Icon(Icons.route_rounded, size: 22),
          const SizedBox(width: 12),
          Expanded(child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(tr('VPN / TUN', 'VPN / TUN'),
                  style: const TextStyle(fontWeight: FontWeight.w700)),
              Text(_capabilities.engineReady && _capabilities.fullTunnel
                  ? tr('تونل دستگاه پشتیبانی می‌شود', 'Device tunnel supported')
                  : tr('در این دستگاه تأیید نشده', 'Not verified on this device'),
                  style: Theme.of(context).textTheme.bodySmall),
            ],
          )),
          _help('VPN / TUN', tr(
            'حالت تمام‌تونل که ترافیک دستگاه را از مسیر VPN هدایت می‌کند. فعال بودن موتور به‌تنهایی تضمین نمی‌کند که همه ترافیک بدون نشت منتقل می‌شود.',
            'Full-device tunneling. Engine support alone is not proof against leaks.',
          )),
          Icon(_capabilities.engineReady && _capabilities.fullTunnel
              ? Icons.check_circle_rounded : Icons.lock_outline_rounded,
              color: _capabilities.engineReady && _capabilities.fullTunnel
                  ? const Color(0xFF47CBA8) : null),
        ]), key: const Key('vpnTunMode')),
        const SizedBox(height: 8),
        _glass(Row(children: [
          const Icon(Icons.swap_horiz_rounded, size: 22),
          const SizedBox(width: 12),
          Expanded(child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(tr('Proxy / System Proxy', 'Proxy / System Proxy'),
                  style: const TextStyle(fontWeight: FontWeight.w700)),
              Text(tr('موتور تغییر مسیر پروکسی هنوز متصل نیست',
                      'Proxy switching engine not integrated'),
                  style: Theme.of(context).textTheme.bodySmall),
            ],
          )),
          _help('Proxy', tr(
            'حالت پروکسی فقط برنامه‌هایی را پوشش می‌دهد که از SOCKS یا پروکسی سیستم پیروی می‌کنند. با VPN کل سیستم تفاوت دارد؛ هنوز امکان تغییر امن حالت از این بخش فراهم نشده است.',
            'A local SOCKS/system proxy only covers proxy-aware apps. Safe mode switching is not yet integrated.',
          )),
          const Icon(Icons.lock_outline_rounded),
        ]), key: const Key('vpnProxyModeUnavailable')),
        _section(tr('تفکیک برنامه‌ها', 'Split tunneling')),
        _glass(Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _routingOption(
              label: tr('تمام دستگاه', 'Entire device'),
              selected: true,
              enabled: true,
              help: tr('در وضعیت فعلی تمام ترافیک دستگاه از VPN عبور می‌کند؛ البته با توجه به محدودیت پروتکل و تنظیمات شبکه.',
                  'Currently routes device traffic via VPN, subject to the protocol and OS routing capabilities.'),
              key: const Key('vpnRoutingFullTunnel'),
            ),
            Divider(height: 12, color: Theme.of(context).dividerColor),
            _routingOption(
              label: tr('فقط برنامه‌های انتخابی', 'Only selected apps'),
              selected: false,
              enabled: false,
              help: tr('این حالت تنها پس از اضافه‌شدن فیلتر واقعی بسته‌های برنامه‌ها و انتخاب برنامه‌های نصب‌شده فعال می‌شود.',
                  'Requires a verified per-app packet routing implementation and an installed-app picker.'),
              key: const Key('vpnRoutingIncludeApps'),
            ),
            Divider(height: 12, color: Theme.of(context).dividerColor),
            _routingOption(
              label: tr('همه به‌جز برنامه‌های انتخابی', 'Exclude selected apps'),
              selected: false,
              enabled: false,
              help: tr('برای عبور مستقیم برنامه‌های مشخص باید قوانین واقعی سیستم‌عامل ساخته و تست شوند.',
                  'Requires verified OS routing rules for applications excluded from the VPN.'),
              key: const Key('vpnRoutingExcludeApps'),
            ),
          ],
        ), key: const Key('vpnSplitTunnelCard')),
        _section(tr('وضعیت شبکه', 'Network status')),
        LayoutBuilder(builder: (context, constraints) {
          final compact = constraints.maxWidth < 550;
          final width = compact ? constraints.maxWidth : (constraints.maxWidth - 10) / 2;
          return Wrap(spacing: 10, runSpacing: 10, children: [
            SizedBox(width: width, child: _statusItem(
              key: const Key('vpnNativeEngineStatus'),
              title: tr('موتور VPN', 'VPN engine'),
              value: _capabilities.engineReady
                  ? tr('آماده', 'Ready') : tr('در دسترس نیست', 'Unavailable'),
              ready: _capabilities.engineReady,
              icon: Icons.power_rounded,
              help: tr('آمادگی موتور اتصال به معنی متصل‌بودن VPN نیست.',
                'An available engine does not mean VPN is connected.'),
            )),
            SizedBox(width: width, child: _statusItem(
              key: const Key('vpnWfpStatus'),
              title: tr('فایروال ویندوز', 'Windows firewall engine'),
              value: globalReady ? tr('شناسایی شد', 'Detected') :
                  tr('در دسترس نیست', 'Unavailable'),
              ready: globalReady,
              icon: Icons.security_rounded,
              help: tr('شناسایی WFP فقط پیش‌نیاز Kill Switch است و به معنی مسدودسازی ترافیک نیست.',
                  'WFP detection is only a prerequisite and does not mean traffic is blocked.'),
            )),
            SizedBox(width: width, child: _statusItem(
              key: const Key('vpnDnsGuard'),
              title: tr('حفاظت DNS', 'DNS protection'),
              value: _capabilities.dnsGuard
                  ? tr('پشتیبانی موتور', 'Engine supports')
                  : tr('تأیید نشده', 'Not verified'),
              ready: _capabilities.dnsGuard,
              icon: Icons.dns_rounded,
              help: tr('وضعیت پشتیبانی موتور است؛ جلوگیری قطعی از نشت DNS فقط با تست اتصال مشخص می‌شود.',
                  'This reports engine support; actual DNS leak protection needs a live connection test.'),
            )),
            SizedBox(width: width, child: _statusItem(
              key: const Key('vpnIpv6Guard'),
              title: tr('حفاظت IPv6', 'IPv6 protection'),
              value: _capabilities.ipv6Guard
                  ? tr('پشتیبانی موتور', 'Engine supports')
                  : tr('تأیید نشده', 'Not verified'),
              ready: _capabilities.ipv6Guard,
              icon: Icons.lan_rounded,
              help: tr('این نشانگر پشتیبانی را نمایش می‌دهد، نه تأیید عدم نشت IPv6.',
                  'Shows reported engine support, not a confirmed IPv6 leak test.'),
            )),
          ]);
        }),
        const SizedBox(height: 12),
        Text(tr('فقط امکانات فعال و قابل بررسی نمایش داده می‌شوند. سایر قابلیت‌ها تا زمان پیاده‌سازی واقعی پنهان هستند.',
            'Only observable features are shown. Unimplemented controls remain hidden.'),
          style: Theme.of(context).textTheme.bodySmall),
      ],
    );

    if (widget.embedded) return content;
    return Scaffold(
      appBar: AppBar(title: Text(tr('تنظیمات شبکه', 'Network settings'))),
      body: BrandBackground(
        brand: widget.brand,
        child: ListView(
          padding: const EdgeInsets.all(18),
          children: [content],
        ),
      ),
    );
  }
}
