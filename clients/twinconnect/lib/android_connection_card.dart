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
    super.key,
  });

  final PanelDirectoryEntry panel;
  final String username;
  final String sessionToken;
  final PanelProtocolCatalog catalog;
  final NativeProtocolReadiness native;
  // Exact panel node ID selected on the shared Servers screen.
  final String? selectedNodeId;

  @override
  State<AndroidConnectionCard> createState() => _AndroidConnectionCardState();
}

class _AndroidConnectionCardState extends State<AndroidConnectionCard> {
  final _controller = const AndroidTunnelController();
  final _store = const VpnPolicyStore();

  bool _busy = false;
  bool _up = false;
  String? _errorCode;
  String? _selectedProtocolCode;

  PanelProtocolStatus? _entry(String code) {
    for (final row in widget.catalog.entries) {
      if (row.protocol.code == code) return row;
    }
    return null;
  }

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

  Future<WireGuardNode?> _chooseNode(List<WireGuardNode> nodes) async {
    if (nodes.isEmpty) return null;
    if (nodes.length == 1) return nodes.single;
    return showDialog<WireGuardNode>(
      context: context,
      builder: (dialogContext) => SimpleDialog(
        title: Text(AppStrings.of(dialogContext).wireGuardChooseServer),
        children: [
          for (final node in nodes)
            SimpleDialogOption(
              onPressed: () => Navigator.pop(dialogContext, node),
              child: Text(node.name),
            ),
        ],
      ),
    );
  }

  Future<void> _connect() async {
    if (_selectedProtocolCode != 'wireguard' && _selectedProtocolCode != null) return;
    if (_busy || _up || !Platform.isAndroid ||
        !widget.native.supports('wireguard')) {
      return;
    }
    setState(() {
      _busy = true;
      _errorCode = null;
    });
    try {
      final policy = await _store.load(
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
      final selectedProfiles = selectedNodeId == null
          ? profiles
          : ClientProtocolProfiles(
              namespace: profiles.namespace,
              protocol: profiles.protocol,
              items: profiles.items.where((item) =>
                  item['node_id']?.toString() == selectedNodeId).toList(),
            );
      // Never silently connect to a different country/node than selected.
      final nodes = AndroidTunnelController.wireGuardNodes(selectedProfiles);
      if (nodes.isEmpty) {
        if (mounted) setState(() => _errorCode = selectedNodeId == null
            ? 'NO_WIREGUARD_CONFIG' : 'SELECTED_WIREGUARD_NODE_UNAVAILABLE');
        return;
      }
      if (!mounted) return;
      final selected = await _chooseNode(nodes);
      if (selected == null) return;
      final response = await _controller.connectWireGuard(
        node: selected,
        policy: policy,
        capabilities: capabilities,
        nativeProtocols: widget.native,
      );
      if (!mounted) return;
      setState(() => _up = response['state'] == 'interface_up');
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

  @override
  Widget build(BuildContext context) {
    final s = AppStrings.of(context);
    final available = widget.catalog.entries
        .where((entry) => entry.selected).toList(growable: false);
    if (available.isEmpty) return const SizedBox.shrink();
    // All protocols allowed by this tenant's plan remain visible. Runtime
    // readiness is separate from subscription entitlement.
    final chosenCode = available.any((entry) =>
            entry.protocol.code == _selectedProtocolCode)
        ? _selectedProtocolCode!
        : available.first.protocol.code;
    final chosen = available.firstWhere(
        (entry) => entry.protocol.code == chosenCode);
    final wireguard = _entry('wireguard');
    final nativeReady = Platform.isAndroid &&
        widget.native.supports('wireguard') &&
        wireguard?.selected == true &&
        wireguard?.configRecordPresent == true;
    final canConnect = chosenCode == 'wireguard' && nativeReady;

    return Padding(
      key: const Key('androidConnectionCard'),
      padding: const EdgeInsets.all(10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              s.pick('پروتکل‌های مجاز اشتراک', 'Subscription protocols'),
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            Wrap(
              key: const Key('androidProtocolChooser'),
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final entry in available)
                  ChoiceChip(
                    key: Key('androidProtocol_${entry.protocol.code}'),
                    label: Text(entry.protocol.name),
                    selected: chosenCode == entry.protocol.code,
                    onSelected: _busy ? null : (_) => setState(() {
                      _selectedProtocolCode = entry.protocol.code;
                      _errorCode = null;
                    }),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              !chosen.configRecordPresent
                  ? s.pick('کانفیگ این پروتکل در اشتراک موجود نیست.',
                           'No profile for this protocol in your subscription.')
                  : canConnect
                      ? (_up ? s.wireGuardActiveUnverified : s.wireGuardReady)
                      : s.pick('موتور اتصال این پروتکل در نسخه اندروید هنوز آماده نیست.',
                               'This protocol engine is not yet available on Android.'),
            ),
            const SizedBox(height: 10),
            if (chosenCode == 'wireguard')
              FilledButton.icon(
                key: const Key('androidWireGuardAction'),
                onPressed: _busy ? null :
                    _up ? _disconnect : canConnect ? _connect : null,
                icon: Icon(_up
                    ? Icons.stop_circle_outlined : Icons.power_settings_new),
                label: Text(_up ? s.wireGuardDisconnect : s.wireGuardConnect),
              )
            else if (_up)
              FilledButton.icon(
                onPressed: _busy ? null : _disconnect,
                icon: const Icon(Icons.stop_circle_outlined),
                label: Text(s.wireGuardDisconnect),
              ),
            if (_errorCode != null) ...[
              const SizedBox(height: 10),
              Text(
                _errorCode == 'NO_WIREGUARD_CONFIG' ||
                    _errorCode == 'SELECTED_WIREGUARD_NODE_UNAVAILABLE'
                    ? s.wireGuardNoConfigs
                    : s.nativeError(_errorCode!),
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
          ],
        ),
    );
  }
}
