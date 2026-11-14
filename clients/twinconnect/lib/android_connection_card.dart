import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'android_connection_strings.dart';
import 'android_tunnel.dart';
import 'app_strings.dart';
import 'native_vpn_bridge.dart';
import 'protocols.dart';
import 'tenant_api.dart';
import 'tenant_models.dart';
import 'server_inventory.dart';
import 'vpn_policy_store.dart';

/// A real WireGuard-native Android action, never a fake Cisco proxy.
///
/// The connection is labeled "interface up, handshake unverified" until
/// native handshake + leak checks exist. The widget NEVER persists keys.
class AndroidConnectionCard extends StatefulWidget {
  const AndroidConnectionCard({
    required this.panel,
    required this.username,
    required this.sessionToken,
    required this.catalog,
    required this.native,
    this.selectedNodeId,
    this.selectedProtocolCode,
    this.servers,
    super.key,
  });

  final PanelDirectoryEntry panel;
  final String username;
  final String sessionToken;
  final PanelProtocolCatalog catalog;
  final NativeProtocolReadiness native;
  // Exact panel node ID selected on the shared Servers screen.
  final String? selectedNodeId;
  /// The server screen owns protocol selection, not the connect screen.
  final String? selectedProtocolCode;
  final AppServerInventory? servers;

  @override
  State<AndroidConnectionCard> createState() => _AndroidConnectionCardState();
}

class _AndroidConnectionCardState extends State<AndroidConnectionCard> {
  final _controller = const AndroidTunnelController();
  final _store = const VpnPolicyStore();

