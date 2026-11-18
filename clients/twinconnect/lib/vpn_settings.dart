import 'dart:io';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app_strings.dart';
import 'brand_theme.dart';
import 'interactive_glass_card.dart';
import 'native_vpn_bridge.dart';
import 'vpn_policy.dart';
import 'vpn_policy_store.dart';
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
  Map<String, dynamic> _androidGuardDetails = const {};
  Map<String, dynamic> _androidNetworkDetails = const {};
  final VpnPolicyStore _policyStore = const VpnPolicyStore();
  VpnPolicy _routingPolicy = const VpnPolicy();
  bool _routingSaving = false;
  bool _routingLoaded = false;
  bool _checking = false;
  bool _vmGuardBusy = false;
  bool _androidKillRequested = false;
  bool _androidKillBusy = false;
  bool _androidVpnConflict = false;
  bool _androidOsLockdown = false;
  bool _androidLockdownVerifiable = false;
  bool _androidLegacyGuardUp = false;
  bool _androidSharedAwgReady = false;
  Timer? _androidGuardPoll;

  @override
  void initState() {
    super.initState();
    _check();
    _loadRoutingPolicy();
    _refreshAndroidGuard();
    _refreshAndroidNetworkDiagnostics();
    if (Platform.isAndroid) {
      _androidGuardPoll = Timer.periodic(const Duration(seconds: 3), (_) {
        if (!_androidKillBusy) {
          _refreshAndroidGuard();
          _refreshAndroidNetworkDiagnostics();
        }
      });
    }
  }

  @override
  void dispose() {
    _androidGuardPoll?.cancel();
    super.dispose();
  }

  Future<void> _loadRoutingPolicy() async {
    final policy = await _policyStore.load(widget.tenant, widget.account);
    if (mounted) setState(() {
      _routingPolicy = policy;
      _routingLoaded = true;
    });
  }

  Future<void> _setAndroidKill(bool requested) async {
    if (_androidKillBusy || !_routingLoaded) return;
    final previous = _routingPolicy;
    if (requested && previous.routingMode != VpnRoutingMode.fullTunnel) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(AppStrings.of(context).pick(
          'برای محافظت کامل ابتدا حالت «تمام دستگاه» را انتخاب کنید.',
          'Choose Entire device before enabling Kill Switch.')),
      ));
      return;
    }
    setState(() => _androidKillBusy = true);
    try {
      const channel = MethodChannel('com.twinpanel.twinconnect/vpn');
      if (requested) {
        await NativeVpnBridge.configureAndroidAppRouting(previous);
        await channel.invokeMethod<dynamic>('startDisconnectedTrafficGuard');
      } else {
        await channel.invokeMethod<dynamic>('stopDisconnectedTrafficGuard');
      }
      for (var attempt = 0; attempt < 12; attempt++) {
        await Future<void>.delayed(const Duration(milliseconds: 250));
        await _refreshAndroidGuard();
        if (_androidKillRequested == requested) break;
      }
      if (_androidKillRequested != requested) {
        throw StateError('KILL_SWITCH_NOT_VERIFIED');
      }
      final updated = previous.copyWith(killSwitchRequested: requested);
      if (!await _policyStore.save(widget.tenant, widget.account, updated)) {
        throw StateError('KILL_SWITCH_PREFERENCE_NOT_SAVED');
      }
      if (mounted) setState(() => _routingPolicy = updated);
    } on PlatformException catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('Kill Switch: ' + error.code),
      ));
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Kill Switch: state or policy not confirmed'),
      ));
    } finally {
      if (mounted) setState(() => _androidKillBusy = false);
    }
  }

  Future<void> _selectRouting(VpnRoutingMode mode) async {
    if (!Platform.isAndroid || _routingSaving || !_routingLoaded) return;
    if (mode != VpnRoutingMode.fullTunnel && _androidKillRequested) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(AppStrings.of(context).pick(
          'برای تفکیک برنامه‌ها ابتدا Kill Switch را خاموش کنید.',
          'Turn off Kill Switch before enabling split tunneling.')),
      ));
      return;
    }
    List<String> selected = const [];
    if (mode != VpnRoutingMode.fullTunnel) {
      try {
        const native = MethodChannel('com.twinpanel.twinconnect/vpn');
        final result = await native.invokeMapMethod<String, dynamic>('listLaunchableApps');
        final raw = result?['apps'];
        if (raw is! List) throw StateError('APP_LIST_UNAVAILABLE');
        final apps = <(String, String)>[];
        for (final row in raw) {
          if (row is! Map) continue;
          final id = row['packageName'];
          final label = row['label'];
          if (id is String && label is String && id.isNotEmpty) {
            apps.add((id, label));
          }
        }
        if (!mounted) return;
        if (apps.isEmpty) throw StateError('APP_LIST_EMPTY');
        final chosen = _routingPolicy.routingMode == mode
            ? _routingPolicy.appIds.toSet() : <String>{};
        var search = '';
        final picked = await showDialog<Set<String>>(
          context: context,
          builder: (ctx) => StatefulBuilder(
            builder: (ctx, update) {
              final filtered = apps.where((item) =>
                  item.$2.toLowerCase().contains(search.toLowerCase()) ||
                  item.$1.toLowerCase().contains(search.toLowerCase())
              ).toList(growable: false);
              return AlertDialog(
                title: Text(AppStrings.of(ctx).pick(
                    'انتخاب برنامه‌ها', 'Select apps')),
                content: SizedBox(
                  width: 430,
                  height: 400,
                  child: Column(children: [
                    TextField(
                      onChanged: (value) => update(() => search = value),
                      decoration: InputDecoration(
                        prefixIcon: const Icon(Icons.search),
                        hintText: AppStrings.of(ctx).pick('جستجوی برنامه', 'Search apps'),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Expanded(child: ListView.builder(
                      itemCount: filtered.length,
                      itemBuilder: (ctx, index) {
                        final row = filtered[index];
                        return CheckboxListTile(
                          dense: true,
                          title: Text(row.$2, maxLines: 1,
                              overflow: TextOverflow.ellipsis),
                          subtitle: Text(row.$1, maxLines: 1,
                              overflow: TextOverflow.ellipsis),
                          value: chosen.contains(row.$1),
                          onChanged: (checked) => update(() {
                            if (checked == true) {
                              if (chosen.length < 100) chosen.add(row.$1);
                            } else {
                              chosen.remove(row.$1);
                            }
                          }),
                        );
                      },
                    )),
                  ]),
                ),
                actions: [
                  TextButton(onPressed: () => Navigator.pop(ctx),
                    child: Text(AppStrings.of(ctx).pick('انصراف', 'Cancel'))),
                  FilledButton(
                    onPressed: chosen.isEmpty ? null :
                        () => Navigator.pop(ctx, chosen),
                    child: Text(AppStrings.of(ctx).pick('ذخیره', 'Save')),
                  ),
                ],
              );
            },
          ),
        );
        if (picked == null || picked.isEmpty || !mounted) return;
        selected = picked.toList()..sort();
      } catch (_) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Installed-app picker unavailable'),
        ));
        return;
      }
    }
    final updated = _routingPolicy.copyWith(
      routingMode: mode,
      appIds: selected,
    );
    if (updated.draftProblems(VpnPlatform.android).isNotEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('App routing policy is invalid'),
      ));
      return;
    }
    setState(() => _routingSaving = true);
    try {
      if (!await _policyStore.save(widget.tenant, widget.account, updated)) {
        throw StateError('APP_ROUTING_SAVE_FAILED');
      }
      if (!mounted) return;
      setState(() => _routingPolicy = updated);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(AppStrings.of(context).pick(
          'ذخیره شد؛ تنظیمات پس از اتصال مجدد VPN اعمال می‌شود.',
          'Saved. Reconnect VPN to apply app routing.')),
      ));
    } catch (_) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Unable to save app routing'),
      ));
    } finally {
      if (mounted) setState(() => _routingSaving = false);
    }
  }

  Future<void> _refreshAndroidGuard() async {
    if (!Platform.isAndroid) return;
    try {
      final result = await const MethodChannel('com.twinpanel.twinconnect/vpn')
          .invokeMapMethod<String, dynamic>('getDisconnectedTrafficGuardStatus');
      if (mounted) setState(() {
        _androidGuardDetails = result ?? const {};
        _androidKillRequested = result?['sharedGuardEnabled'] == true;
        _androidLegacyGuardUp = result?['legacyGuardActive'] == true;
        _androidSharedAwgReady =
            (result?['sharedTunSupportedProtocols'] as List?)?.contains('amneziawg') == true;
        _androidVpnConflict = result?['otherVpnActive'] == true;
        _androidOsLockdown = result?['osLockdown'] == true;
        _androidLockdownVerifiable = result?['lockdownVerificationAvailable'] == true;
      });
    } on PlatformException {
      if (mounted) setState(() {
        _androidKillRequested = false;
        _androidLegacyGuardUp = false;
        _androidSharedAwgReady = false;
        _androidVpnConflict = false;
        _androidOsLockdown = false;
        _androidLockdownVerifiable = false;
      });
    }
  }

  Future<void> _refreshAndroidNetworkDiagnostics() async {
    if (!Platform.isAndroid) return;
    try {
      final status = await const MethodChannel('com.twinpanel.twinconnect/vpn')
          .invokeMapMethod<String, dynamic>('getAndroidVpnNetworkDiagnostics');
      if (mounted && status?['contractVersion'] == 1) {
        setState(() => _androidNetworkDetails = status!);
      }
    } on PlatformException {
      if (mounted) setState(() => _androidNetworkDetails = const {});
    }
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
      'platform: ' + NativeVpnBridge.platform.name,
    ];
    if (Platform.isAndroid) {
      await _refreshAndroidGuard();
      await _refreshAndroidNetworkDiagnostics();
      var registration = 'UNKNOWN';
      try {
        final raw = await const MethodChannel('com.twinpanel.twinconnect/vpn')
            .invokeMapMethod<String, dynamic>('getVpnRegistrationStatus');
        registration = raw?['discoverable'] == true ? 'YES' : 'NO';
      } catch (_) {}
      diagnosticText.addAll([
        'shared_vpn_registration: ' + registration,
        'vpn_transport_active: ' +
            (_androidNetworkDetails['vpnTransportActive'] == true).toString(),
        'shared_tun_owner: ' +
            (_androidGuardDetails['sharedTunOwner'] == true).toString(),
        'shared_tun_protocol: ' +
            (_androidGuardDetails['sharedTunProtocol']?.toString() ?? 'NONE'),
        'selected_app_routing: ' + _routingPolicy.routingMode.name,
        'selected_app_count: ' + _routingPolicy.appIds.length.toString(),
        'native_app_routing: ' +
            (_androidGuardDetails['appRoutingMode']?.toString() ?? 'UNKNOWN'),
        'kill_switch_shared_guard: ' + _androidKillRequested.toString(),
        'android_os_lockdown: ' + _androidOsLockdown.toString(),
        'vpn_default_route_ipv4: ' +
            (_androidNetworkDetails['vpnDefaultIpv4'] == true).toString(),
        'vpn_default_route_ipv6: ' +
            (_androidNetworkDetails['vpnDefaultIpv6'] == true).toString(),
        'vpn_dns_server_count: ' +
            (_androidNetworkDetails['vpnDnsCount']?.toString() ?? 'UNKNOWN'),
        'network_validated: ' +
            (_androidNetworkDetails['networkValidated'] == true).toString(),
        'dns_leak_test_performed: false',
      ]);
    } else {
      diagnosticText.addAll([
        'vpn_engine_ready: ' + _capabilities.engineReady.toString(),
        'full_tunnel_supported: ' + _capabilities.fullTunnel.toString(),
        'wfp_available: ' + (_guard['wfpAvailable'] == true).toString(),
        'guard_service_installed: ' + (_guard['serviceInstalled'] == true).toString(),
        'guard_armed_verified: ' + _guardActive.toString(),
        'dns_engine_support: ' + _capabilities.dnsGuard.toString(),
        'ipv6_engine_support: ' + _capabilities.ipv6Guard.toString(),
        'guard_reason: ' + (_guard['reason']?.toString() ?? 'UNKNOWN'),
      ]);
    }
    await Clipboard.setData(ClipboardData(text: diagnosticText.join('\n')));
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
    VoidCallback? onTap,
  }) => InkWell(
    key: key,
    borderRadius: BorderRadius.circular(14),
    onTap: enabled ? onTap : null,
    child: Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
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
      ]),
    ),
  );

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
        if (Platform.isAndroid)
          _glass(Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(
                  _androidKillRequested ? Icons.verified_user_rounded
                      : Icons.shield_outlined,
                  color: _androidKillRequested ? Colors.greenAccent : null,
                ),
                title: const Text('Kill Switch'),
                subtitle: Text(tr(
                  _androidKillRequested
                      ? 'فعال: تونل مشترک ترافیک را هنگام قطع اتصال مسدود می‌کند. برای خاموشی کامل برنامه، قفل شبکه اندروید لازم است.'
                      : _androidVpnConflict && !_androidLockdownVerifiable
                          ? 'موتور VPN مستقل دیگری فعال است؛ محافظ مشترک در دسترس نیست.'
                          : _androidSharedAwgReady
                              ? 'محافظ مشترک WireGuard، Cisco، AmneziaWG، OpenVPN، Xray و پروتکل‌های sing-box را فعال کنید.'
                              : 'محافظ مشترک WireGuard، Cisco، OpenVPN، Xray و پروتکل‌های sing-box را فعال کنید.',
                  _androidKillRequested
                      ? 'Enabled: shared TUN blocks traffic on disconnect. Android lockdown is still needed for app termination.'
                      : _androidVpnConflict && !_androidLockdownVerifiable
                          ? 'An independent VPN engine is active; shared guard is unavailable.'
                          : _androidSharedAwgReady
                              ? 'One-switch shared TUN guard for WireGuard, Cisco, AmneziaWG, OpenVPN, Xray and sing-box protocols.'
                              : 'One-switch shared TUN guard for WireGuard, Cisco, OpenVPN, Xray and sing-box protocols.',
                )),
                trailing: Switch.adaptive(
                  key: const Key('androidSharedKillSwitch'),
                  value: _androidKillRequested,
                  onChanged: _androidKillBusy || !_routingLoaded ? null : _setAndroidKill,
                ),
              ),
              Text(
                _androidOsLockdown
                    ? tr('قفل شبکه اندروید نیز فعال است.', 'Android OS lockdown is also verified.')
                    : tr('در صورت بسته‌شدن اجباری برنامه یا راه‌اندازی دوباره گوشی، محافظت داخلی تضمین‌شده نیست.',
                        'The in-app guard cannot guarantee protection after force-stop, process death, or reboot.'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
              TextButton.icon(
                onPressed: () async {
                  try {
                    final result = await const MethodChannel(
                      'com.twinpanel.twinconnect/vpn',
                    ).invokeMapMethod<String, dynamic>('getVpnRegistrationStatus');
                    if (!mounted) return;
                    final discovered = result?['discoverable'] == true;
                    final services = result?['registeredVpnServices'];
                    final count = services is List ? services.length : 0;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(discovered
                          ? tr('سرویس VPN ثبت شده است (تعداد: $count).',
                              'VPN service registered ($count found).')
                          : tr('سرویس VPN در نسخه نصب‌شده شناسایی نشد.',
                              'No discoverable VPN service in installed app.')),
                    ));
                  } on PlatformException catch (error) {
                    if (!mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text('VPN registration: ${error.code}'),
                    ));
                  }
                },
                icon: const Icon(Icons.fact_check_outlined),
                label: Text(tr('بررسی ثبت VPN در اندروید',
                    'Check Android VPN registration')),
              ),
              if (_androidLegacyGuardUp)
                TextButton.icon(
                  onPressed: _androidKillBusy ? null : () => _setAndroidKill(false),
                  icon: const Icon(Icons.stop_circle_outlined),
                  label: Text(tr('توقف محافظ قدیمی', 'Stop legacy traffic guard')),
                ),
              TextButton.icon(
                onPressed: _checking ? null : () async { await _check(); await _refreshAndroidGuard(); },
                icon: const Icon(Icons.refresh_rounded),
                label: Text(tr('بررسی مجدد وضعیت محافظت',
                    'Refresh protection status')),
              ),
            ],
          )),

        if (Platform.isWindows) ...[
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
              Text(tr('پروکسی سراسری نیازمند مدیریت دستگاه است',
                      'System-wide proxy requires device management'),
                  style: Theme.of(context).textTheme.bodySmall),
            ],
          )),
          _help('Proxy', tr(
            'برنامه عادی اندروید نمی‌تواند پروکسی سراسری سایر برنامه‌ها را بدون دسترسی مالک دستگاه تغییر دهد. این بخش عمداً غیرفعال است تا تنظیمی ظاهری به‌جای اتصال واقعی نشان داده نشود.',
            'A normal Android app cannot set the device-wide proxy for other apps without device-owner access. This mode remains disabled rather than pretending to switch routing.',
          )),
          const Icon(Icons.lock_outline_rounded),
        ]), key: const Key('vpnProxyModeUnavailable')),
        _section(tr('تفکیک برنامه‌ها', 'Split tunneling')),
        _glass(Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _routingOption(
              label: tr('تمام دستگاه', 'Entire device'),
              selected: !Platform.isAndroid ||
                  _routingPolicy.routingMode == VpnRoutingMode.fullTunnel,
              enabled: true,
              onTap: Platform.isAndroid ? () => _selectRouting(VpnRoutingMode.fullTunnel) : null,
              help: tr('در حالت تمام دستگاه، ترافیک برنامه‌های مجاز از VPN عبور می‌کند؛ البته با توجه به محدودیت پروتکل و تنظیمات شبکه.',
                  'Currently routes device traffic via VPN, subject to the protocol and OS routing capabilities.'),
              key: const Key('vpnRoutingFullTunnel'),
            ),
            Divider(height: 12, color: Theme.of(context).dividerColor),
            _routingOption(
              label: tr('فقط برنامه‌های انتخابی', 'Only selected apps'),
              selected: Platform.isAndroid &&
                  _routingPolicy.routingMode == VpnRoutingMode.onlySelectedApps,
              enabled: Platform.isAndroid && _routingLoaded && !_androidKillRequested && !_routingSaving,
              onTap: () => _selectRouting(VpnRoutingMode.onlySelectedApps),
              help: tr('برنامه‌های انتخابی از VPN استفاده می‌کنند و سایر برنامه‌ها مستقیم به اینترنت متصل می‌شوند. Kill Switch باید خاموش باشد.',
                  'Selected apps use the VPN; other apps connect directly. Kill Switch must be off.'),
              key: const Key('vpnRoutingIncludeApps'),
            ),
            Divider(height: 12, color: Theme.of(context).dividerColor),
            _routingOption(
              label: tr('همه به‌جز برنامه‌های انتخابی', 'Exclude selected apps'),
              selected: Platform.isAndroid &&
                  _routingPolicy.routingMode == VpnRoutingMode.excludeSelectedApps,
              enabled: Platform.isAndroid && _routingLoaded && !_androidKillRequested && !_routingSaving,
              onTap: () => _selectRouting(VpnRoutingMode.excludeSelectedApps),
              help: tr('برنامه‌های انتخابی از VPN استثنا می‌شوند و مستقیم به اینترنت می‌روند. Kill Switch باید خاموش باشد.',
                  'Selected apps bypass the VPN and connect directly. Kill Switch must be off.'),
              key: const Key('vpnRoutingExcludeApps'),
            ),
          ],
        ), key: const Key('vpnSplitTunnelCard')),
        if (Platform.isAndroid && _routingPolicy.routingMode != VpnRoutingMode.fullTunnel)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(tr(
              'انتخاب‌شده: ${_routingPolicy.appIds.length} برنامه • پس از اتصال مجدد اعمال می‌شود',
              'Selected: ${_routingPolicy.appIds.length} apps • applies after reconnect',
            ), style: Theme.of(context).textTheme.bodySmall),
          ),
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
            if (Platform.isAndroid) ...[
              _statusItem(
                key: const Key('vpnAndroidTransportStatus'),
                title: tr('تونل فعال اندروید', 'Android VPN transport'),
                value: _androidNetworkDetails['vpnTransportActive'] == true
                    ? tr('رابط VPN فعال', 'VPN interface active')
                    : tr('تونل فعالی شناسایی نشد', 'No active VPN interface'),
                ready: _androidNetworkDetails['vpnTransportActive'] == true,
                icon: Icons.route_rounded,
                help: tr('وجود رابط VPN به تنهایی به معنای اتصال موفق به سرور نیست.',
                    'A VPN interface is not proof of a working encrypted server session.'),
              ),
              const SizedBox(height: 6),
              _statusItem(
                key: const Key('vpnAndroidGuardStatus'),
                title: 'Kill Switch',
                value: _androidOsLockdown
                    ? tr('قفل شبکه سیستم فعال', 'Android OS lockdown verified')
                    : _androidKillRequested
                        ? tr('مسدودسازی درون برنامه فعال', 'In-app blocking active')
                        : tr('خاموش', 'Disabled'),
                ready: _androidKillRequested || _androidOsLockdown,
                icon: Icons.shield_outlined,
                help: tr('این بخش وضعیت محافظت را نشان می‌دهد؛ برای تست نشت واقعی باید تست جداگانه انجام شود.',
                    'This is protection state, not a network leak test.'),
              ),
              const SizedBox(height: 6),
              _statusItem(
                key: const Key('vpnAndroidRoutingStatus'),
                title: tr('مسیر برنامه‌ها', 'App routing'),
                value: _androidGuardDetails['appRoutingMode']?.toString() ??
                    tr('در انتظار اتصال', 'Pending next connection'),
                ready: _androidGuardDetails['appRoutingMode'] ==
                    _routingPolicy.routingMode.name,
                icon: Icons.apps_rounded,
                help: tr('فیلتر برنامه‌ها هنگام اتصال مجدد روی سرویس VPN اعمال می‌شود.',
                    'Per-app filters are applied when the VPN tunnel is re-established.'),
              ),
              const SizedBox(height: 6),
            ] else ...[
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
            ],
            _statusItem(
              key: const Key('vpnDnsGuard'),
              title: 'DNS',
              value: Platform.isAndroid
                  ? (_androidNetworkDetails['vpnDnsCount'] is int &&
                      (_androidNetworkDetails['vpnDnsCount'] as int) > 0
                      ? tr('DNS روی رابط VPN ثبت شد', 'VPN DNS configured')
                      : tr('ثبت DNS تأیید نشد', 'VPN DNS unverified'))
                  : (_capabilities.dnsGuard ? tr('پشتیبانی موتور', 'Engine supported')
                      : tr('تأیید نشده', 'Unverified')),
              ready: Platform.isAndroid
                  ? (_androidNetworkDetails['vpnDnsCount'] is int &&
                      (_androidNetworkDetails['vpnDnsCount'] as int) > 0)
                  : _capabilities.dnsGuard,
              icon: Icons.dns_rounded,
              help: tr('وضعیت قابلیت موتور است، نه نتیجه تست نشت DNS.',
                'Engine capability is not a DNS leak test.'),
            ),
            const SizedBox(height: 6),
            _statusItem(
              key: const Key('vpnIpv6Guard'),
              title: 'IPv6',
              value: Platform.isAndroid
                  ? (_androidNetworkDetails['vpnDefaultIpv6'] == true
                      ? tr('مسیر IPv6 داخل VPN', 'IPv6 VPN route present')
                      : tr('مسیر IPv6 تأیید نشد', 'IPv6 VPN route unverified'))
                  : (_capabilities.ipv6Guard ? tr('پشتیبانی موتور', 'Engine supported')
                      : tr('تأیید نشده', 'Unverified')),
              ready: Platform.isAndroid
                  ? _androidNetworkDetails['vpnDefaultIpv6'] == true
                  : _capabilities.ipv6Guard,
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
