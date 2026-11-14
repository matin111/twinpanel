import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

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
  bool _vmGuardBusy = false;
  bool _networkResetBusy = false;
  bool _guardRecoveryBusy = false;
  bool _guardTrialBusy = false;

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

  Future<void> _copyDiagnostics() async {
    final diagnosticText = <String>[
      'TwinConnect network diagnostics',
      'platform: ${NativeVpnBridge.platform.name}',
      'vpn_engine_ready: ${_capabilities.engineReady}',
      'full_tunnel_supported: ${_capabilities.fullTunnel}',
      'wfp_available: ${_guard['wfpAvailable'] == true}',
      'guard_service_installed: ${_guard['serviceInstalled'] == true}',
      'guard_armed_verified: $_guardActive',
      'dns_engine_support: ${_capabilities.dnsGuard}',
      'ipv6_engine_support: ${_capabilities.ipv6Guard}',
      'guard_reason: ${_guard['reason'] ?? 'UNKNOWN'}',
    ].join('\n');
    await Clipboard.setData(ClipboardData(text: diagnosticText));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(AppStrings.of(context).pick(
          'گزارش عیب‌یابی کپی شد', 'Diagnostic report copied')),
    ));
  }

  Future<void> _vmGuardAction(bool enable) async {
    if (_vmGuardBusy ||
        !Platform.isWindows ||
        Platform.environment['TWINCONNECT_DISPOSABLE_VM'] != '1') return;
    String alias = '';
    String endpoint = '';
    String executable = '';
    if (enable) {
      final aliasController = TextEditingController(text: 'TwinConnectSB');
      final endpointController = TextEditingController();
      final executableController = TextEditingController();
      try {
        final accepted = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('Experimental Windows VM guard'),
            content: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 430),
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                const Text('Disposable VM only. Verify external recovery '
                    'and never use on your everyday Windows installation.'),
                TextField(controller: aliasController,
                    decoration: const InputDecoration(labelText: 'Tunnel alias')),
                TextField(controller: endpointController,
                    decoration: const InputDecoration(labelText: 'Endpoint IPv4')),
                TextField(controller: executableController,
                    decoration: const InputDecoration(labelText: 'Transport executable path')),
              ]),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx, false),
                  child: const Text('Cancel')),
              FilledButton(onPressed: () => Navigator.pop(ctx, true),
                  child: const Text('Test only in disposable VM')),
            ],
          ),
        );
        if (accepted != true || !mounted) return;
        alias = aliasController.text;
        endpoint = endpointController.text;
        executable = executableController.text;
      } finally {
        // Defer controller disposal until the dialog transition has closed.
        await Future<void>.delayed(const Duration(milliseconds: 250));
        aliasController.dispose();
        endpointController.dispose();
        executableController.dispose();
      }
    }
    if (!mounted) return;
    setState(() => _vmGuardBusy = true);
    final result = await NativeVpnBridge.experimentalVmGlobalGuard(
      action: enable ? 'arm' : 'disarm',
      alias: alias,
      endpoint: endpoint,
      executable: executable,
    );
    await _check();
    if (!mounted) return;
    setState(() => _vmGuardBusy = false);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(result['success'] == true
          ? 'VM command acknowledged; leak tests still required'
          : 'VM guard rejected: ${result['reason']}'),
    ));
  }



  Future<void> _testSignedWindowsGuard() async {
    if (!Platform.isWindows || _guardTrialBusy ||
        _guard['serviceInstalled'] != true) return;
    final s = AppStrings.of(context);
    final tunnel = TextEditingController(text: 'TwinConnect');
    final endpoint = TextEditingController();
    final transport = TextEditingController();
    bool? accepted;
    try {
      accepted = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(s.pick('تست دو دقیقه‌ای Kill Switch', 'Two-minute Kill Switch test')),
          content: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text(s.pick(
                'فقط برای سرویس امضاشده و VPN متصل. قوانین محافظت پس از دو دقیقه خودکار پاک می‌شوند. قبل از اجرا مسیر بازیابی را آماده داشته باش.',
                'Signed guard and connected VPN only. WFP rules are automatically removed after two minutes. Keep offline recovery available.',
              )),
              TextField(controller: tunnel,
                decoration: const InputDecoration(labelText: 'Tunnel alias')),
              TextField(controller: endpoint,
                decoration: const InputDecoration(labelText: 'VPN endpoint IPv4')),
              TextField(controller: transport,
                decoration: const InputDecoration(labelText: 'VPN transport executable')),
            ]),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false),
              child: Text(s.pick('انصراف', 'Cancel'))),
            FilledButton(onPressed: () => Navigator.pop(ctx, true),
              child: Text(s.pick('شروع تست', 'Start test'))),
          ],
        ),
      );
      if (accepted != true || !mounted) return;
      setState(() => _guardTrialBusy = true);
      final script = File(File(Platform.resolvedExecutable).parent.path +
          r'\tools\windows_guard_control.ps1');
      if (!await script.exists()) {
        throw const FileSystemException('GUARD_CONTROL_SCRIPT_MISSING');
      }
      final result = await Process.run('powershell.exe', [
        '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', script.path, '-Action', 'Arm',
        '-TunnelAlias', tunnel.text.trim(),
        '-EndpointIpv4', endpoint.text.trim(),
        '-TransportExe', transport.text.trim(),
      ]).timeout(const Duration(seconds: 40));
      if (result.exitCode != 0 ||
          !result.stdout.toString().contains('GUARD_ARMED_TWO_MINUTE_TEST')) {
        throw StateError('GUARD_ARM_FAILED: ' + result.stderr.toString());
      }
      await _check();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(s.pick(
          'تست محدود فعال شد؛ قوانین تا دو دقیقه دیگر خودکار بازیابی می‌شوند.',
          'Time-limited test started. Owned WFP rules will be recovered automatically in two minutes.',
        )),
      ));
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(s.pick(
            'فعال‌سازی تأیید نشد؛ سرویس امضاشده، VPN متصل و دسترسی Administrator را بررسی کن.',
            'Guard activation was not verified. Check signed service, active VPN and Administrator access.',
          )),
        ));
      }
    } finally {
      if (mounted) setState(() => _guardTrialBusy = false);
      await Future<void>.delayed(const Duration(milliseconds: 250));
      tunnel.dispose();
      endpoint.dispose();
      transport.dispose();
    }
  }

  Future<void> _resetWindowsNetwork() async {
    if (!Platform.isWindows || _networkResetBusy) return;
    final s = AppStrings.of(context);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(s.pick('ریست تنظیمات اینترنت ویندوز',
            'Reset Windows network settings')),
        content: Text(s.pick(
          'اتصال VPN و اینترنت ممکن است قطع شود. کش DNS، Winsock و TCP/IP ریست می‌شوند و بعد از آن باید ویندوز را ریستارت کنی. اگر سرویس محافظت امضاشده نصب باشد، قوانین متعلق به TwinConnect هم بازیابی می‌شوند. قوانین فایروال دیگر برنامه‌ها دست‌نخورده می‌مانند. ادامه می‌دهی؟',
          'Internet and VPN may disconnect. This resets DNS cache, Winsock and TCP/IP. Restart Windows afterward. If the signed TwinConnect guard is installed, its own WFP rules are recovered first. Other apps\' firewall rules are not removed. Continue?',
        )),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false),
              child: Text(s.pick('انصراف', 'Cancel'))),
          FilledButton(onPressed: () => Navigator.pop(ctx, true),
              child: Text(s.pick('ریست شبکه', 'Reset network'))),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _networkResetBusy = true);
    String message;
    try {
      final script = File('${File(Platform.resolvedExecutable).parent.path}'
          '\\tools\\reset_windows_network.ps1');
      if (!await script.exists()) {
        throw const FileSystemException('NETWORK_RESET_TOOL_MISSING');
      }
      final result = await Process.run(
        'powershell.exe',
        ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
          '-File', script.path],
      ).timeout(const Duration(seconds: 90));
      if (result.exitCode != 0 ||
          !result.stdout.toString().contains('NETWORK_RESET_OK_RESTART_REQUIRED')) {
        throw StateError('NETWORK_RESET_FAILED: ${result.stderr}');
      }
      message = s.pick(
        'تنظیمات شبکه ریست شد؛ برای تکمیل، ویندوز را ریستارت کن.',
        'Network reset completed. Restart Windows to finish.',
      );
    } catch (error) {
      message = s.pick(
        'ریست شبکه انجام نشد. برنامه را با دسترسی Administrator اجرا کن. گزارش: C:\\ProgramData\\TwinConnect\\network-reset.log',
        'Network reset failed. Run the app as Administrator. Log: C:\\ProgramData\\TwinConnect\\network-reset.log',
      );
    }
    if (!mounted) return;
    setState(() => _networkResetBusy = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), duration: const Duration(seconds: 8)),
    );
  }


  Future<void> _recoverWindowsGuard() async {
    if (!Platform.isWindows || _guardRecoveryBusy) return;
    final s = AppStrings.of(context);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(s.pick('بازیابی اضطراری Kill Switch',
            'Emergency Kill Switch recovery')),
        content: Text(s.pick(
          'فقط قوانین محافظتی متعلق به TwinConnect حذف می‌شوند و ممکن است اینترنت مستقیم دوباره برقرار شود. این کار تنظیمات شبکه ویندوز را ریست نمی‌کند. ادامه می‌دهی؟',
          'This removes TwinConnect-owned protection rules only and may restore direct internet access. It does not reset Windows networking. Continue?',
        )),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false),
              child: Text(s.pick('انصراف', 'Cancel'))),
          FilledButton(onPressed: () => Navigator.pop(ctx, true),
              child: Text(s.pick('بازیابی', 'Recover'))),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _guardRecoveryBusy = true);
    String message;
    try {
      final script = File('${File(Platform.resolvedExecutable).parent.path}'
          '\\tools\\reset_windows_network.ps1');
      if (!await script.exists()) {
        throw const FileSystemException('GUARD_RECOVERY_TOOL_MISSING');
      }
      final result = await Process.run('powershell.exe',
        ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
          '-File', script.path, '-GuardOnly'],
      ).timeout(const Duration(seconds: 60));
      if (result.exitCode != 0 ||
          !result.stdout.toString().contains('TWINCONNECT_GUARD_RECOVERY_OK')) {
        throw StateError('GUARD_RECOVERY_FAILED: ${result.stderr}');
      }
      message = s.pick('بازیابی محافظ TwinConnect انجام شد.',
          'TwinConnect guard recovery completed.');
    } catch (_) {
      message = s.pick(
        'بازیابی تأیید نشد. با Administrator اجرا کن؛ گزارش: C:\\ProgramData\\TwinConnect\\network-reset.log',
        'Recovery was not verified. Run as Administrator; log: C:\\ProgramData\\TwinConnect\\network-reset.log',
      );
    }
    await _check();
    if (!mounted) return;
    setState(() => _guardRecoveryBusy = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), duration: const Duration(seconds: 8)),
    );
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

        if (Platform.isWindows && _guard['serviceInstalled'] == true) ...[
          const SizedBox(height: 8),
          _glass(Row(children: [
            const Icon(Icons.science_outlined, size: 22),
            const SizedBox(width: 12),
            Expanded(child: Text(tr(
              'تست کنترل‌شده Kill Switch (۲ دقیقه)',
              'Kill Switch controlled test (2 min)',
            ))),
            TextButton(
              key: const Key('vpnSignedGuardTimedTest'),
              onPressed: _guardTrialBusy ? null : _testSignedWindowsGuard,
              child: _guardTrialBusy
                  ? const SizedBox(width: 18, height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : Text(tr('تست', 'Test')),
            ),
          ]), key: const Key('vpnSignedGuardTimedTestCard')),
        ],
        // Recovery must remain accessible even if the guard service crashes,
        // is unregistered, or a native status probe fails closed.
        if (Platform.isWindows) ...[
          const SizedBox(height: 8),
          _glass(Row(children: [
            const Icon(Icons.shield_outlined, size: 22),
            const SizedBox(width: 12),
            Expanded(child: Text(
              tr('بازیابی اضطراری Kill Switch',
                 'Emergency Kill Switch recovery'),
              style: const TextStyle(fontWeight: FontWeight.w600),
            )),
            TextButton(
              key: const Key('vpnGuardEmergencyRecovery'),
              onPressed: _guardRecoveryBusy ? null : _recoverWindowsGuard,
              child: _guardRecoveryBusy
                  ? const SizedBox(width: 18, height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : Text(tr('بازیابی', 'Recover')),
            ),
          ]), key: const Key('vpnGuardEmergencyRecoveryCard')),
        ],
        if (Platform.isWindows) ...[
          const SizedBox(height: 8),
          _glass(Row(children: [
            const Icon(Icons.settings_backup_restore_rounded, size: 22),
            const SizedBox(width: 12),
            Expanded(child: Text(
              tr('ریست تنظیمات اینترنت ویندوز', 'Reset Windows network settings'),
              style: const TextStyle(fontWeight: FontWeight.w600),
            )),
            _help('Windows network reset', tr(
              'با تأیید کاربر، DNS و Winsock و TCP/IP ریست می‌شود. برای تکمیل به راه‌اندازی مجدد ویندوز نیاز است. در صورت وجود سرویس امضاشده TwinConnect، قوانین محافظتی متعلق به آن نیز بازیابی و بررسی می‌شوند.',
              'With confirmation, clears DNS cache and resets Winsock/TCP-IP. Requires a Windows restart. A trusted installed TwinConnect guard is recovered and its owned WFP rules verified first.',
            )),
            TextButton(
              key: const Key('vpnWindowsNetworkReset'),
              onPressed: _networkResetBusy ? null : _resetWindowsNetwork,
              child: _networkResetBusy
                  ? const SizedBox(width: 18, height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : Text(tr('ریست', 'Reset')),
            ),
          ]), key: const Key('vpnWindowsNetworkResetCard')),
        ],
        if (Platform.isWindows &&
            Platform.environment['TWINCONNECT_DISPOSABLE_VM'] == '1')
          _glass(Row(children: [
            const Icon(Icons.science_outlined),
            const SizedBox(width: 8),
            const Expanded(child: Text('Experimental VM guard — not production')),
            TextButton(
              key: const Key('vpnVmArm'),
              onPressed: _vmGuardBusy ? null : () => _vmGuardAction(true),
              child: const Text('Arm test'),
            ),
            TextButton(
              key: const Key('vpnVmDisarm'),
              onPressed: _vmGuardBusy ? null : () => _vmGuardAction(false),
              child: const Text('Disarm'),
            ),
          ]), key: const Key('vpnVmGuardControl')),
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
        const SizedBox(height: 11),
        _glass(ExpansionTile(
          key: const Key('vpnDiagnosticsDisclosure'),
          initiallyExpanded: false,
          tilePadding: const EdgeInsets.symmetric(horizontal: 3),
          childrenPadding: const EdgeInsets.symmetric(vertical: 6),
          title: Text(tr('عیب‌یابی اتصال', 'Connection diagnostics'),
              style: const TextStyle(fontWeight: FontWeight.w700)),
          leading: const Icon(Icons.monitor_heart_outlined),
          children: [
            Align(
              alignment: AlignmentDirectional.centerEnd,
              child: TextButton.icon(
                key: const Key('vpnCopyDiagnostics'),
                onPressed: _copyDiagnostics,
                icon: const Icon(Icons.copy_all_rounded, size: 17),
                label: Text(tr('کپی گزارش', 'Copy diagnostics')),
              ),
            ),
            _statusItem(
              key: const Key('vpnNativeEngineStatus'),
              title: tr('موتور VPN', 'VPN engine'),
              value: _capabilities.engineReady
                  ? tr('آماده', 'Ready')
                  : tr('در دسترس نیست', 'Unavailable'),
              ready: _capabilities.engineReady,
              icon: Icons.power_rounded,
              help: tr('این فقط وضعیت موتور اتصال است، نه تأیید اتصال به VPN.',
                'Engine readiness does not prove an active VPN connection.'),
            ),
            const SizedBox(height: 6),
            _statusItem(
              key: const Key('vpnWfpStatus'),
              title: tr('Windows Filtering Platform', 'Windows Filtering Platform'),
              value: globalReady ? tr('شناسایی شد', 'Detected')
                  : tr('در دسترس نیست', 'Unavailable'),
              ready: globalReady,
              icon: Icons.security_rounded,
              help: tr('فقط امکان دسترسی به فیلتر ویندوز را بررسی می‌کند؛ به معنای فعال بودن Kill Switch نیست.',
                'WFP availability is not proof that system traffic is blocked.'),
            ),
            const SizedBox(height: 6),
            _statusItem(
              key: const Key('vpnDnsGuard'),
              title: 'DNS',
              value: _capabilities.dnsGuard ? tr('پشتیبانی موتور', 'Engine supported')
                  : tr('تأیید نشده', 'Unverified'),
              ready: _capabilities.dnsGuard,
              icon: Icons.dns_rounded,
              help: tr('وضعیت قابلیت موتور است، نه نتیجه تست نشت DNS.',
                'Engine capability is not a DNS leak test.'),
            ),
            const SizedBox(height: 6),
            _statusItem(
              key: const Key('vpnIpv6Guard'),
              title: 'IPv6',
              value: _capabilities.ipv6Guard ? tr('پشتیبانی موتور', 'Engine supported')
                  : tr('تأیید نشده', 'Unverified'),
              ready: _capabilities.ipv6Guard,
              icon: Icons.lan_rounded,
              help: tr('وضعیت قابلیت موتور است، نه نتیجه تست نشت IPv6.',
                'Engine capability is not an IPv6 leak test.'),
            ),
          ],
        ), key: const Key('vpnDiagnosticsCard')),
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