  bool _busy = false;
  bool _up = false;
  String? _errorCode;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    if (!Platform.isAndroid) return;
    try {
      final status = await _controller.status();
      if (!mounted) return;
      setState(() => _up = status['state'] == 'interface_up');
    } catch (_) {
      if (mounted) setState(() => _up = false);
    }
  }

  String _nativeError(Object error) {
    if (error is PlatformException) return error.code;
    if (error is TenantApiException) return error.message;
    if (error is StateError) {
      final message = error.toString();
      const expected = [
        'AUTO_RECONNECT_UNAVAILABLE',
        'AUTO_CONNECT_UNAVAILABLE',
        'KILL_SWITCH_NOT_ENFORCED',
        'INCLUDE_APPS_UNSUPPORTED',
        'EXCLUDE_APPS_UNSUPPORTED',
        'DNS_PROTECTION_UNAVAILABLE',
        'IPV6_PROTECTION_UNAVAILABLE',
        'ENGINE_NOT_READY',
        'PROTOCOL_ENGINE_NOT_READY',
      ];
      for (final code in expected) {
        if (message.contains(code)) return code;
      }
    }
    return 'NATIVE_VPN_START_FAILED';
  }

  /// Automatic connection uses the panel's account-authorized node list.
  /// An explicit Servers selection wins; never prompt for raw node codes.
  WireGuardNode? _autoNode(
    ClientProtocolProfiles profiles,
    String? selectedNodeId,
  ) {
    final inventory = widget.servers?.servers ?? const <AppServer>[];
    final candidates = <(String, WireGuardNode, AppServer?)>[];
    for (final item in profiles.items) {
      final id = item['node_id']?.toString();
      final raw = item['config'];
      if (id == null || raw is! String || raw.trim().isEmpty) continue;
      if (selectedNodeId != null && id != selectedNodeId) continue;
      final matching = inventory.where((server) => server.id == id).firstOrNull;
      if (inventory.isNotEmpty &&
          (matching == null || !matching.nodeOnline)) continue;
      final name = matching?.name ??
          (item['node'] is String ? item['node'] as String : id);
      candidates.add((id, WireGuardNode(name: name, config: raw), matching));
    }
    if (candidates.isEmpty) return null;
    candidates.sort((a, b) {
      final aLatency = a.$3?.latencyMs ?? 60001;
      final bLatency = b.$3?.latencyMs ?? 60001;
      final delta = aLatency.compareTo(bLatency);
      return delta != 0 ? delta : a.$1.compareTo(b.$1);
    });
    return candidates.first.$2;
  }

  Future<void> _connect() async {
    if (widget.selectedProtocolCode != 'wireguard' &&
        widget.selectedProtocolCode != null) return;
    if (_busy || _up || !Platform.isAndroid ||
        !widget.native.supports('wireguard')) {
      return;
    }
    setState(() {
      _busy = true;
      _errorCode = null;
    });
    try {
      final policy = await _store.loadFailClosed(
        widget.panel.namespace, widget.username,
      );
      final capabilities = await NativeVpnBridge.probe();
      NativeVpnBridge.requireProtocolSafeToConnect(
        policy,
        capabilities,
        VpnProtocols.byCode('wireguard')!,
        widget.native,
      );
      // Fetch secrets only AFTER the native engine/policy guard passes.
      final profiles = await TenantApi.fromBuildConfig().loadSessionNativeProfiles(
        panel: widget.panel,
        sessionToken: widget.sessionToken,
        protocol: VpnProtocols.byCode('wireguard')!,
        native: widget.native,
      );
      final selectedNodeId = widget.selectedNodeId;
      final selected = _autoNode(profiles, selectedNodeId);
      if (selected == null) {
        if (mounted) setState(() => _errorCode = selectedNodeId == null
            ? 'NO_ONLINE_WIREGUARD_NODE'
            : 'SELECTED_WIREGUARD_NODE_UNAVAILABLE');
        return;
      }
      if (!mounted) return;
      final response = await _controller.connectWireGuard(
        node: selected,
        policy: policy,
        capabilities: capabilities,
        nativeProtocols: widget.native,
      );
      if (!mounted) return;
      setState(() => _up = response['state'] == 'interface_up');
    } on FormatException catch (error) {
      if (mounted) setState(() => _errorCode = error.message);
    } catch (error) {
      if (mounted) setState(() => _errorCode = _nativeError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _disconnect() async {
    if (_busy || !Platform.isAndroid) return;
    setState(() {
      _busy = true;
      _errorCode = null;
    });
    try {
      await _controller.stop();
      if (mounted) setState(() => _up = false);
    } catch (error) {
      if (mounted) setState(() => _errorCode = _nativeError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  // Values remain unavailable until native handshake and byte counters
  // have been verified. Never fabricate IP, ping or traffic measurements.
  Widget _metric(BuildContext context, IconData icon, String label, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 11),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(13),
        border: Border.all(
          color: Theme.of(context).colorScheme.outline.withValues(alpha: .22)),
      ),
      child: Column(children: [
        Icon(icon, size: 17),
        const SizedBox(height: 4),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 3),
        Text(value, style: Theme.of(context).textTheme.titleMedium),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStrings.of(context);
    final available = widget.catalog.entries
        .where((entry) => entry.selected).toList(growable: false);
    if (available.isEmpty) {
      return Text(s.pick('پروتکل فعالی برای این اشتراک وجود ندارد.',
          'No protocols enabled for this subscription.'));
    }
    // Protocol selection happens on the Servers screen. Never silently
    // change the explicitly chosen protocol to WireGuard.
    final requested = widget.selectedProtocolCode;
    final chosen = requested != null
        ? available.where((e) => e.protocol.code == requested).firstOrNull
        : available.where((e) => e.protocol.code == 'wireguard').firstOrNull ??
            available.first;
    final nativeReady = Platform.isAndroid &&
        widget.native.supports('wireguard') &&
        chosen?.protocol.code == 'wireguard' &&
        chosen?.configRecordPresent == true;
    final protocolName = chosen?.protocol.name ?? (requested ?? '—');
    final connected = _up;
    final accent = connected ? const Color(0xFF35D9AE)
        : const Color(0xFF72C1D6);

    return Column(
      key: const Key('androidConnectionCard'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Center(
          child: AnimatedContainer(
            key: const Key('androidVerifiedStatus'),
            duration: const Duration(milliseconds: 350),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
            decoration: BoxDecoration(
              color: accent.withValues(alpha: .12),
              border: Border.all(color: accent.withValues(alpha: .45)),
              borderRadius: BorderRadius.circular(25),
            ),
            child: Text(
              _busy
                  ? s.pick('در حال اتصال...', 'Connecting...')
                  : connected
                      ? s.wireGuardActiveUnverified
                      : s.pick('آفلاین هستید', 'You are offline'),
              textAlign: TextAlign.center,
              style: TextStyle(color: accent, fontWeight: FontWeight.w700),
            ),
          ),
        ),
        const SizedBox(height: 25),
        Center(
          child: TweenAnimationBuilder<double>(
            tween: Tween(begin: .96, end: connected ? 1.08 : 1),
            duration: const Duration(milliseconds: 480),
            curve: Curves.easeOutCubic,
            builder: (context, scale, child) =>
                Transform.scale(scale: scale, child: child),
            child: Container(
              key: const Key('androidPowerIndicator'),
              width: 156, height: 156,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(colors: [
                  accent.withValues(alpha: .22),
                  accent.withValues(alpha: .06),
                ]),
                border: Border.all(
                  color: accent.withValues(alpha: .55), width: 2),
                boxShadow: [
                  BoxShadow(color: accent.withValues(alpha: .14),
                      blurRadius: 36, spreadRadius: 6),
                ],
              ),
              child: Icon(Icons.power_settings_new_rounded,
                  color: accent, size: 72),
            ),
          ),
        ),
        const SizedBox(height: 22),
        Text(protocolName, textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.w700)),
        const SizedBox(height: 7),
        Text(
          widget.selectedNodeId == null
              ? s.pick('انتخاب خودکار سرور', 'Automatic server selection')
              : s.pick('سرور انتخاب‌شده', 'Selected server'),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 15),
        if (!connected && !nativeReady)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Text(
              chosen?.configRecordPresent != true
                  ? s.pick('این پروتکل در اشتراک فعال نیست یا کانفیگ ندارد.',
                      'This protocol is unavailable or has no profile.')
                  : s.pick('موتور این پروتکل در اندروید هنوز آماده اتصال نیست.',
                      'This protocol engine is not ready on Android yet.'),
              textAlign: TextAlign.center,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ),
        SizedBox(
          height: 55,
          child: FilledButton.icon(
            key: const Key('androidPrimaryConnect'),
            onPressed: _busy ? null : connected ? _disconnect
                : nativeReady ? _connect : null,
            icon: Icon(connected ? Icons.stop_circle_outlined :
                Icons.power_settings_new_rounded),
            label: Text(connected ? s.wireGuardDisconnect
                : s.pick('اتصال', 'Connect')),
          ),
        ),
        const SizedBox(height: 18),
        Container(
          key: const Key('androidNetworkOverview'),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surface.withValues(alpha: .10),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: accent.withValues(alpha: .20)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(s.pick('وضعیت شبکه', 'Network status'),
                style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 10),
              Text(connected ? s.wireGuardActiveUnverified :
                  s.pick('تونل غیرفعال است', 'Tunnel disconnected')),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(child: _metric(context, Icons.public, 'IP', '—')),
                const SizedBox(width: 8),
                Expanded(child: _metric(context, Icons.bolt, 'Ping', '—')),
              ]),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(child: _metric(context, Icons.arrow_downward,
                    s.pick('دانلود', 'Download'), '—')),
                const SizedBox(width: 8),
                Expanded(child: _metric(context, Icons.arrow_upward,
                    s.pick('آپلود', 'Upload'), '—')),
              ]),
            ],
          ),
        ),
        if (_errorCode != null) ...[
          const SizedBox(height: 12),
          Text(
            _errorCode == 'NO_WIREGUARD_CONFIG' ||
                    _errorCode == 'SELECTED_WIREGUARD_NODE_UNAVAILABLE'
                ? s.wireGuardNoConfigs
                : s.nativeError(_errorCode!),
            textAlign: TextAlign.center,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
          const SizedBox(height: 5),
          SelectableText(
            'VPN error: ${_errorCode!}',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ],
    );
  }
}
