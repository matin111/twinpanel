import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app_strings.dart';
import 'connection_bootstrap.dart';
import 'native_vpn_bridge.dart';
import 'protocols.dart';
import 'server_inventory.dart';
import 'tenant_api.dart';
import 'tenant_models.dart';
import 'vpn_policy_store.dart';
import 'windows_wireguard.dart';

/// Actual Windows WireGuard system-tunnel controls, distinct from the offline
/// Dev dashboard. Requires the official WireGuard installation, Administrator
/// privileges, current panel authorization and a strict full-tunnel profile.
///
/// A running Windows service is shown as "interface up", never "connected".
class WindowsConnectionCard extends StatefulWidget {
  const WindowsConnectionCard({
    required this.panel,
    required this.username,
    required this.sessionToken,
    required this.catalog,
    required this.servers,
    super.key,
  });

  final PanelDirectoryEntry panel;
  final String username;
  final String sessionToken;
  final PanelProtocolCatalog catalog;
  final AppServerInventory servers;

  @override
  State<WindowsConnectionCard> createState() => _WindowsConnectionCardState();
}

class _WindowsConnectionCardState extends State<WindowsConnectionCard> {
  final _controller = const WindowsWireGuardController();
  final _store = const VpnPolicyStore();
  bool _busy = false;
  bool _up = false;
  bool _needsCleanup = false;
  bool _unmanaged = false;
  bool _peerVerified = false;
  int _receivedBytes = 0;
  int _sentBytes = 0;
  bool _ready = false;
  String? _selectedId;
  String? _errorCode;

  bool get _allowed => widget.catalog.entries.any((entry) =>
    entry.protocol.code == 'wireguard' &&
    entry.selected && entry.configRecordPresent);

  @override
  void initState() {
    super.initState();
    _refreshNative();
  }

  Future<void> _refreshNative() async {
    if (!Platform.isWindows) return;
    try {
      final status = await _controller.status();
      final native = await NativeVpnBridge.protocolReadiness();
      if (!mounted) return;
      setState(() {
        _up = status['state'] == 'interface_up' ||
            status['state'] == 'peer_verified';
        _needsCleanup = status['state'] == 'needs_cleanup';
        _unmanaged = status['state'] == 'unmanaged_service';
        _peerVerified = status['state'] == 'peer_verified' &&
            status['peerHandshakeVerified'] == true;
        _receivedBytes = status['rxBytes'] is int
            ? status['rxBytes'] as int : 0;
        _sentBytes = status['txBytes'] is int
            ? status['txBytes'] as int : 0;
        _ready = native.supports('wireguard');
      });
    } catch (_) {
      if (mounted) setState(() => _ready = false);
    }
  }

  String _safeError(Object error) {
    if (error is PlatformException) return error.code;
    if (error is TenantApiException) return error.message;
    if (error is ConnectionBootstrapException) return error.code;
    if (error is FormatException) return error.message;
    return 'WINDOWS_WIREGUARD_FAILED';
  }

