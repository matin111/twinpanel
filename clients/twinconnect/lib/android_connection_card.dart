import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'android_connection_strings.dart';
import 'android_tunnel.dart';
import 'cisco_openconnect_profile.dart';
import 'app_strings.dart';
import 'native_vpn_bridge.dart';
import 'protocols.dart';
import 'tenant_api.dart';
import 'tenant_models.dart';
import 'server_inventory.dart';
import 'vpn_policy_store.dart';
import 'twinconnect_wave_indicator.dart';

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
    this.subscriptionContent,
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
  final Widget? subscriptionContent;

  @override
  State<AndroidConnectionCard> createState() => _AndroidConnectionCardState();
}

class _AndroidConnectionCardState extends State<AndroidConnectionCard> {
  final _controller = const AndroidTunnelController();
  final _store = const VpnPolicyStore();

  bool _busy = false;
  bool _up = false;
  bool _ciscoUp = false;
  String? _errorCode;
  AppServer? _activeServer;
  String? _activeServerName;
  final List<double> _rxSamples = <double>[];
  final List<double> _txSamples = <double>[];
  Timer? _telemetryTimer;
  bool _polling = false;
  bool _handshake = false;
  int? _rxBytes, _txBytes;
  double? _downloadBps, _uploadBps;
  DateTime? _lastCountersAt;
  String? _publicIp;
  int? _httpsLatencyMs;
  bool _checkingInternet = false;
  DateTime? _lastInternetCheck;