  Future<void> _connect() async {
    final selectedId = _selectedId;
    if (_busy || _up || !Platform.isWindows || !_ready || !_allowed ||
        selectedId == null) return;
    setState(() { _busy = true; _errorCode = null; });
    try {
      final api = TenantApi.fromBuildConfig();
      final policy = await _store.load(widget.panel.namespace, widget.username);
      final capabilities = await NativeVpnBridge.probe();
      final native = await NativeVpnBridge.protocolReadiness();
      // The panel authorization and assigned node list are re-fetched
      // immediately before any private profile is requested.
      final candidate = await ConnectionBootstrap(api: api).prepare(
        panel: widget.panel,
        sessionToken: widget.sessionToken,
        serverId: selectedId,
        protocolCode: 'wireguard',
        policy: policy,
        capabilities: capabilities,
        nativeProtocols: native,
      );
      final node = WindowsWireGuardController.configForSingleNode(
        candidate.profiles, selectedId);
      final result = await _controller.start(
        node: node,
        policy: policy,
        capabilities: capabilities,
        nativeProtocols: native,
      );
      if (!mounted) return;
      setState(() {
        _up = result['state'] == 'interface_up' ||
            result['state'] == 'peer_verified';
        _needsCleanup = false;
        _unmanaged = false;
        _peerVerified = result['peerHandshakeVerified'] == true;
        _receivedBytes = result['rxBytes'] is int ? result['rxBytes'] as int : 0;
        _sentBytes = result['txBytes'] is int ? result['txBytes'] as int : 0;
      });
    } catch (error) {
      if (mounted) setState(() => _errorCode = _safeError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _disconnect() async {
    if (_busy || (!_up && !_needsCleanup) || !Platform.isWindows) return;
    setState(() { _busy = true; _errorCode = null; });
    try {
      await _controller.stop();
      if (mounted) setState(() {
        _up = false;
        _needsCleanup = false;
        _unmanaged = false;
        _peerVerified = false;
        _receivedBytes = 0;
        _sentBytes = 0;
      });
    } catch (error) {
      if (mounted) setState(() => _errorCode = _safeError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = AppStrings.of(context);
    if (!Platform.isWindows || (!_allowed && !_up)) {
      return const SizedBox.shrink();
    }
    final available = widget.servers.servers.toList(growable: false);
    final validSelection = available.any((server) => server.id == _selectedId)
        ? _selectedId : null;

    return Card(
      key: const Key('windowsConnectionCard'),
      child: Padding(
        padding: const EdgeInsets.all(17),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(s.pick('اتصال WireGuard ویندوز', 'Windows WireGuard'),
                style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 9),
            Text(_unmanaged
                ? s.pick(
                    'یک سرویس WireGuard با همین نام متعلق به این برنامه نیست؛ '
                    'برای جلوگیری از اختلال، تغییری در آن ایجاد نمی‌شود.',
                    'A same-named WireGuard service is not owned by TwinConnect. '
                    'It will not be modified.')
                : _needsCleanup
                ? s.pick(
                    'سرویس قبلی ناقص مانده؛ برای پاک‌سازی روی دکمه پایین بزنید.',
                    'Previous tunnel service needs cleanup before reconnecting.')
                : _up
                ? (_peerVerified
                    ? s.pick('دست‌دهی WireGuard با سرور تأیید شد؛ '
                            'دسترسی اینترنت و نبود نشت هنوز آزموده نشده‌اند.',
                            'WireGuard peer handshake verified; '
                            'internet access and leak tests remain unverified.')
                    : s.pick(
                        'رابط WireGuard فعال است؛ ارتباط با سرور هنوز تأیید نشده.',
                        'Interface is up; peer handshake not yet verified.'))
                : _ready
                    ? s.pick(
                        'WireGuard نصب است. برای اتصال، سرور مجاز را انتخاب کنید.',
                        'WireGuard is installed. Select an authorized server.')
                    : s.pick(
                        'WireGuard رسمی را نصب کنید و TwinConnect را با Administrator اجرا کنید.',
                        'Install official WireGuard and run TwinConnect as Administrator.')),
            if (_up) ...[
              const SizedBox(height: 10),
              Wrap(spacing: 18, runSpacing: 7, children: [
                Text(s.pick('دریافت: $_receivedBytes بایت',
                    'Received: $_receivedBytes bytes')),
                Text(s.pick('ارسال: $_sentBytes بایت',
                    'Sent: $_sentBytes bytes')),
              ]),
            ],
            const SizedBox(height: 10),
            if (!_up && !_needsCleanup && !_unmanaged)
              DropdownButtonFormField<String>(
                key: const Key('windowsWireGuardServer'),
                initialValue: validSelection,
                isExpanded: true,
                decoration: InputDecoration(
                  labelText: s.pick('سرور WireGuard', 'WireGuard server'),
                ),
                items: [
                  for (final server in available)
                    DropdownMenuItem(
                      value: server.id,
                      child: Text(server.nodeOnline
                          ? server.name
                          : '${server.name} · ${s.pick('وضعیت نود نامشخص', 'status unverified')}'),
                    ),
                ],
                onChanged: _busy ? null : (value) => setState(() {
                  _selectedId = value;
                }),
              ),
            const SizedBox(height: 12),
            FilledButton.icon(
              key: const Key('windowsWireGuardAction'),
              onPressed: _busy
                  ? null
                  : (_up || _needsCleanup)
                      ? _disconnect
                      : (_ready && !_unmanaged && _allowed &&
                          validSelection != null)
                          ? _connect : null,
              icon: Icon(_up || _needsCleanup ? Icons.stop_circle_outlined
                  : Icons.power_settings_new_rounded),
              label: Text(_needsCleanup
                  ? s.pick('پاک‌سازی سرویس', 'Clean up service')
                  : _up
                      ? s.pick('قطع رابط', 'Stop interface')
                      : s.pick('شروع WireGuard', 'Start WireGuard')),
            ),
            const SizedBox(height: 5),
            OutlinedButton.icon(
              key: const Key('windowsWireGuardRefresh'),
              onPressed: _busy ? null : _refreshNative,
              icon: const Icon(Icons.refresh_rounded),
              label: Text(s.pick('بررسی وضعیت', 'Check status')),
            ),
            if (_errorCode != null) ...[
              const SizedBox(height: 9),
              Text(
                s.pick('اتصال انجام نشد: $_errorCode',
                    'Tunnel could not start: $_errorCode'),
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