  @override
  void initState() {
    super.initState();
    unawaited(_refresh());
    _telemetryTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      unawaited(_refresh());
    });
  }

  @override
  void dispose() {
    _telemetryTimer?.cancel();
    super.dispose();
  }

  static int? _counter(dynamic value) =>
      value is int && value >= 0 ? value : null;

  static String _speed(double? bytesPerSecond) {
    if (bytesPerSecond == null) return '—';
    if (bytesPerSecond < 1024) return '${bytesPerSecond.toStringAsFixed(0)} B/s';
    if (bytesPerSecond < 1024 * 1024) {
      return '${(bytesPerSecond / 1024).toStringAsFixed(1)} KB/s';
    }
    return '${(bytesPerSecond / (1024 * 1024)).toStringAsFixed(2)} MB/s';
  }

  void _clearTelemetry() {
    _rxBytes = null;
    _txBytes = null;
    _downloadBps = null;
    _uploadBps = null;
    _lastCountersAt = null;
    _rxSamples.clear();
    _txSamples.clear();
    _handshake = false;
    _publicIp = null;
    _httpsLatencyMs = null;
    _lastInternetCheck = null;
    _activeServer = null;
    _activeServerName = null;
  }

  Future<void> _refresh() async {
    if (!Platform.isAndroid || _polling) return;
    _polling = true;
    try {
      if (_ciscoUp) {
        final status = await _controller.ciscoStatus();
        if (!mounted) return;
        if (status['state'] != 'interface_up' ||
            status['trafficRoutingVerified'] != true) {
          setState(() {
            _ciscoUp = false;
            _clearTelemetry();
          });
        }
        return;
      }
      final status = await _controller.status();
      if (!mounted) return;
      final up = status['state'] == 'interface_up';
      final rx = _counter(status['rxBytes']);
      final tx = _counter(status['txBytes']);
      final now = DateTime.now();
      setState(() {
        _up = up;
        if (!up) {
          _clearTelemetry();
          return;
        }
        _handshake = status['peerHandshakeVerified'] == true;
        if (rx != null && tx != null) {
          final previous = _lastCountersAt;
          final seconds = previous == null ? 0 :
              now.difference(previous).inMilliseconds / 1000.0;
          if (seconds > 0.1 && _rxBytes != null && _txBytes != null) {
            _downloadBps = rx >= _rxBytes! ?
                (rx - _rxBytes!) / seconds : null;
            _uploadBps = tx >= _txBytes! ?
                (tx - _txBytes!) / seconds : null;
          }
          _rxBytes = rx;
          _txBytes = tx;
          _lastCountersAt = now;
          _rxSamples.add(_downloadBps ?? 0.0);
          _txSamples.add(_uploadBps ?? 0.0);
          if (_rxSamples.length > 32) _rxSamples.removeAt(0);
          if (_txSamples.length > 32) _txSamples.removeAt(0);
        } else {
          _downloadBps = null;
          _uploadBps = null;
          _lastCountersAt = null;
          _rxBytes = null;
          _txBytes = null;
        }
        if (!_handshake) {
          _publicIp = null;
          _httpsLatencyMs = null;
        }
      });
      if (up && _handshake &&
          !_checkingInternet && (_lastInternetCheck == null ||
          now.difference(_lastInternetCheck!) > const Duration(seconds: 12))) {
        unawaited(_checkInternet());
      }
    } catch (_) {
      if (mounted) setState(() {
        _up = false;
        _clearTelemetry();
      });
    } finally {
      _polling = false;
    }
  }

  Future<void> _checkInternet() async {
    if (_checkingInternet) return;
    _checkingInternet = true;
    _lastInternetCheck = DateTime.now();
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 5);
    try {
      final watch = Stopwatch()..start();
      final request = await client.getUrl(Uri.https('api.ipify.org', '/'));
      final response = await request.close().timeout(const Duration(seconds: 7));
      final result = (await utf8.decoder.bind(response).join()).trim();
      watch.stop();
      if (response.statusCode != 200 ||
          InternetAddress.tryParse(result) == null) {
        throw const FormatException('PUBLIC_IP_INVALID');
      }
      if (mounted && _up && _handshake) setState(() {
        _publicIp = result;
        _httpsLatencyMs = watch.elapsedMilliseconds;
      });
    } catch (_) {
      if (mounted) setState(() {
        _publicIp = null;
        _httpsLatencyMs = null;
      });
    } finally {
      client.close(force: true);
      _checkingInternet = false;
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
      candidates.add((id, WireGuardNode(name: name, config: raw, nodeId: id), matching));
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

  /// Cisco uses its own engine and authenticated panel profile. Never hand
  /// Cisco credentials to WireGuard or download secrets before readiness.
  Future<void> _connectCisco() async {
    if (_busy || _up || _ciscoUp || !Platform.isAndroid ||
        !widget.native.supports('cisco')) return;
    setState(() {
      _busy = true;
      _errorCode = null;
    });
    try {
      final profiles = await TenantApi.fromBuildConfig()
          .loadSessionNativeProfiles(
            panel: widget.panel,
            sessionToken: widget.sessionToken,
            protocol: VpnProtocols.byCode('cisco')!,
            native: widget.native,
          );
      final selectedId = widget.selectedNodeId;
      final inventory = widget.servers?.servers ?? const <AppServer>[];
      final choices = profiles.items.where((item) {
        final id = item['node_id']?.toString();
        if (id == null || (selectedId != null && selectedId != id)) {
          return false;
        }
        final match = inventory.where((node) => node.id == id).firstOrNull;
        return inventory.isEmpty || match?.nodeOnline == true;
      }).toList(growable: false);
      if (choices.isEmpty) {
        throw const FormatException('CISCO_NO_AUTHORIZED_SERVER');
      }
      final item = choices.first;
      final profile = CiscoOpenConnectProfile.fromItem(item);
      final response = await _controller.connectCisco(
        profile: profile,
        nativeProtocols: widget.native,
      );
      if (!mounted) return;
      if (response['state'] != 'interface_up' ||
          response['trafficRoutingVerified'] != true) {
        throw const FormatException('CISCO_NATIVE_TUNNEL_UNVERIFIED');
      }
      final id = item['node_id']?.toString();
      setState(() {
        _ciscoUp = true;
        _activeServer = inventory.where((node) => node.id == id).firstOrNull;
        _activeServerName = _activeServer?.name ??
            (item['node'] is String ? item['node'] as String : null);
      });
    } on FormatException catch (error) {
      if (mounted) setState(() => _errorCode = error.message);
    } catch (error) {
      if (mounted) setState(() => _errorCode = _nativeError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _disconnectCisco() async {
    if (_busy || !_ciscoUp) return;
    setState(() => _busy = true);
    try {
      await _controller.stopCisco();
      if (mounted) setState(() {
        _ciscoUp = false;
        _clearTelemetry();
      });
    } catch (error) {
      if (mounted) setState(() => _errorCode = _nativeError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
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
      setState(() {
        _up = response['state'] == 'interface_up';
        if (_up) {
          _activeServerName = selected.name;
          _activeServer = widget.servers?.servers
              .where((server) => server.id == selected.nodeId)
              .firstOrNull;
        }
      });
      unawaited(_refresh());
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
      if (mounted) setState(() { _up = false; _clearTelemetry(); });
    } catch (error) {
      if (mounted) setState(() => _errorCode = _nativeError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  // Values remain unavailable until native handshake and byte counters
  // have been verified. Never fabricate IP, ping or traffic measurements.
  static String _countryFlag(String code) {
    final country = code.trim().toUpperCase();
    if (country.length != 2 ||
        !country.codeUnits.every((unit) => unit >= 65 && unit <= 90)) {
      return '🌐';
    }
    return String.fromCharCodes(
      country.codeUnits.map((unit) => 0x1F1E6 + unit - 65),
    );
  }

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
    // Quick Connect chooses ONLY an entitled protocol with an installed,
    // native engine and an existing profile. Never default to Cisco merely
    // because it appears first in the subscription's catalog.
    final readyOptions = available.where((entry) =>
        entry.configRecordPresent &&
        widget.native.supports(entry.protocol.code)).toList(growable: false);
    final chosen = requested != null
        ? available.where((e) => e.protocol.code == requested).firstOrNull
        : readyOptions.where((e) => e.protocol.code == 'wireguard').firstOrNull ??
            readyOptions.firstOrNull;
    final nativeReady = Platform.isAndroid &&
        widget.native.supports('wireguard') &&
        chosen?.protocol.code == 'wireguard' &&
        chosen?.configRecordPresent == true;
    // The active protocol is sourced from the running native engine, not
    // from the browsing filter. A WireGuard interface must NEVER be labeled
    // OpenVPN, Hysteria2, or Cisco when the user switches tabs.
    final connected = _up || _ciscoUp;
    final protocolName = _up ? 'WireGuard'
        : _ciscoUp ? 'Cisco / OpenConnect'
        : chosen?.protocol.name ??
            (requested ?? s.pick('پروتکل آماده‌ای وجود ندارد', 'No ready protocol'));
    final internetVerified = _ciscoUp ||
        (_up && _handshake && _publicIp != null);
    final ciscoSelected = chosen?.protocol.code == 'cisco';
    final ciscoReady = ciscoSelected &&
        widget.native.supports('cisco') &&
        chosen?.configRecordPresent == true;
    final canStartSelected = ciscoSelected ? ciscoReady : nativeReady;
    // An interface without a peer handshake is NOT a successful VPN.
    // Reserve the connected green treatment for verified transport.
    final accent = internetVerified ? const Color(0xFF35D9AE)
        : connected ? const Color(0xFFE8B06B)
        : const Color(0xFF72C1D6);

    return Column(
      key: const Key('androidConnectionCard'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(28),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 21, sigmaY: 21),
            child: Container(
              key: const Key('androidSharedPowerCard'),
              padding: const EdgeInsets.fromLTRB(18, 22, 18, 18),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(28),
                gradient: LinearGradient(
                  colors: Theme.of(context).brightness == Brightness.dark
                      ? [const Color(0xFF203847).withValues(alpha: .48),
                         const Color(0xFF142B37).withValues(alpha: .34),
                         const Color(0xFF234B4B).withValues(alpha: .31)]
                      : [const Color(0xFFFFFFFF).withValues(alpha: .97),
                         const Color(0xFFF8FBFC).withValues(alpha: .96),
                         const Color(0xFFF0F7F8).withValues(alpha: .96)],
                ),
                border: Border.all(
                  color: Theme.of(context).brightness == Brightness.dark
                      ? const Color(0xFF7DA5B0).withValues(alpha: .31)
                      : const Color(0xFFAFCDD3).withValues(alpha: .78)),
              ),
              child: Column(children: [
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
                  : internetVerified
                      ? s.pick('اینترنت VPN تأیید شد', 'VPN internet reachable')
                      : _up && _handshake
                          ? s.pick('دست‌دهی سرور تأیید شد؛ اینترنت هنوز تأیید نشده', 'Peer handshake verified; internet not yet verified')
                          : connected
                              ? s.pick('تونل فعال است، اما اتصال به سرور تأیید نشده', 'Tunnel interface up; server connection unverified')
                              : s.pick('آفلاین هستید', 'You are offline'),
              textAlign: TextAlign.center,
              style: TextStyle(color: accent, fontWeight: FontWeight.w700),
            ),
          ),
        ),
        const SizedBox(height: 25),
        Center(
          child: TwinConnectWaveIndicator(
            key: const Key('androidSharedConnectionDataFabric'),
            connected: connected && _handshake,
            connecting: _busy,
            dark: Theme.of(context).brightness == Brightness.dark,
            rxSamples: List<double>.unmodifiable(_rxSamples),
            txSamples: List<double>.unmodifiable(_txSamples),
          ),
        ),
        const SizedBox(height: 22),
        Text(protocolName, textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.w700)),
        const SizedBox(height: 7),
        Container(
          key: const Key('androidActualConnectedLocation'),
          child: Column(children: [
            Text(
              connected
                  ? (_activeServerName == null
                      ? s.pick('مکان اتصال نامشخص است', 'Connected location unknown')
                      : _activeServerName!)
                  : s.pick('هنوز به سروری متصل نیستید', 'No active server'),
              textAlign: TextAlign.center,
            ),
            if (connected && _activeServer != null) ...[
              const SizedBox(height: 6),
              Text(
                '${_countryFlag(_activeServer!.countryCode)} '
                '${_activeServer!.countryCode.toUpperCase()}',
                key: const Key('androidActiveCountryFlag'),
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ],
          ]),
        ),
        const SizedBox(height: 15),
        if (!connected && !canStartSelected)
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
          height: 59,
          child: FilledButton.icon(
            key: const Key('androidPrimaryConnect'),
            style: FilledButton.styleFrom(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(18)),
            ),
            onPressed: _busy ? null : _ciscoUp ? _disconnectCisco
                : _up ? _disconnect
                : canStartSelected
                    ? (ciscoSelected ? _connectCisco : _connect) : null,
            icon: Icon(connected ? Icons.stop_rounded :
                Icons.bolt_rounded),
            label: Text(connected
                ? s.pick('قطع تونل', 'Disconnect tunnel')
                : !canStartSelected
                    ? s.pick('اتصال در دسترس نیست', 'Connection unavailable')
                    : s.pick('اتصال سریع', 'Connect now')),
          ),
        ),
        if (widget.subscriptionContent != null) ...[
          const SizedBox(height: 12),
          widget.subscriptionContent!,
        ],
              ]),
            ),
          ),
        ),
        const SizedBox(height: 12),
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
              Text(!connected ? s.pick('تونل غیرفعال است', 'Tunnel disconnected')
                  : internetVerified
                      ? s.pick('دسترسی اینترنت از VPN تأیید شد.', 'Internet reachable through VPN.')
                      : _up && _handshake
                          ? s.pick('دست‌دهی انجام شده اما اینترنت هنوز تأیید نشده.', 'Peer handshake received; VPN internet not yet verified.')
                          : s.pick('رابط VPN فعال است اما هنوز پاسخ سرور دریافت نشده است. ممکن است اینترنت کار نکند.',
                              'VPN interface is up but no server handshake has been verified. Internet may not work.')),
              if (_up && !_handshake) ...[
                const SizedBox(height: 8),
                SelectableText(
                  'Diagnostic: WG_INTERFACE_UP_NO_HANDSHAKE',
                  key: const Key('androidNoHandshakeDiagnostic'),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
              const SizedBox(height: 12),
              Row(children: [
                Expanded(child: _metric(context, Icons.public, 'IP', _publicIp ?? '—')),
                const SizedBox(width: 8),
                Expanded(child: _metric(context, Icons.bolt, 'HTTPS',
                    _httpsLatencyMs == null ? '—' : '${_httpsLatencyMs} ms')),
              ]),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(child: _metric(context, Icons.arrow_downward,
                    s.pick('دانلود', 'Download'), _speed(_downloadBps))),
                const SizedBox(width: 8),
                Expanded(child: _metric(context, Icons.arrow_upward,
                    s.pick('آپلود', 'Upload'), _speed(_uploadBps))),
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
