import 'dart:ui' show ImageFilter, FontFeature;
import 'dart:io' show Platform, HttpClient, InternetAddress, Process, ProcessException, FileSystemException, SocketException, HttpException;
import 'dart:convert' show utf8;
import 'dart:async' show Timer, TimeoutException, unawaited;

import 'package:flutter/services.dart' show PlatformException;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'protocols.dart';
import 'server_inventory.dart';
import 'server_latency.dart';
import 'windows_singbox_preflight.dart';
import 'singbox_profile_validator.dart';
import 'shadowtls_chain.dart';
import 'singbox_windows_config.dart';
import 'windows_singbox_tunnel.dart';
import 'windows_xray_proxy.dart';
import 'windows_sudoku_proxy.dart';
import 'sudoku_client_profile.dart';
import 'windows_xray_preflight.dart';
import 'xray_inbound_profiles.dart';
import 'xray_inbound_secure_cache.dart';
import 'xray_inbound_latency.dart';
import 'windows_openconnect_tunnel.dart';
import 'windows_openvpn_tunnel.dart';
import 'windows_l2tp_tunnel.dart';
import 'l2tp_profile.dart';
import 'openvpn_profile_validator.dart';
import 'cisco_openconnect_profile.dart';
import 'connection_bootstrap.dart';
import 'tenant_api.dart';
import 'vpn_policy_store.dart';
import 'vpn_policy.dart';
import 'windows_wireguard.dart';
import 'tenant_models.dart';
import 'brand_theme.dart';
import 'plan_classification.dart';
import 'account_snapshot.dart';
import 'native_vpn_bridge.dart';
import 'country_flag.dart';
import 'ambient_background.dart';
import 'interactive_glass_card.dart';
import 'share_vpn_preview.dart';
import 'connection_signal_art.dart';
import 'tunnel_traffic_chart.dart';
import 'vpn_settings.dart';

/// Authenticated application uses the original visual dashboard layout with live data.

class TwinConnectLiveDashboard extends StatefulWidget {
  const TwinConnectLiveDashboard({
    required this.panel,
    required this.username,
    required this.brand,
    this.onBrandRefresh,
    required this.sessionToken,
    required this.catalog,
    required this.servers,
    this.serverRefreshError,
    required this.native,
    required this.onRefresh,
    required this.plan,
    required this.accountStatus,
    required this.account,
    required this.onLogout,
    required this.onRefreshAccount,
    this.accountError,
    super.key,
  });
  final PanelDirectoryEntry panel;
  final String username;
  final BrandPreview brand;
  final Future<bool> Function()? onBrandRefresh;
  final String sessionToken;
  final PanelProtocolCatalog? catalog;
  final AppServerInventory? servers;
  final String? serverRefreshError;
  final NativeProtocolReadiness native;
  final VoidCallback onRefresh;
  final AppPlanClassification? plan;
  final String accountStatus;
  final AppAccountSnapshot? account;
  final VoidCallback onLogout;
  final VoidCallback onRefreshAccount;
  final String? accountError;
  @override
  State<TwinConnectLiveDashboard> createState() => _TwinConnectLiveDashboardState();
}

class _DemoServer {
  const _DemoServer(this.flag, this.country, this.city, this.protocols);
  final String flag;
  final String country;
  final String city;
  final List<String> protocols;
}

class _TwinConnectLiveDashboardState extends State<TwinConnectLiveDashboard> {
  final WindowsWireGuardController _vpn = const WindowsWireGuardController();
  late final WindowsSingBoxTunnel _modernTunnel = WindowsSingBoxTunnel(
    onUnexpectedExit: () {
      _modernHealthTimer?.cancel();
      _stopModernTrafficMonitoring();
      // Never leave a credential-bearing local Xray proxy running if
      // the Windows TUN that owns system routes exits unexpectedly.
      if (_xrayProxy.isRunning) {
        _xrayProxy.stop().catchError((Object _) {});
      }
      if (_sudokuProxy.isRunning) {
        _sudokuProxy.stop().catchError((Object _) {});
      }
      if (!mounted) return;
      setState(() {
        _modernUp = false;
        _vpnError = 'SINGBOX_TUNNEL_EXITED';
        _publicIp = null;
      });
    },
  );
  late final WindowsXrayProxy _xrayProxy = WindowsXrayProxy(
    onUnexpectedExit: () {
      _modernHealthTimer?.cancel();
      _stopModernTrafficMonitoring();
      // The TUN must also stop if its upstream SOCKS process disappears.
      _modernTunnel.stop().catchError((Object _) {});
      if (!mounted) return;
      setState(() {
        _modernUp = false;
        _vpnError = 'XRAY_PROCESS_EXITED';
        _publicIp = null;
      });
    },
  );
  late final WindowsSudokuProxy _sudokuProxy = WindowsSudokuProxy(
    onUnexpectedExit: () {
      _modernHealthTimer?.cancel();
      _stopModernTrafficMonitoring();
      // The full-tunnel adapter must stop when its Sudoku upstream dies.
      _modernTunnel.stop().catchError((Object _) {});
      if (!mounted) return;
      setState(() {
        _modernUp = false;
        _vpnError = _sudokuProxy.lastUnexpectedExitReason ?? 'SUDOKU_CORE_EXITED';
        _publicIp = null;
      });
    },
  );
  final WindowsOpenConnectTunnel _ciscoTunnel = WindowsOpenConnectTunnel();
  final WindowsOpenVpnTunnel _openVpnTunnel = WindowsOpenVpnTunnel();
  final WindowsL2tpTunnel _l2tpTunnel = WindowsL2tpTunnel();
  bool _modernUp = false;
  Timer? _modernHealthTimer;
  Timer? _modernTrafficTimer;
  bool _modernTrafficBusy = false;
  int? _modernRx;
  int? _modernTx;
  int? _tunnelOriginRx;
  int? _tunnelOriginTx;
  bool _modernHealthBusy = false;
  int _modernHealthFailures = 0;
  String? _modernProtocol;
  String? _modernNodeId;
  final VpnPolicyStore _vpnPolicy = const VpnPolicyStore();
  bool _vpnBusy = false;
  bool _vpnUp = false;
  bool _vpnVerified = false;
  bool _vpnReady = false;
  bool _vpnUnmanaged = false;
  bool _vpnCleanup = false;
  int _vpnRx = 0;
  int _vpnTx = 0;
  final List<double> _rxHistory = [];
  final List<double> _txHistory = [];
  DateTime? _lastSampleAt;
  int? _lastSampleRx;
  int? _lastSampleTx;
  String? _lastSampleSource;
  double? _rxBytesPerSecond;
  double? _txBytesPerSecond;

  void _clearTrafficSamples() {
    _rxHistory.clear();
    _txHistory.clear();
    _lastSampleAt = null;
    _lastSampleRx = null;
    _lastSampleTx = null;
    _lastSampleSource = null;
    _rxBytesPerSecond = null;
    _txBytesPerSecond = null;
  }

  // Only measured native byte deltas are plotted; a new connection,
  // counter reset or protocol change starts a fresh baseline.
  void _recordTraffic(String source, int rx, int tx) {
    final now = DateTime.now();
    if (_lastSampleSource != source || _lastSampleAt == null ||
        _lastSampleRx == null || _lastSampleTx == null ||
        rx < _lastSampleRx! || tx < _lastSampleTx!) {
      _clearTrafficSamples();
      _lastSampleSource = source;
      _lastSampleAt = now;
      _lastSampleRx = rx;
      _lastSampleTx = tx;
      return;
    }
    final elapsed = now.difference(_lastSampleAt!).inMilliseconds / 1000;
    if (elapsed < .3) return;
    final rxRate = (rx - _lastSampleRx!) / elapsed;
    final txRate = (tx - _lastSampleTx!) / elapsed;
    _lastSampleAt = now;
    _lastSampleRx = rx;
    _lastSampleTx = tx;
    if (!rxRate.isFinite || !txRate.isFinite ||
        rxRate < 0 || txRate < 0) return;
    _rxBytesPerSecond = rxRate;
    _txBytesPerSecond = txRate;
    _rxHistory.add(rxRate);
    _txHistory.add(txRate);
    if (_rxHistory.length > 24) _rxHistory.removeAt(0);
    if (_txHistory.length > 24) _txHistory.removeAt(0);
  }

  String? _vpnError;
  String? _publicIp;
  int? _httpsLatencyMs;
  bool _autoFastest = false;
  bool _networkRefreshing = false;
  int _networkEpoch = 0;
  Timer? _networkTimer;
  // Only a verified tunnel counts as connected. Tick just the duration label,
  // not the whole blurred dashboard, to avoid unnecessary GPU work.
  final ValueNotifier<int> _connectedSeconds = ValueNotifier<int>(0);
  DateTime? _connectedSince;
  Timer? _durationTicker;

  bool get _verifiedConnectionActive => _modernUp || _vpnVerified;

  void _updateConnectionClock() {
    if (!_verifiedConnectionActive) {
      _connectedSince = null;
      if (_connectedSeconds.value != 0) _connectedSeconds.value = 0;
      return;
    }
    _connectedSince ??= DateTime.now();
    final seconds = DateTime.now().difference(_connectedSince!).inSeconds;
    if (_connectedSeconds.value != seconds) _connectedSeconds.value = seconds;
  }

  static String _formatConnectedSeconds(int seconds) {
    final duration = Duration(seconds: seconds);
    final hours = duration.inHours.toString().padLeft(2, '0');
    final minutes = (duration.inMinutes % 60).toString().padLeft(2, '0');
    final remainder = (duration.inSeconds % 60).toString().padLeft(2, '0');
    return '$hours:$minutes:$remainder';
  }

  String? _activeNodeId;

  final Map<String, int?> _nodePings = {};
  final Map<String, String> _nodePingErrors = {};
  // Group headers are collapsed by default. Keep expansion state per country,
  // not per server, so refreshed inventories never make the list jump around.
  final Set<String> _expandedCountries = {};
  static const Map<String, String> _countryNamesFa = {
    'DE': 'آلمان', 'TR': 'ترکیه', 'US': 'آمریکا', 'FR': 'فرانسه',
    'GB': 'انگلیس', 'UK': 'انگلیس', 'NL': 'هلند', 'FI': 'فنلاند',
    'IR': 'ایران', 'CA': 'کانادا', 'SE': 'سوئد', 'CH': 'سوئیس',
    'AT': 'اتریش', 'IT': 'ایتالیا', 'ES': 'اسپانیا', 'RU': 'روسیه',
    'HK': 'هنگ‌کنگ', 'JP': 'ژاپن', 'AE': 'امارات', 'SG': 'سنگاپور',
  };
  static const Map<String, String> _countryNamesEn = {
    'DE': 'Germany', 'TR': 'Turkey', 'US': 'United States',
    'FR': 'France', 'GB': 'United Kingdom', 'UK': 'United Kingdom',
    'NL': 'Netherlands', 'FI': 'Finland', 'IR': 'Iran',
    'CA': 'Canada', 'SE': 'Sweden', 'CH': 'Switzerland',
    'AT': 'Austria', 'IT': 'Italy', 'ES': 'Spain', 'RU': 'Russia',
    'HK': 'Hong Kong', 'JP': 'Japan', 'AE': 'United Arab Emirates',
    'SG': 'Singapore',
  };
  String _countryLabel(String code) {
    final normalized = CountryFlag.normalizedCode(code);
    return (_persian ? _countryNamesFa : _countryNamesEn)[normalized]
        ?? normalized;
  }
  final Set<String> _pingingNodes = {};
  bool _pingAllBusy = false;
  bool _statusRefreshing = false;
  bool _nativeReadyRefreshing = false;
  DateTime? _lastNativeReadyCheck;
  int? _latencyFor(AppServer node) => _nodePings.containsKey(node.id)
    ? _nodePings[node.id] : node.latencyMs;

  int? get _connectedServerRtt {
    if (_modernUp && _modernProtocol == 'v2ray' &&
        _selectedXrayNodeId != null && _selectedXrayInboundId != null) {
      final value = _xrayInboundRtts[
          '${_selectedXrayNodeId!}:${_selectedXrayInboundId!}'];
      if (value != null) return value;
    }
    if ((!_vpnUp && !_modernUp) || (_modernUp ? _modernNodeId : _activeNodeId) == null) return null;
    final nodes = widget.servers?.servers;
    if (nodes == null) return null;
    for (final node in nodes) {
      if (node.id == (_modernUp ? _modernNodeId : _activeNodeId)) return _latencyFor(node);
    }
    return null;
  }

  Future<void> _refreshNativeReadiness() async {
    if (_nativeReadyRefreshing || !Platform.isWindows) return;
    _nativeReadyRefreshing = true;
    try {
      final native = await NativeVpnBridge.protocolReadiness()
          .timeout(const Duration(seconds: 8));
      if (mounted) setState(() => _vpnReady = native.supports('wireguard'));
      _lastNativeReadyCheck = DateTime.now();
    } catch (_) {
      // Readiness failure must not erase an already verified tunnel state.
    } finally {
      _nativeReadyRefreshing = false;
    }
  }

  Future<void> _probeNode(int index) async {
    final nodes = widget.servers?.servers;
    if (!Platform.isWindows || nodes == null || index < 0 ||
        index >= nodes.length) { return; }
    final node = nodes[index];
    if (_pingingNodes.contains(node.id)) { return; }
    if (node.probeIp == null) {
      if (mounted) { setState(() {
        _nodePings[node.id] = null;
        _nodePingErrors[node.id] = 'NO_PROBE_ADDRESS';
      }); }
      return;
    }
    setState(() => _pingingNodes.add(node.id));
    int? latency;
    String? error;
    try {
      final clock = Stopwatch()..start();
      final windowsRoot = Platform.environment['SystemRoot'];
      if (windowsRoot == null || windowsRoot.isEmpty) {
        error = 'PING_PROGRAM_UNAVAILABLE';
        return;
      }
      final pingExe = '$windowsRoot\\System32\\PING.EXE';
      final result = await Process.run(pingExe,
        ['-n', '1', '-w', '1500', node.probeIp!],
        runInShell: false).timeout(const Duration(seconds: 4));
      clock.stop();
      if (result.exitCode == 0) {
        final output = result.stdout.toString();
        // Prefer the ICMP reply's RTT when Windows emits an English
        // field; localized Windows installations may omit "time=".
        final match = RegExp(r'time\s*[=<]\s*(\d+)\s*ms',
          caseSensitive: false).firstMatch(output);
        latency = match == null ? null : int.tryParse(match.group(1)!);
        if (latency == null && RegExp(r'time\s*<\s*1\s*ms',
          caseSensitive: false).hasMatch(output)) { latency = 1; }
        // A successful single-reply ping is measured by elapsed time
        // when localized output cannot be parsed. This includes process
        // startup overhead and is explicitly marked approximate.
        if (latency == null) {
          latency = clock.elapsedMilliseconds.clamp(1, 60000).toInt();
          error = 'APPROXIMATE_RTT';
        }
      } else {
        error = 'ICMP_TIMEOUT_OR_BLOCKED';
      }
    } catch (_) {
      error = 'PING_FAILED';
    } finally {
      if (mounted) { setState(() {
        _nodePings[node.id] = latency;
        if (error == null) {
          _nodePingErrors.remove(node.id);
        } else {
          _nodePingErrors[node.id] = error;
        }
        _pingingNodes.remove(node.id);
      }); }
    }
  }
  Future<void> _probeAllNodes() async {
    final nodes = widget.servers?.servers;
    if (nodes == null || _pingAllBusy) return;
    setState(() => _pingAllBusy = true);
    try {
      for (var start = 0; start < nodes.length && mounted; start += 4) {
        final end = start + 4 < nodes.length ? start + 4 : nodes.length;
        await Future.wait([
          for (var i = start; i < end; i++) _probeNode(i),
        ]);
      }
    } finally {
      if (mounted) setState(() => _pingAllBusy = false);
    }
  }


  int? get _fastestKnownIndex {
    final servers = widget.servers?.servers;
    if (servers == null) return null;
    int? best;
    for (var i = 0; i < servers.length; i++) {
      final node = servers[i];
      // Only a measured ICMP value qualifies; panel hints are not live ping.
      final latency = _nodePings[node.id];
      if (!node.nodeOnline || latency == null || latency < 0) continue;
      if (best == null || latency < _nodePings[servers[best].id]!) {
        best = i;
      }
    }
    return best;
  }

  void _resetNetworkStats() {
    _networkEpoch++;
    _networkTimer?.cancel();
    _networkTimer = null;
    _publicIp = null;
    _httpsLatencyMs = null;
  }

  Future<void> _readNetworkStats() async {
    if (!mounted || !_vpnVerified || _networkRefreshing) return;
    _networkRefreshing = true;
    final epoch = _networkEpoch;
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 5);
    try {
      final clock = Stopwatch()..start();
      final request = await client.getUrl(Uri.https('api.ipify.org', '/'));
      final response = await request.close().timeout(const Duration(seconds: 7));
      final ip = (await utf8.decoder.bind(response).join()).trim();
      clock.stop();
      if (response.statusCode != 200 ||
          ip.length > 45 || InternetAddress.tryParse(ip) == null) {
        throw const FormatException('PUBLIC_IP_UNAVAILABLE');
      }
      if (!mounted || epoch != _networkEpoch || !_vpnVerified) return;
      setState(() {
        _publicIp = ip;
        _httpsLatencyMs = clock.elapsedMilliseconds;
      });
    } catch (_) {
      if (mounted && epoch == _networkEpoch && _vpnVerified) {
        setState(() { _publicIp = null; _httpsLatencyMs = null; });
      }
    } finally {
      client.close(force: true);
      _networkRefreshing = false;
    }
  }

  void _startNetworkStats() {
    _networkTimer?.cancel();
    if (!_vpnUp) return;
    if (_vpnVerified) _readNetworkStats();
    _networkTimer = Timer.periodic(const Duration(seconds: 12), (_) {
      if (!mounted) return;
      _refreshVpnStatus();
      if (_vpnVerified) _readNetworkStats();
    });
  }

  Future<void> _disconnectAndSignOut() async {
    if (_vpnBusy) return;
    if (_vpnUnmanaged) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(tr('تونل فعلی توسط TwinConnect مدیریت نمی‌شود.',
          'The current tunnel is not managed by TwinConnect.')),
      ));
      return;
    }
    setState(() { _vpnBusy = true; _vpnError = null; });
    try {
      if (_modernTunnel.isRunning || _xrayProxy.isRunning || _sudokuProxy.isRunning ||
          _ciscoTunnel.isRunning ||
          _openVpnTunnel.hasChild || _l2tpTunnel.hasChild || _modernUp) {
        _modernHealthTimer?.cancel();
        _stopModernTrafficMonitoring();
        if (_ciscoTunnel.isRunning) {
          await _ciscoTunnel.stop();
        } else if (_openVpnTunnel.hasChild) {
          await _openVpnTunnel.stop();
        } else if (_l2tpTunnel.hasChild) {
          await _l2tpTunnel.stop();
        } else if (_modernTunnel.isRunning) {
          await _modernTunnel.stop();
        }
        if (_xrayProxy.isRunning) await _xrayProxy.stop();
      if (_sudokuProxy.isRunning) await _sudokuProxy.stop();
        if (!mounted) return;
        setState(() { _modernUp = false; _modernProtocol = null; _modernNodeId = null; });
      }
      // Do not clear the stored login while a managed VPN is still active.
      // Always read the native state, even if the UI appears disconnected.
      var status = await _vpn.status().timeout(const Duration(seconds: 10));
      if (status['state'] == 'unmanaged_service') {
        throw const FormatException('UNMANAGED_WIREGUARD_SERVICE');
      }
      if (status['state'] != 'down') {
        await _vpn.stop().timeout(const Duration(seconds: 20));
        status = await _vpn.status().timeout(const Duration(seconds: 10));
      }
      if (status['state'] != 'down') {
        throw const FormatException('TUNNEL_NOT_STOPPED');
      }
      if (!mounted) return;
      _resetNetworkStats();
      setState(() {
        _vpnUp = false;
        _vpnVerified = false;
        _vpnCleanup = false;
        _activeNodeId = null;
        _vpnRx = 0;
        _vpnTx = 0;
      });
      widget.onLogout();
    } catch (error) {
      if (!mounted) return;
      setState(() => _vpnError = _errorText(error));
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(tr(
          'قطع امن تونل انجام نشد؛ حساب همچنان وارد است.',
          'Could not safely disconnect; account remains signed in.',
        )),
      ));
    } finally {
      if (mounted) setState(() => _vpnBusy = false);
    }
  }

  // Check the active route periodically without restarting a functioning
  // tunnel. Two consecutive failures flag degraded routing, but do not
  // override a user's selection or unexpectedly disconnect them.
  void _stopModernTrafficMonitoring() {
    _modernTrafficTimer?.cancel();
    _modernTrafficTimer = null;
    _modernRx = null;
    _modernTx = null;
    _tunnelOriginRx = null;
    _tunnelOriginTx = null;
    _clearTrafficSamples();
  }

  Future<void> _refreshModernTraffic() async {
    if (!mounted || !_modernUp || _modernTrafficBusy) return;
    _modernTrafficBusy = true;
    try {
      final activeProtocol = _modernProtocol;
      final isCisco = activeProtocol == 'cisco';
      final isOpenVpn = activeProtocol == 'openvpn';
      final isL2tp = activeProtocol == 'l2tp';
      final totals = isCisco
          ? await _ciscoTunnel.readTrafficTotals()
          : isOpenVpn
              ? await _openVpnTunnel.readTrafficTotals()
              : isL2tp
                  ? await _l2tpTunnel.readTrafficTotals()
                  : await _modernTunnel.readTrafficTotals();
      if (!mounted || !_modernUp || totals == null ||
          activeProtocol != _modernProtocol) return;
      int rx = totals.received;
      int tx = totals.sent;
      if (isCisco || isOpenVpn || isL2tp) {
        _tunnelOriginRx ??= rx;
        _tunnelOriginTx ??= tx;
        // Show bytes transferred during this connection, not lifetime totals.
        rx = rx >= _tunnelOriginRx! ? rx - _tunnelOriginRx! : 0;
        tx = tx >= _tunnelOriginTx! ? tx - _tunnelOriginTx! : 0;
      }
      // A zero-traffic interval must report 0 B/s, not leave the last
      // nonzero speed on screen. Reuse the existing 2-second counter poll:
      // no downloads, speed tests, or per-server background probes.
      setState(() {
        _modernRx = rx;
        _modernTx = tx;
        _recordTraffic('modern:$activeProtocol', rx, tx);
      });
    } finally {
      _modernTrafficBusy = false;
    }
  }

  void _startModernTrafficMonitoring() {
    _stopModernTrafficMonitoring();
    if (!_modernUp) return;
    _refreshModernTraffic();
    _modernTrafficTimer = Timer.periodic(
      const Duration(seconds: 2), (_) => _refreshModernTraffic(),
    );
  }

  void _startModernHealthMonitoring() {
    _modernHealthTimer?.cancel();
    _modernHealthFailures = 0;
    _modernHealthTimer = Timer.periodic(const Duration(seconds: 25), (_) async {
      if (!mounted || !_modernUp || _vpnBusy || _modernHealthBusy) return;
      _modernHealthBusy = true;
      try {
        final healthy = ((_modernProtocol == 'v2ray' &&
              !_xrayProxy.isRunning) ||
              (_modernProtocol == 'sudoku' && !_sudokuProxy.isRunning))
            ? false
            : _modernProtocol == 'cisco'
            ? await _ciscoTunnel.checkHealth()
            : _modernProtocol == 'openvpn'
                ? await _openVpnTunnel.checkHealth()
                : _modernProtocol == 'l2tp'
                    ? await _l2tpTunnel.checkHealth()
                    : await _modernTunnel.checkHealth();
        if (!mounted || !_modernUp || _vpnBusy) return;
        // Losing the Cisco child or its verified egress must never leave
        // an "online" badge visible for an unverified tunnel.
        if (!healthy && _modernProtocol == 'l2tp') {
          _modernHealthFailures++;
          if (!_l2tpTunnel.isRunning || _modernHealthFailures >= 2) {
            _modernHealthTimer?.cancel();
            setState(() {
              _modernUp = false;
              _publicIp = null;
              _vpnError = _l2tpTunnel.lastHealthError ??
                  (_l2tpTunnel.hasChild
                    ? 'L2TP_HEALTH_DEGRADED' : 'L2TP_CONNECTION_FAILED');
            });
          }
          return;
        }
        if (!healthy && _modernProtocol == 'openvpn') {
          _modernHealthFailures++;
          if (!_openVpnTunnel.isRunning || _modernHealthFailures >= 2) {
            _modernHealthTimer?.cancel();
            setState(() {
              _modernUp = false;
              _publicIp = null;
              _vpnError = _openVpnTunnel.isRunning
                  ? 'OPENVPN_HEALTH_DEGRADED' : 'OPENVPN_PROCESS_EXITED';
            });
          }
          return; // OpenVPN must not fall through to sing-box diagnostics.
        }
        if (!healthy && _modernProtocol == 'cisco') {
          _modernHealthFailures++;
          if (!_ciscoTunnel.isRunning || _modernHealthFailures >= 2) {
            _modernHealthTimer?.cancel();
            setState(() {
              _modernUp = false;
              _publicIp = null;
              _vpnError = _ciscoTunnel.isRunning
                  ? 'CISCO_HEALTH_DEGRADED' : 'CISCO_PROCESS_EXITED';
            });
            return;
          }
        }
        if (healthy) {
          _modernHealthFailures = 0;
          if (_vpnError == 'SINGBOX_TUN_HEALTH_DEGRADED') {
            setState(() => _vpnError = null);
          }
        } else {
          _modernHealthFailures++;
          if (_modernHealthFailures >= 2 &&
              _vpnError != 'SINGBOX_TUN_HEALTH_DEGRADED') {
            setState(() => _vpnError = 'SINGBOX_TUN_HEALTH_DEGRADED');
          }
        }
      } finally {
        _modernHealthBusy = false;
      }
    });
  }

  // Only a fresh connection with NO existing Windows VPN can overlap the
  // DIRECT pre-TUN IP snapshot with authorized profile delivery. During a
  // protocol switch the baseline MUST be sampled after old routes are gone.
  bool get _canPrefetchDirectBaseline =>
      !_vpnUp && !_vpnCleanup && !_vpnUnmanaged && !_modernUp &&
      !_modernTunnel.isRunning && !_xrayProxy.isRunning && !_sudokuProxy.isRunning &&
      !_ciscoTunnel.isRunning && !_openVpnTunnel.hasChild &&
      !_l2tpTunnel.hasChild;

  Future<({ClientProtocolProfiles profiles, String? baselineIp})>
      _loadNativeProfilesWithBaseline({
    required VpnProtocolDefinition definition,
    required Future<String> Function() directIp,
  }) async {
    final api = TenantApi.fromBuildConfig();
    Future<ClientProtocolProfiles> load() => api.loadSessionNativeProfiles(
      panel: widget.panel, sessionToken: widget.sessionToken,
      protocol: definition,
      native: NativeProtocolReadiness(
        supportedCodes: {definition.code},
      ),
    );
    if (!_canPrefetchDirectBaseline) {
      return (profiles: await load(), baselineIp: null);
    }
    // The sample records its OWN completion time; a slow panel response
    // cannot cause an old baseline to be reused after 8 seconds.
    final both = await Future.wait<Object>([
      load(),
      directIp().then((ip) => (ip: ip, measuredAt: DateTime.now())),
    ]);
    final sample = both[1] as ({String ip, DateTime measuredAt});
    final fresh = DateTime.now().difference(sample.measuredAt) <
        const Duration(seconds: 8);
    return (profiles: both[0] as ClientProtocolProfiles,
            baselineIp: fresh ? sample.ip : null);
  }

  Future<void> _startCiscoTunnel(String serverId) async {
    if (_vpnBusy) return;
    setState(() { _vpnBusy = true; _vpnError = null; });
    try {
      if (_vpnUnmanaged) {
        throw const FormatException('UNMANAGED_WIREGUARD_SERVICE');
      }
      final authorized = widget.catalog?.entries.any((entry) =>
          entry.protocol.code == 'cisco' && entry.selected &&
          entry.configRecordPresent) ?? false;
      if (!authorized) {
        throw const FormatException('PROTOCOL_NOT_INCLUDED_IN_SUBSCRIPTION');
      }
      if (!await WindowsOpenConnectTunnel.enginePresent()) {
        throw const FormatException('CISCO_ENGINE_UNAVAILABLE');
      }
      final definition = VpnProtocols.byCode('cisco')!;
      final prepared = await _loadNativeProfilesWithBaseline(
        definition: definition,
        directIp: WindowsOpenConnectTunnel.directPublicIp,
      );
      final profiles = prepared.profiles;
      final matches = profiles.items.where((item) =>
          item['node_id']?.toString() == serverId).toList(growable: false);
      if (matches.length != 1) {
        throw const FormatException('CISCO_SERVER_PROFILE_MISSING');
      }
      // Validate the replacement credentials before disconnecting any VPN.
      final target = CiscoOpenConnectProfile.fromItem(matches.single);
      if (_vpnUp || _vpnCleanup) {
        await _vpn.stop().timeout(const Duration(seconds: 20));
        final stopped = await _vpn.status().timeout(
            const Duration(seconds: 10));
        if (stopped['state'] != 'down') {
          throw const FormatException('PREVIOUS_TUNNEL_NOT_STOPPED');
        }
        if (!mounted) return;
        setState(() {
          _vpnUp = false;
          _vpnVerified = false;
          _vpnCleanup = false;
          _activeNodeId = null;
          _vpnRx = 0;
          _vpnTx = 0;
          _resetNetworkStats();
        });
      }
      if (_modernTunnel.isRunning || _xrayProxy.isRunning || _sudokuProxy.isRunning ||
          _ciscoTunnel.isRunning ||
          _openVpnTunnel.hasChild || _l2tpTunnel.hasChild) {
        _modernHealthTimer?.cancel();
        _stopModernTrafficMonitoring();
        if (_ciscoTunnel.isRunning) {
          await _ciscoTunnel.stop();
        } else if (_openVpnTunnel.hasChild) {
          await _openVpnTunnel.stop();
        } else if (_l2tpTunnel.hasChild) {
          await _l2tpTunnel.stop();
        } else {
          await _modernTunnel.stop();
        }
        if (_xrayProxy.isRunning) await _xrayProxy.stop();
      if (_sudokuProxy.isRunning) await _sudokuProxy.stop();
        if (!mounted) return;
        setState(() {
          _modernUp = false;
          _modernProtocol = null;
          _modernNodeId = null;
          _publicIp = null;
        });
      }
      final verifiedIp = await _ciscoTunnel.start(target,
          baselinePublicIp: prepared.baselineIp);
      if (!mounted) return;
      setState(() {
        _modernUp = true;
        _modernProtocol = 'cisco';
        _modernNodeId = serverId;
        _publicIp = verifiedIp;
        _vpnError = null;
      });
      _startModernTrafficMonitoring();
      _startModernHealthMonitoring();
    } catch (error) {
      if (mounted) {
        setState(() {
          _modernUp = (_ciscoTunnel.isRunning &&
                  _ciscoTunnel.exitIp != null) || _modernTunnel.isRunning;
          if (!_modernUp) {
            _modernProtocol = null;
            _modernNodeId = null;
            _publicIp = null;
          }
          _vpnError = _errorText(error);
        });
      }
    } finally {
      if (mounted) setState(() => _vpnBusy = false);
    }
  }

  Future<void> _startOpenVpnTunnel(String serverId) async {
    if (_vpnBusy) return;
    setState(() { _vpnBusy = true; _vpnError = null; });
    try {
      if (_vpnUnmanaged) {
        throw const FormatException('UNMANAGED_WIREGUARD_SERVICE');
      }
      final authorized = widget.catalog?.entries.any((entry) =>
          entry.protocol.code == 'openvpn' && entry.selected &&
          entry.configRecordPresent) ?? false;
      if (!authorized) {
        throw const FormatException('PROTOCOL_NOT_INCLUDED_IN_SUBSCRIPTION');
      }
      if (!await WindowsOpenVpnTunnel.enginePresent()) {
        throw const FormatException('OPENVPN_ENGINE_NOT_INSTALLED');
      }
      final definition = VpnProtocols.byCode('openvpn')!;
      final prepared = await _loadNativeProfilesWithBaseline(
        definition: definition,
        directIp: WindowsOpenVpnTunnel.publicIp,
      );
      final profiles = prepared.profiles;
      final matches = profiles.items.where((item) =>
          item['node_id']?.toString() == serverId).toList(growable: false);
      if (matches.length != 1) {
        throw const FormatException('OPENVPN_SERVER_PROFILE_MISSING');
      }
      // Validate the replacement credentials before disconnecting any VPN.
      OpenVpnProfileValidator.validate(matches.single);
      final target = matches.single;
      if (_vpnUp || _vpnCleanup) {
        await _vpn.stop().timeout(const Duration(seconds: 20));
        final stopped = await _vpn.status().timeout(
            const Duration(seconds: 10));
        if (stopped['state'] != 'down') {
          throw const FormatException('PREVIOUS_TUNNEL_NOT_STOPPED');
        }
        if (!mounted) return;
        setState(() {
          _vpnUp = false;
          _vpnVerified = false;
          _vpnCleanup = false;
          _activeNodeId = null;
          _vpnRx = 0;
          _vpnTx = 0;
          _resetNetworkStats();
        });
      }
      if (_modernTunnel.isRunning || _xrayProxy.isRunning || _sudokuProxy.isRunning ||
          _ciscoTunnel.isRunning ||
          _openVpnTunnel.hasChild || _l2tpTunnel.hasChild) {
        _modernHealthTimer?.cancel();
        _stopModernTrafficMonitoring();
        if (_ciscoTunnel.isRunning) {
          await _ciscoTunnel.stop();
        } else if (_openVpnTunnel.hasChild) {
          await _openVpnTunnel.stop();
        } else if (_l2tpTunnel.hasChild) {
          await _l2tpTunnel.stop();
        } else {
          await _modernTunnel.stop();
        }
        if (_xrayProxy.isRunning) await _xrayProxy.stop();
      if (_sudokuProxy.isRunning) await _sudokuProxy.stop();
        if (!mounted) return;
        setState(() {
          _modernUp = false;
          _modernProtocol = null;
          _modernNodeId = null;
          _publicIp = null;
        });
      }
      final verifiedIp = await _openVpnTunnel.start(target,
          baselinePublicIp: prepared.baselineIp);
      if (!mounted) return;
      setState(() {
        _modernUp = true;
        _modernProtocol = 'openvpn';
        _modernNodeId = serverId;
        _publicIp = verifiedIp;
        _vpnError = null;
      });
      _startModernTrafficMonitoring();
      _startModernHealthMonitoring();
    } catch (error) {
      if (mounted) {
        setState(() {
          _modernUp = (_openVpnTunnel.isRunning &&
                  _openVpnTunnel.exitIp != null) ||
              _ciscoTunnel.isRunning || _modernTunnel.isRunning;
          if (!_modernUp) {
            _modernProtocol = null;
            _modernNodeId = null;
            _publicIp = null;
          }
          _vpnError = _errorText(error);
        });
      }
    } finally {
      if (mounted) setState(() => _vpnBusy = false);
    }
  }

  Future<void> _startL2tpTunnel(String serverId) async {
    if (_vpnBusy) return;
    setState(() { _vpnBusy = true; _vpnError = null; });
    try {
      if (_vpnUnmanaged) {
        throw const FormatException('UNMANAGED_WIREGUARD_SERVICE');
      }
      final authorized = widget.catalog?.entries.any((entry) =>
          entry.protocol.code == 'l2tp' && entry.selected &&
          entry.configRecordPresent) ?? false;
      if (!authorized) {
        throw const FormatException('PROTOCOL_NOT_INCLUDED_IN_SUBSCRIPTION');
      }
      final definition = VpnProtocols.byCode('l2tp')!;
      final prepared = await _loadNativeProfilesWithBaseline(
        definition: definition,
        directIp: WindowsL2tpTunnel.directPublicIp,
      );
      final profiles = prepared.profiles;
      final matches = profiles.items.where((item) =>
          item['node_id']?.toString() == serverId).toList(growable: false);
      if (matches.length != 1) {
        throw const FormatException('L2TP_SERVER_PROFILE_MISSING');
      }
      // Validate the replacement credentials before disconnecting any VPN.
      final target = L2tpProfile.fromItem(matches.single);
      if (_vpnUp || _vpnCleanup) {
        await _vpn.stop().timeout(const Duration(seconds: 20));
        final stopped = await _vpn.status().timeout(
            const Duration(seconds: 10));
        if (stopped['state'] != 'down') {
          throw const FormatException('PREVIOUS_TUNNEL_NOT_STOPPED');
        }
        if (!mounted) return;
        setState(() {
          _vpnUp = false;
          _vpnVerified = false;
          _vpnCleanup = false;
          _activeNodeId = null;
          _vpnRx = 0;
          _vpnTx = 0;
          _resetNetworkStats();
        });
      }
      if (_modernTunnel.isRunning || _xrayProxy.isRunning || _sudokuProxy.isRunning ||
          _ciscoTunnel.isRunning ||
          _openVpnTunnel.hasChild || _l2tpTunnel.hasChild) {
        _modernHealthTimer?.cancel();
        _stopModernTrafficMonitoring();
        if (_ciscoTunnel.isRunning) {
          await _ciscoTunnel.stop();
        } else if (_openVpnTunnel.hasChild) {
          await _openVpnTunnel.stop();
        } else if (_l2tpTunnel.hasChild) {
          await _l2tpTunnel.stop();
        } else {
          await _modernTunnel.stop();
        }
        if (_xrayProxy.isRunning) await _xrayProxy.stop();
      if (_sudokuProxy.isRunning) await _sudokuProxy.stop();
        if (!mounted) return;
        setState(() {
          _modernUp = false;
          _modernProtocol = null;
          _modernNodeId = null;
          _publicIp = null;
        });
      }
      final verifiedIp = await _l2tpTunnel.start(target,
          baselinePublicIp: prepared.baselineIp);
      if (!mounted) return;
      setState(() {
        _modernUp = true;
        _modernProtocol = 'l2tp';
        _modernNodeId = serverId;
        _publicIp = verifiedIp;
        _vpnError = null;
      });
      _startModernTrafficMonitoring();
      _startModernHealthMonitoring();
    } catch (error) {
      if (mounted) {
        setState(() {
          _modernUp = (_l2tpTunnel.isRunning &&
                  _l2tpTunnel.exitIp != null) ||
              _openVpnTunnel.isRunning ||
              _ciscoTunnel.isRunning || _modernTunnel.isRunning;
          if (!_modernUp) {
            _modernProtocol = null;
            _modernNodeId = null;
            _publicIp = null;
          }
          _vpnError = _errorText(error);
        });
      }
    } finally {
      if (mounted) setState(() => _vpnBusy = false);
    }
  }

  Future<void> _startXrayTunnel(String serverId, {String? inboundId}) async {
    if (_vpnBusy || !Platform.isWindows) return;
    setState(() { _vpnBusy = true; _vpnError = null; });
    try {
      if (_vpnUnmanaged || _vpnCleanup) {
        throw const FormatException('PREVIOUS_TUNNEL_NOT_STOPPED');
      }
      final authorized = widget.catalog?.entries.any((entry) =>
          entry.protocol.code == 'v2ray' && entry.selected &&
          entry.configRecordPresent) ?? false;
      if (!authorized) {
        throw const FormatException('PROTOCOL_NOT_INCLUDED_IN_SUBSCRIPTION');
      }
      // Both native binaries are checked independently. Parallel probing
      // removes a redundant serial subprocess wait on cold Windows startup.
      final engines = await Future.wait<bool>([
        WindowsXrayPreflight.enginePresent(),
        WindowsSingBoxPreflight.enginePresent(),
      ]);
      if (!engines[0] || !engines[1]) {
        throw const FormatException('XRAY_OR_TUN_ENGINE_UNAVAILABLE');
      }
      final definition = VpnProtocols.byCode('v2ray')!;
      final response = await TenantApi.fromBuildConfig()
          .loadSessionNativeProfiles(
        panel: widget.panel,
        sessionToken: widget.sessionToken,
        protocol: definition,
        native: const NativeProtocolReadiness(supportedCodes: {'v2ray'}),
      );
      final matches = response.xrayServerGroups
          .where((group) => group.serverId == serverId)
          .expand((group) => group.inbounds)
          .toList(growable: false);
      if (matches.isEmpty) {
        throw const FormatException('XRAY_SERVER_PROFILES_MISSING');
      }
      // Each inbound is a separate server-list choice. Never interrupt the
      // user's connection to show a second selection dialog.
      final requestedInboundId = inboundId ??
          (_selectedXrayNodeId == serverId ? _selectedXrayInboundId : null);
      final eligible = requestedInboundId == null
          ? matches
          : matches.where((item) => item.id == requestedInboundId)
              .toList(growable: false);
      if (eligible.isEmpty) {
        throw const FormatException('XRAY_INBOUND_NOT_AVAILABLE');
      }
      // Legacy Quick Connect (before choosing a specific inbound) uses the
      // first *real* profile from the panel, never a synthetic transport.
      final chosen = eligible.first;
      if (!mounted) return;

      // Prepare and validate the subscription-scoped Xray endpoint BEFORE
      // changing any Windows routes or interrupting an existing tunnel.
      // An existing Xray bridge is stopped only after the replacement was
      // selected; no stale profile or node address is reused.
      if (_modernTunnel.isRunning) await _modernTunnel.stop();
      if (_xrayProxy.isRunning) await _xrayProxy.stop();
      if (_sudokuProxy.isRunning) await _sudokuProxy.stop();
      if (_ciscoTunnel.isRunning) await _ciscoTunnel.stop();
      if (_openVpnTunnel.hasChild) await _openVpnTunnel.stop();
      if (_l2tpTunnel.hasChild) await _l2tpTunnel.stop();
      if (_vpnUp || _vpnCleanup) {
        await _vpn.stop().timeout(const Duration(seconds: 20));
        final status = await _vpn.status().timeout(
          const Duration(seconds: 10));
        if (status['state'] != 'down') {
          throw const FormatException('PREVIOUS_TUNNEL_NOT_STOPPED');
        }
        if (mounted) setState(() {
          _vpnUp = false;
          _vpnVerified = false;
          _vpnCleanup = false;
          _activeNodeId = null;
          _vpnRx = 0;
          _vpnTx = 0;
          _resetNetworkStats();
        });
      }
      _modernHealthTimer?.cancel();
      _stopModernTrafficMonitoring();
      if (mounted) setState(() {
        _modernUp = false;
        _modernProtocol = null;
        _modernNodeId = null;
        _publicIp = null;
      });

      // Remote Xray verification and the DIRECT pre-TUN public-IP
      // baseline do not depend on each other. Run both at once rather than
      // adding two separate internet round trips to every connection.
      // Neither result claims VPN connectivity until the TUN is verified.
      final preTunnel = await Future.wait<Object>([
        _xrayProxy.start(chosen),
        WindowsSingBoxTunnel.measureBaselineIp(),
      ]);
      final socksPort = preTunnel[0] as int;
      final baselineIp = preTunnel[1] as String;
      final verifiedExit = _xrayProxy.verifiedExitIp;
      final pinnedEndpointIPv4 = _xrayProxy.pinnedServerIPv4;
      if (verifiedExit == null || pinnedEndpointIPv4 == null) {
        throw const FormatException('XRAY_REMOTE_EGRESS_NOT_VERIFIED');
      }
      // The existing Windows sing-box TUN remains responsible for routing,
      // DNS isolation, and an independent post-route public IP verification.
      final publicIp = await _modernTunnel.start(
        protocol: 'v2ray',
        serverId: serverId,
        profile: const <String, dynamic>{},
        xraySocksPort: socksPort,
        xrayVerifiedExitIp: verifiedExit,
        xrayEndpointIPv4: pinnedEndpointIPv4,
        baselinePublicIp: baselineIp,
      );
      if (!mounted) return;
      setState(() {
        _modernUp = true;
        _modernProtocol = 'v2ray';
        _modernNodeId = serverId;
        _selectedXrayNodeId = serverId;
        _selectedXrayInboundId = chosen.id;
        _publicIp = publicIp;
        _vpnError = null;
      });
      _startModernTrafficMonitoring();
      _startModernHealthMonitoring();
    } catch (error) {
      // Never leave a local Xray upstream alive without its verified TUN.
      if (_xrayProxy.isRunning && !_modernTunnel.isRunning) {
        try { await _xrayProxy.stop(); } catch (_) {}
      }
      if (mounted) setState(() {
        _modernUp = _modernTunnel.isRunning ||
            _ciscoTunnel.isRunning ||
            _openVpnTunnel.isRunning ||
            _l2tpTunnel.isRunning;
        if (!_modernUp) {
          _modernProtocol = null;
          _modernNodeId = null;
          _publicIp = null;
        }
        _vpnError = _errorText(error);
      });
    } finally {
      if (mounted) setState(() => _vpnBusy = false);
    }
  }

  Future<void> _startSudokuTunnel(String serverId) async {
    if (_vpnBusy || !Platform.isWindows) return;
    setState(() { _vpnBusy = true; _vpnError = null; });
    try {
      if (_vpnUnmanaged || _vpnCleanup) {
        throw const FormatException('PREVIOUS_TUNNEL_NOT_STOPPED');
      }
      final authorized = widget.catalog?.entries.any((entry) =>
          entry.protocol.code == 'sudoku' && entry.selected &&
          entry.configRecordPresent) ?? false;
      if (!authorized) {
        throw const FormatException('PROTOCOL_NOT_INCLUDED_IN_SUBSCRIPTION');
      }
      final ready = await Future.wait<bool>([
        WindowsSudokuProxy.enginePresent(),
        WindowsSingBoxPreflight.enginePresent(),
      ]);
      if (!ready[0] || !ready[1]) {
        throw const FormatException('SUDOKU_OR_TUN_ENGINE_UNAVAILABLE');
      }
      final profiles = await TenantApi.fromBuildConfig()
          .loadSessionNativeProfiles(
        panel: widget.panel,
        sessionToken: widget.sessionToken,
        protocol: VpnProtocols.byCode('sudoku')!,
        native: const NativeProtocolReadiness(supportedCodes: {'sudoku'}),
      );
      final profile = SudokuClientProfile.resolveDeliveredProfile(
        requestedNodeId: serverId,
        items: profiles.items,
        inventory: widget.servers,
      );
      if (profile == null) {
        throw const FormatException('SUDOKU_SERVER_PROFILE_MISSING');
      }
      // An old displayed Exit can lack a central Sudoku identity while a
      // verified same-country Exit is deliverable. Report the actual node.
      final resolvedServerId = profile.nodeId;
      final fallbackIndex = widget.servers?.servers.indexWhere(
          (server) => server.id == resolvedServerId) ?? -1;
      // Delivery and native engine validation happen BEFORE touching a
      // running VPN. Never leave two active TUN devices or core processes.
      if (_modernTunnel.isRunning) await _modernTunnel.stop();
      if (_xrayProxy.isRunning) await _xrayProxy.stop();
      if (_sudokuProxy.isRunning) await _sudokuProxy.stop();
      if (_ciscoTunnel.isRunning) await _ciscoTunnel.stop();
      if (_openVpnTunnel.hasChild) await _openVpnTunnel.stop();
      if (_l2tpTunnel.hasChild) await _l2tpTunnel.stop();
      if (_vpnUp || _vpnCleanup) {
        await _vpn.stop().timeout(const Duration(seconds: 20));
        final status = await _vpn.status()
            .timeout(const Duration(seconds: 10));
        if (status['state'] != 'down') {
          throw const FormatException('PREVIOUS_TUNNEL_NOT_STOPPED');
        }
        if (mounted) setState(() {
          _vpnUp = false;
          _vpnVerified = false;
          _vpnCleanup = false;
          _activeNodeId = null;
          _vpnRx = 0;
          _vpnTx = 0;
          _resetNetworkStats();
        });
      }
      _modernHealthTimer?.cancel();
      _stopModernTrafficMonitoring();
      if (mounted) setState(() {
        _modernUp = false;
        _modernProtocol = null;
        _modernNodeId = null;
        _publicIp = null;
      });

      // The Sudoku core performs its own authenticated Sudoku handshake.
      // In parallel, get a DIRECT pre-TUN public-IP baseline. Both are
      // required before sing-box is allowed to modify Windows routes.
      final preTunnel = await Future.wait<Object>([
        _sudokuProxy.start(profile),
        WindowsSingBoxTunnel.measureBaselineIp().timeout(
          const Duration(seconds: 9),
          onTimeout: () =>
              throw const FormatException('SUDOKU_BASELINE_IP_TIMEOUT'),
        ),
      ]);
      final socksPort = preTunnel[0] as int;
      final baselineIp = preTunnel[1] as String;
      final verifiedExit = _sudokuProxy.verifiedExitIp;
      final endpoint = _sudokuProxy.endpointIpv4;
      if (verifiedExit == null || endpoint == null) {
        throw const FormatException('SUDOKU_REMOTE_EGRESS_UNVERIFIED');
      }
      final ip = await _modernTunnel.start(
        protocol: 'sudoku',
        serverId: resolvedServerId,
        profile: const <String, dynamic>{},
        sudokuSocksPort: socksPort,
        sudokuVerifiedExitIp: verifiedExit,
        sudokuEndpointIPv4: endpoint,
        baselinePublicIp: baselineIp,
      );
      if (!mounted) return;
      setState(() {
        _modernUp = true;
        _modernProtocol = 'sudoku';
        _modernNodeId = resolvedServerId;
        if (fallbackIndex >= 0) _selected = fallbackIndex;
        _publicIp = ip;
        _vpnError = null;
      });
      _startModernTrafficMonitoring();
      _startModernHealthMonitoring();
    } catch (error) {
      if (_sudokuProxy.isRunning && !_modernTunnel.isRunning) {
        try { await _sudokuProxy.stop(); } catch (_) {}
      }
      if (mounted) setState(() {
        _modernUp = _modernTunnel.isRunning ||
            _ciscoTunnel.isRunning ||
            _openVpnTunnel.isRunning ||
            _l2tpTunnel.isRunning;
        if (!_modernUp) {
          _modernProtocol = null;
          _modernNodeId = null;
          _publicIp = null;
        }
        _vpnError = _errorText(error);
      });
    } finally {
      if (mounted) setState(() => _vpnBusy = false);
    }
  }

  Future<void> _startModernTunnel(String protocol, String serverId) async {
    if (_vpnBusy) return;
    setState(() { _vpnBusy = true; _vpnError = null; });
    try {
      if (_vpnUnmanaged) {
        throw const FormatException('UNMANAGED_WIREGUARD_SERVICE');
      }
      final authorized = widget.catalog?.entries.any((entry) =>
          entry.protocol.code == protocol && entry.selected &&
          entry.configRecordPresent) ?? false;
      if (!authorized) {
        throw const FormatException('PROTOCOL_NOT_INCLUDED_IN_SUBSCRIPTION');
      }
      final definition = VpnProtocols.byCode(protocol);
      if (definition == null ||
          !SingBoxProfileValidator.supportsFamily(protocol)) {
        throw const FormatException('SINGBOX_PROTOCOL_NOT_SUPPORTED');
      }
      if (!await WindowsSingBoxPreflight.enginePresent()) {
        throw const FormatException('SINGBOX_ENGINE_UNAVAILABLE');
      }
      final profiles = await TenantApi.fromBuildConfig().loadSessionNativeProfiles(
        panel: widget.panel,
        sessionToken: widget.sessionToken,
        protocol: definition,
        native: NativeProtocolReadiness(supportedCodes: {protocol}),
      );
      final matches = profiles.items.where((item) =>
          item['node_id']?.toString() == serverId).toList(growable: false);
      if (matches.length != 1) {
        throw const FormatException('MODERN_SERVER_PROFILE_MISSING');
      }
      // ShadowTLS cannot be flattened into one outbound: validate the
      // subscription's two-stage Shadowsocks -> ShadowTLS chain before
      // stopping any existing connection. Other protocols are unchanged.
      if (protocol == 'shadowtls') {
        ShadowTlsChain.fromItem(matches.single);
      }
      // When switching away from a working VPN, validate before stopping
      // it. For a fresh connect the tunnel controller performs the exact
      // same native config validation; avoid starting sing-box twice.
      if (_vpnUp || _vpnCleanup || _modernTunnel.isRunning ||
          _ciscoTunnel.isRunning || _openVpnTunnel.hasChild ||
          _l2tpTunnel.hasChild) {
        final targetConfig = SingBoxWindowsConfig.compose(
            protocol: protocol, item: matches.single);
        if (!await WindowsSingBoxPreflight.checkInMemory(targetConfig)) {
          throw const FormatException('SINGBOX_TUN_CONFIG_INVALID');
        }
      }
      if (_vpnUp || _vpnCleanup) {
        await _vpn.stop().timeout(const Duration(seconds: 20));
        final stopped = await _vpn.status().timeout(
          const Duration(seconds: 10));
        if (stopped['state'] != 'down') {
          throw const FormatException('PREVIOUS_TUNNEL_NOT_STOPPED');
        }
        if (!mounted) return;
        setState(() {
          _vpnUp = false;
          _vpnVerified = false;
          _vpnCleanup = false;
          _activeNodeId = null;
          _vpnRx = 0;
          _vpnTx = 0;
          _resetNetworkStats();
        });
      }
      if (_modernTunnel.isRunning || _xrayProxy.isRunning || _sudokuProxy.isRunning ||
          _ciscoTunnel.isRunning ||
          _openVpnTunnel.hasChild || _l2tpTunnel.hasChild) {
        _modernHealthTimer?.cancel();
        _stopModernTrafficMonitoring();
        if (_ciscoTunnel.isRunning) {
          await _ciscoTunnel.stop();
        } else if (_openVpnTunnel.hasChild) {
          await _openVpnTunnel.stop();
        } else if (_l2tpTunnel.hasChild) {
          await _l2tpTunnel.stop();
        } else {
          await _modernTunnel.stop();
        }
        if (_xrayProxy.isRunning) await _xrayProxy.stop();
      if (_sudokuProxy.isRunning) await _sudokuProxy.stop();
        if (!mounted) return;
        setState(() {
          _modernUp = false;
          _publicIp = null;
        });
      }
      final newIp = await _modernTunnel.start(
        protocol: protocol, serverId: serverId, profile: matches.single);
      if (!mounted) return;
      setState(() {
        _modernUp = true;
        _modernProtocol = protocol;
        _modernNodeId = serverId;
        _publicIp = newIp;
        _vpnError = null;
      });
      _startModernTrafficMonitoring();
      _startModernHealthMonitoring();
    } catch (error) {
      if (mounted) {
        setState(() {
          _modernUp = _modernTunnel.isRunning ||
              _ciscoTunnel.isRunning ||
              _openVpnTunnel.isRunning ||
              _l2tpTunnel.isRunning;
          if (!_modernUp) {
            _modernProtocol = null;
            _modernNodeId = null;
          }
          _vpnError = _errorText(error);
        });
      }
    } finally {
      if (mounted) setState(() => _vpnBusy = false);
    }
  }

  Future<void> _stopModernTunnel() async {
    if (_vpnBusy) return;
    _modernHealthTimer?.cancel();
    _stopModernTrafficMonitoring();
    setState(() { _vpnBusy = true; _vpnError = null; });
    try {
      if (_ciscoTunnel.isRunning) {
        await _ciscoTunnel.stop();
      } else if (_openVpnTunnel.hasChild) {
        await _openVpnTunnel.stop();
      } else if (_l2tpTunnel.hasChild) {
        await _l2tpTunnel.stop();
      } else if (_modernTunnel.isRunning) {
        await _modernTunnel.stop();
      }
      if (_xrayProxy.isRunning) await _xrayProxy.stop();
      if (_sudokuProxy.isRunning) await _sudokuProxy.stop();
      if (!mounted) return;
      setState(() {
        _modernUp = false;
        _modernProtocol = null;
        _modernNodeId = null;
        _publicIp = null;
      });
    } catch (error) {
      if (mounted) {
        setState(() {
          if (_modernProtocol == 'cisco' && !_ciscoTunnel.isRunning) {
            _modernUp = false;
            _publicIp = null;
            _modernNodeId = null;
            _modernProtocol = null;
          }
          _vpnError = _errorText(error);
        });
      }
    } finally {
      if (mounted) setState(() => _vpnBusy = false);
    }
  }

  Future<void> _selectServerAndConnect(int index) async {
    final nodes = widget.servers?.servers;
    if (nodes == null || index < 0 || index >= nodes.length) {
      if (mounted) setState(() => _vpnError = 'SERVER_NOT_AVAILABLE');
      return;
    }
    // Selection is a UI operation, never dependent on a protocol engine,
    // subscription profile, or an in-flight transport diagnostic.
    final busy = _vpnBusy;
    setState(() {
      _selected = index;
      _page = 'home';
      _autoFastest = false;
      if (!busy) _vpnError = null;
    });
    if (busy) {
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(SnackBar(
        content: Text(tr('سرور انتخاب شد؛ عملیات قبلی هنوز در حال اجراست.',
            'Server selected; previous connection operation is still running.'))));
      return;
    }
    if (!Platform.isWindows) {
      setState(() => _vpnError = 'WINDOWS_ENGINE_REQUIRED');
      return;
    }
    if (_filter != 'all' && _filter != 'wireguard') {
      // Selecting a node when disconnected only changes the selection.
      // While a modern tunnel is connected, switching nodes triggers
      // a verified handoff, after validating the replacement profile.
      if (_modernUp &&
          (_modernNodeId != nodes[index].id || _modernProtocol != _filter)) {
        if (_filter == 'cisco') {
          await _startCiscoTunnel(nodes[index].id);
        } else if (_filter == 'openvpn') {
          await _startOpenVpnTunnel(nodes[index].id);
        } else if (_filter == 'l2tp') {
          await _startL2tpTunnel(nodes[index].id);
        } else if (_filter == 'v2ray') {
          await _startXrayTunnel(nodes[index].id);
        } else if (_filter == 'sudoku') {
          await _startSudokuTunnel(nodes[index].id);
        } else if (SingBoxProfileValidator.supportsFamily(_filter)) {
          await _startModernTunnel(_filter, nodes[index].id);
        }

      }
      return;
    }
    final targetId = nodes[index].id;
    if (_vpnUp && _activeNodeId == targetId && !_modernUp) {
      setState(() { _selected = index; _page = 'home'; });
      return;
    }
    if (_vpnUnmanaged) {
      setState(() => _vpnError = 'UNMANAGED_WIREGUARD_SERVICE');
      return;
    }
    if (!_vpnReady || !_wireGuardAllowed) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(tr('موتور WireGuard یا دسترسی اشتراک آماده نیست.',
            'WireGuard engine or subscription access is unavailable.'))));
      setState(() => _vpnError = !_wireGuardAllowed
          ? 'WIREGUARD_NOT_ALLOWED'
          : 'WIREGUARD_NOT_INSTALLED_OR_ADMIN_REQUIRED');
      return;
    }

    // Validate the target and obtain only its authorized profile BEFORE
    // removing the working tunnel. A failed preflight keeps it running.
    setState(() { _vpnBusy = true; _vpnError = null; });
    try {
      final api = TenantApi.fromBuildConfig();
      final checks = await Future.wait<Object>([
        _vpnPolicy.load(widget.panel.namespace, widget.username),
        NativeVpnBridge.probe(),
        // The same fresh authenticated catalog is reused by bootstrap.
        // No extra catalog request is made after native readiness.
        api.loadSessionProtocolCatalog(
          panel: widget.panel, sessionToken: widget.sessionToken),
      ]);
      final policy = checks[0] as VpnPolicy;
      final capabilities = checks[1] as NativeVpnCapabilities;
      final native = await NativeVpnBridge.protocolReadiness(
        validatedCapabilities: capabilities,
      );
      final candidate = await ConnectionBootstrap(api: api).prepare(
        panel: widget.panel,
        sessionToken: widget.sessionToken,
        serverId: targetId,
        protocolCode: 'wireguard',
        policy: policy,
        capabilities: capabilities,
        nativeProtocols: native,
        currentAttemptCatalog: Future<PanelProtocolCatalog>.value(
            checks[2] as PanelProtocolCatalog),
      );
      final node = WindowsWireGuardController.configForSingleNode(
          candidate.profiles, targetId);
      if (!mounted) return;

      if (_modernTunnel.isRunning || _xrayProxy.isRunning || _sudokuProxy.isRunning ||
          _ciscoTunnel.isRunning ||
          _openVpnTunnel.hasChild || _l2tpTunnel.hasChild || _modernUp) {
        _stopModernTrafficMonitoring();
        if (_ciscoTunnel.isRunning) {
          await _ciscoTunnel.stop();
        } else if (_openVpnTunnel.hasChild) {
          await _openVpnTunnel.stop();
        } else if (_l2tpTunnel.hasChild) {
          await _l2tpTunnel.stop();
        } else if (_modernTunnel.isRunning) {
          await _modernTunnel.stop();
        }
        if (_xrayProxy.isRunning) await _xrayProxy.stop();
      if (_sudokuProxy.isRunning) await _sudokuProxy.stop();
        if (!mounted) return;
        setState(() {
          _modernUp = false;
          _modernProtocol = null;
          _modernNodeId = null;
          _publicIp = null;
        });
      }
      if (_vpnUp || _vpnCleanup) {
        await _vpn.stop();
        if (!mounted) return;
        // Never start a second tunnel until the native bridge confirms down.
        final stopped = await _vpn.status();
        if (stopped['state'] != 'down') {
          throw const FormatException('PREVIOUS_TUNNEL_NOT_STOPPED');
        }
        setState(() {
          _vpnUp = false;
          _vpnVerified = false;
          _vpnCleanup = false;
          _vpnRx = 0;
          _vpnTx = 0;
          _activeNodeId = null;
          _resetNetworkStats();
        });
      }
      final started = await _vpn.start(
        node: node,
        policy: policy,
        capabilities: capabilities,
        nativeProtocols: native,
      );
      if (!mounted) return;
      setState(() {
        _selected = index;
        _filter = 'wireguard';
        _autoFastest = false;
        _page = 'home';
        _vpnUp = started['state'] == 'interface_up' ||
            started['state'] == 'peer_verified';
        _vpnVerified = started['state'] == 'peer_verified' &&
            started['peerHandshakeVerified'] == true;
        _vpnRx = started['rxBytes'] is int ? started['rxBytes'] as int : 0;
        _vpnTx = started['txBytes'] is int ? started['txBytes'] as int : 0;
        _activeNodeId = targetId;
      });
      if (_vpnUp) _startNetworkStats();
    } catch (error) {
      if (mounted) setState(() => _vpnError = _errorText(error));
    } finally {
      if (mounted) setState(() => _vpnBusy = false);
    }
  }

  @override
  void dispose() {
    _durationTicker?.cancel();
    _connectedSeconds.dispose();
    _modernHealthTimer?.cancel();
    _stopModernTrafficMonitoring();
    _modernTunnel.dispose();
    _xrayProxy.dispose();
    _sudokuProxy.dispose();
    _resetNetworkStats();
    super.dispose();
  }


  bool get _wireGuardAllowed => widget.catalog?.entries.any((entry) =>
      entry.protocol.code == 'wireguard' && entry.selected &&
      entry.configRecordPresent) ?? false;

  String? get _selectedServerId {
    final servers = widget.servers?.servers;
    if (servers == null || servers.isEmpty || _selected < 0 ||
        _selected >= servers.length) { return null; }
    return servers[_selected].id;
  }

  String _errorText(Object error) {
    if (error is PlatformException) return error.code;
    if (error is TenantApiException) return error.message;
    if (error is ConnectionBootstrapException) return error.code;
    if (error is FormatException) return error.message;
    // Only display error categories; OS exception messages may contain local
    // paths, server addresses, or other secret-bearing process arguments.
    if (error is ProcessException) return 'VPN_NATIVE_PROCESS_LAUNCH_FAILED';
    if (error is FileSystemException) return 'VPN_PRIVATE_STORAGE_FAILED';
    if (error is SocketException) return 'VPN_NETWORK_UNAVAILABLE';
    if (error is HttpException) return 'VPN_HTTP_UNAVAILABLE';
    if (error is TimeoutException) return 'VPN_OPERATION_TIMEOUT';
    if (error is StateError) return 'NATIVE_ENGINE_UNAVAILABLE';
    if (error is ArgumentError || error is TypeError) {
      return 'VPN_PROFILE_RUNTIME_TYPE_ERROR';
    }
    return 'VPN_INTERNAL_UNEXPECTED_FAILURE';
  }

  @override
  void initState() {
    super.initState();
    _durationTicker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) _updateConnectionClock();
    });
    _dark = widget.brand.themeMode == 'light' ? false
        : widget.brand.themeMode == 'system'
            ? WidgetsBinding.instance.platformDispatcher.platformBrightness == Brightness.dark
            : true;
    _restoreAppearance();
    _refreshNativeReadiness();
    _refreshVpnStatus();
    unawaited(_restoreCachedXrayInbounds());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && (widget.servers?.servers.isNotEmpty ?? false)) {
        _probeAllNodes();
      }
    });
  }

  @override
  void didUpdateWidget(covariant TwinConnectLiveDashboard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.brand.themeMode != widget.brand.themeMode) {
      _dark = widget.brand.themeMode == 'light' ? false
          : widget.brand.themeMode == 'system'
              ? WidgetsBinding.instance.platformDispatcher.platformBrightness == Brightness.dark
              : true;
    }
    if (oldWidget.username != widget.username ||
        oldWidget.panel.namespace != widget.panel.namespace ||
        oldWidget.panel.apiOrigin != widget.panel.apiOrigin) {
      // No in-memory Xray credentials may cross tenants or accounts.
      _xrayGroups = const [];
      _xrayGroupsLoaded = false;
      _xrayGroupsError = null;
      _selectedXrayNodeId = null;
      _selectedXrayInboundId = null;
      _xrayInboundRtts.clear();
      unawaited(_restoreCachedXrayInbounds());
    } else if (oldWidget.servers != widget.servers ||
        oldWidget.catalog != widget.catalog) {
      // The first session inventory often arrives after the dashboard
      // initializes; retry restore once authorized nodes become available.
      _xrayGroups = _assignedXrayGroups(_xrayGroups);
      if (_xrayGroups.isEmpty && !_xrayGroupsLoaded) {
        unawaited(_restoreCachedXrayInbounds());
      }
    }
    if (oldWidget.servers != widget.servers) {
      final ids = widget.servers?.servers.map((node) => node.id).toSet()
          ?? <String>{};
      _nodePings.removeWhere((id, value) => !ids.contains(id));
      _nodePingErrors.removeWhere((id, value) => !ids.contains(id));
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _probeAllNodes();
      });
    }
  }

  Future<void> _refreshVpnStatus() async {
    // Prevent method-channel calls from accumulating while Windows is busy.
    if (!Platform.isWindows || !mounted || _vpnBusy || _statusRefreshing) return;
    _statusRefreshing = true;
    final wasUp = _vpnUp;
    try {
      final status = await _vpn.status().timeout(const Duration(seconds: 8));
      if (!mounted) return;
      final nextUp = status['state'] == 'interface_up' ||
          status['state'] == 'peer_verified';
      final nextVerified = status['state'] == 'peer_verified' &&
          status['peerHandshakeVerified'] == true;
      final nextCleanup = status['state'] == 'needs_cleanup';
      final nextUnmanaged = status['state'] == 'unmanaged_service';
      final nextRx = status['rxBytes'] is int ? status['rxBytes'] as int : 0;
      final nextTx = status['txBytes'] is int ? status['txBytes'] as int : 0;
      // Avoid rebuilding the blurred dashboard when only polling unchanged data.
      if (nextUp != _vpnUp || nextVerified != _vpnVerified ||
          nextCleanup != _vpnCleanup || nextUnmanaged != _vpnUnmanaged ||
          nextRx != _vpnRx || nextTx != _vpnTx) {
        setState(() {
          _vpnUp = nextUp;
          _vpnVerified = nextVerified;
          _vpnCleanup = nextCleanup;
          _vpnUnmanaged = nextUnmanaged;
          _vpnRx = nextRx;
          _vpnTx = nextTx;
          if (nextUp) {
            _recordTraffic('wireguard', nextRx, nextTx);
          } else if (!_modernUp) {
            _clearTrafficSamples();
          }
          if (!nextUp && !_modernUp) _resetNetworkStats();
        });
      }
      if (nextUp && (!wasUp || _networkTimer == null)) _startNetworkStats();
      if (nextUp && nextVerified && _publicIp == null) _readNetworkStats();
      // Native feature probe is expensive; do not repeat it every 12 seconds.
      if (_lastNativeReadyCheck == null ||
          DateTime.now().difference(_lastNativeReadyCheck!) >
              const Duration(minutes: 3)) {
        _refreshNativeReadiness();
      }
    } catch (_) {
      // A status timeout is not evidence that the tunnel disconnected.
      // Keep the last verified state, allowing navigation to stay responsive.
    } finally {
      _statusRefreshing = false;
    }
  }

  Future<void> _toggleVpn() async {
    if (_vpnBusy || !Platform.isWindows) return;
    if (_modernUp || _modernTunnel.isRunning || _xrayProxy.isRunning || _sudokuProxy.isRunning ||
        _ciscoTunnel.isRunning || _openVpnTunnel.hasChild ||
        _l2tpTunnel.hasChild) {
      await _stopModernTunnel();
      return;
    }
    if (_filter != 'all' && _filter != 'wireguard') {
      final id = _selectedServerId;
      if (id == null) {
        setState(() => _vpnError = 'SELECT_MODERN_SERVER');
        return;
      }
      if (_autoFastest) {
        if (_filter == 'all') {
          setState(() => _vpnError = 'SELECT_PROTOCOL_FOR_FASTEST');
          return;
        }
        final best = _fastestKnownIndex;
        if (best == null) {
          setState(() => _vpnError = 'NO_MEASURED_SERVER');
          return;
        }
        setState(() => _selected = best);
      }
      if (_filter == 'cisco') {
        await _startCiscoTunnel(_selectedServerId!);
      } else if (_filter == 'openvpn') {
        await _startOpenVpnTunnel(_selectedServerId!);
      } else if (_filter == 'l2tp') {
        await _startL2tpTunnel(_selectedServerId!);
      } else if (_filter == 'v2ray') {
        await _startXrayTunnel(_selectedServerId!);
      } else if (_filter == 'sudoku') {
        await _startSudokuTunnel(_selectedServerId!);
      } else if (SingBoxProfileValidator.supportsFamily(_filter)) {
        await _startModernTunnel(_filter, _selectedServerId!);
      } else {
        setState(() => _vpnError = 'NATIVE_PROTOCOL_ENGINE_NOT_READY');
      }
      return;
    }
    if (_vpnUnmanaged) {
      setState(() => _vpnError = 'UNMANAGED_WIREGUARD_SERVICE');
      return;
    }
    if (!_vpnUp && !_vpnCleanup && (!_vpnReady || !_wireGuardAllowed ||
        _selectedServerId == null || _filter != 'all' && _filter != 'wireguard')) {
      setState(() => _vpnError = !_wireGuardAllowed
          ? 'WIREGUARD_NOT_ALLOWED'
          : !_vpnReady ? 'WIREGUARD_NOT_INSTALLED_OR_ADMIN_REQUIRED'
          : 'SELECT_WIREGUARD_SERVER');
      return;
    }
    setState(() { _vpnBusy = true; _vpnError = null; });
    try {
      if (_vpnUp || _vpnCleanup) {
        await _vpn.stop();
        if (!mounted) return;
        setState(() {
          _vpnUp = false;
          _vpnVerified = false;
          _vpnCleanup = false;
          _vpnRx = 0;
          _vpnTx = 0;
          _activeNodeId = null;
          _resetNetworkStats();
        });
      } else {
        if (_autoFastest) {
          if (_filter != 'wireguard') {
            throw const FormatException('SELECT_PROTOCOL_FOR_FASTEST');
          }
          final best = _fastestKnownIndex;
          if (best == null) throw const FormatException('NO_MEASURED_SERVER');
          _selected = best;
        }
        final selectedId = _selectedServerId!;
        // Policy storage and native OS readiness are independent.
        // Probe both concurrently, then reuse the SAME native capability
        // snapshot for the mandatory per-protocol readiness gate.
        final api = TenantApi.fromBuildConfig();
        final checks = await Future.wait<Object>([
          _vpnPolicy.load(widget.panel.namespace, widget.username),
          NativeVpnBridge.probe(),
          api.loadSessionProtocolCatalog(
            panel: widget.panel, sessionToken: widget.sessionToken),
        ]);
        final policy = checks[0] as VpnPolicy;
        final capabilities = checks[1] as NativeVpnCapabilities;
        final native = await NativeVpnBridge.protocolReadiness(
          validatedCapabilities: capabilities,
        );
        final candidate = await ConnectionBootstrap(api: api).prepare(
          panel: widget.panel,
          sessionToken: widget.sessionToken,
          serverId: selectedId,
          protocolCode: 'wireguard',
          policy: policy,
          capabilities: capabilities,
          nativeProtocols: native,
          currentAttemptCatalog: Future<PanelProtocolCatalog>.value(
              checks[2] as PanelProtocolCatalog),
        );
        final node = WindowsWireGuardController.configForSingleNode(
            candidate.profiles, selectedId);
        final status = await _vpn.start(
          node: node, policy: policy, capabilities: capabilities,
          nativeProtocols: native,
        );
        if (!mounted) return;
        setState(() {
          _vpnUp = status['state'] == 'interface_up' ||
              status['state'] == 'peer_verified';
          _vpnVerified = status['state'] == 'peer_verified' &&
              status['peerHandshakeVerified'] == true;
          _vpnRx = status['rxBytes'] is int ? status['rxBytes'] as int : 0;
          _vpnTx = status['txBytes'] is int ? status['txBytes'] as int : 0;
          _activeNodeId = selectedId;
        });
        if (_vpnUp) _startNetworkStats();
      }
    } catch (error) {
      if (mounted) {
        setState(() => _vpnError = _errorText(error));
        // A helper may time out after Windows has already removed the tunnel.
        // Reconcile with the actual service; never infer failure = connected.
        try {
          final actual = await _vpn.status().timeout(
            const Duration(seconds: 8));
          if (mounted) {
            final stillUp = actual['state'] == 'interface_up' ||
                actual['state'] == 'peer_verified';
            setState(() {
              _vpnUp = stillUp;
              _vpnVerified = actual['state'] == 'peer_verified' &&
                  actual['peerHandshakeVerified'] == true;
              _vpnCleanup = actual['state'] == 'needs_cleanup';
              if (!stillUp) {
                _activeNodeId = null;
                _resetNetworkStats();
              }
            });
          }
        } catch (_) {
          // Keep the last proven state if Windows cannot be queried.
        }
      }
    } finally {
      if (mounted) setState(() => _vpnBusy = false);
    }
  }

  bool _persian = false;
  bool _dark = true;
  static const _languagePreference = 'twinconnect_ui_language_v1';
  static const _appearancePreference = 'twinconnect_ui_dark_v1';

  Future<void> _restoreAppearance() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final language = prefs.getString(_languagePreference);
      final dark = prefs.getBool(_appearancePreference + '_' + widget.username);
      if (!mounted) return;
      setState(() {
        if (language == 'fa' || language == 'en') {
          _persian = language == 'fa';
        }
        if (dark != null) _dark = dark;
      });
    } catch (_) {}
  }

  Future<void> _changeLanguage() async {
    final next = !_persian;
    setState(() => _persian = next);
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_languagePreference, next ? 'fa' : 'en');
    } catch (_) {}
  }

  Future<void> _changeAppearance() async {
    final next = !_dark;
    setState(() => _dark = next);
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_appearancePreference + '_' + widget.username, next);
    } catch (_) {}
  }

  String _page = 'home';
  String _filter = 'all';
  String _search = '';
  int _selected = 0;
  final Set<int> _favorites = <int>{};
  // User-facing Xray inbounds remain distinct choices. Last validated
  // entries are stored in OS-encrypted short-lived display cache only.
  // A connection ALWAYS fetches fresh authorized profiles from the panel.
  final XrayInboundSecureCache _xrayCache = const XrayInboundSecureCache();
  List<XrayServerProfiles> _xrayGroups = const [];

  bool get _xrayAuthorized => widget.catalog?.entries.any((entry) =>
      entry.protocol.code == 'v2ray' && entry.selected &&
      entry.configRecordPresent) ?? false;

  List<XrayServerProfiles> _assignedXrayGroups(
      List<XrayServerProfiles> groups) {
    final allowed = widget.servers?.servers.map((s) => s.id).toSet()
        ?? <String>{};
    return List.unmodifiable(groups.where((g) =>
        allowed.contains(g.serverId) && g.inbounds.isNotEmpty));
  }

  Future<void> _restoreCachedXrayInbounds() async {
    if (!_xrayAuthorized) return;
    final username = widget.username;
    final namespace = widget.panel.namespace;
    final origin = widget.panel.apiOrigin;
    final previous = await _xrayCache.read(
      username: username, namespace: namespace, panelOrigin: origin);
    if (!mounted || !_xrayAuthorized ||
        widget.username != username ||
        widget.panel.namespace != namespace ||
        widget.panel.apiOrigin != origin ||
        _xrayGroupsLoaded || _xrayGroups.isNotEmpty || previous == null) return;
    final visible = _assignedXrayGroups(previous);
    if (visible.isEmpty) return;
    setState(() => _xrayGroups = visible);
  }
  bool _xrayGroupsLoading = false;
  bool _xrayGroupsLoaded = false;
  String? _xrayGroupsError;
  String? _selectedXrayInboundId;
  String? _selectedXrayNodeId;
  final Map<String, int?> _xrayInboundRtts = {};
  final Set<String> _xrayInboundsProbing = {};
  bool _xrayPingAllBusy = false;

  Future<void> _probeXrayInbound(XrayInboundProfile inbound) async {
    if (!Platform.isWindows || !mounted) return;
    final key = XrayInboundLatency.key(inbound);
    if (_xrayInboundsProbing.contains(key)) return;
    setState(() => _xrayInboundsProbing.add(key));
    final latency = await XrayInboundLatency.probe(inbound);
    if (!mounted) return;
    setState(() {
      _xrayInboundRtts[key] = latency;
      _xrayInboundsProbing.remove(key);
    });
  }

  Future<void> _probeAllXrayInbounds() async {
    if (_xrayPingAllBusy || !mounted) return;
    _xrayPingAllBusy = true;
    try {
      final inbounds = [
        for (final group in _xrayGroups) ...group.inbounds,
      ];
      // Limit parallel sockets to avoid saturating the user's network.
      for (var i = 0; i < inbounds.length && mounted; i += 6) {
        final last = i + 6 < inbounds.length ? i + 6 : inbounds.length;
        await Future.wait([
          for (var j = i; j < last; j++) _probeXrayInbound(inbounds[j]),
        ]);
      }
    } finally {
      _xrayPingAllBusy = false;
    }
  }

  Future<void> _loadXrayGroups({bool refresh = false}) async {
    if (_xrayGroupsLoading || (!refresh && _xrayGroupsLoaded)) return;
    if (!mounted) return;
    setState(() {
      _xrayGroupsLoading = true;
      _xrayGroupsError = null;
    });
    try {
      final username = widget.username;
      final namespace = widget.panel.namespace;
      final origin = widget.panel.apiOrigin;
      final token = widget.sessionToken;
      final response = await TenantApi.fromBuildConfig()
          .loadSessionNativeProfiles(
        panel: widget.panel,
        sessionToken: token,
        protocol: VpnProtocols.byCode('v2ray')!,
        native: const NativeProtocolReadiness(supportedCodes: {'v2ray'}),
      );
      if (!mounted || !_xrayAuthorized ||
          username != widget.username ||
          namespace != widget.panel.namespace ||
          origin != widget.panel.apiOrigin ||
          token != widget.sessionToken) return;
      final visible = _assignedXrayGroups(response.xrayServerGroups);
      setState(() {
        _xrayGroups = visible;
        _xrayGroupsLoaded = true;
        _xrayInboundRtts.clear();
      });
      // Never cache a rejected or empty response. A successful panel
      // refresh replaces previous display data without manufacturing inbounds.
      try {
        if (visible.isEmpty) {
          await _xrayCache.clear();
        } else {
          await _xrayCache.save(
            username: username, namespace: namespace,
            panelOrigin: origin, groups: visible);
        }
      } catch (_) {
        // Secure-storage availability must never block a live connection.
      }
      if (mounted) unawaited(_probeAllXrayInbounds());
    } catch (_) {
      if (!mounted) return;
      // Failed refresh retains already validated in-memory/cached choices.
      // Display cache never authorizes connection or substitutes live data.
      setState(() {
        _xrayGroupsError = 'XRAY_SERVER_PROFILES_UNAVAILABLE';
      });
    } finally {
      if (mounted) setState(() => _xrayGroupsLoading = false);
    }
  }

  List<XrayInboundProfile> _inboundsForNode(String nodeId) {
    for (final group in _xrayGroups) {
      if (group.serverId == nodeId) return group.inbounds;
    }
    return const [];
  }


  String _formatTransferBytes(int bytes) {
    if (bytes < 0) return '—';
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) {
      return '${(bytes / 1024).toStringAsFixed(1)} KB';
    }
    if (bytes < 1024 * 1024 * 1024) {
      return '${(bytes / (1024 * 1024)).toStringAsFixed(2)} MB';
    }
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(2)} GB';
  }

  String _formatBytes(int bytes) {
    const gb = 1024 * 1024 * 1024;
    return '${(bytes / gb).toStringAsFixed(2)} GB';
  }

  String _expiryLabel() {
    final account = widget.account;
    if (account == null) return '—';
    if (account.expiresAt != null) {
      final date = account.expiresAt!.toLocal();
      return '${date.year}-${date.month.toString().padLeft(2, '0')}-'
          '${date.day.toString().padLeft(2, '0')}';
    }
    if (account.activationDurationDays != null &&
        account.activationDurationDays! > 0) {
      return tr('پس از اولین اتصال', 'Starts on first use');
    }
    return tr('نامحدود', 'Unlimited');
  }

  Color get purple => BrandTheme.accent(widget.brand,
      _dark ? Brightness.dark : Brightness.light);
  List<_DemoServer> get demoServers => [
    for (final server in widget.servers?.servers ?? const <AppServer>[])
      _DemoServer(
        server.countryCode,
        server.name,
        server.nodeOnline ? 'Online node' : 'Node status unknown',
        const [],
      ),
  ];
  _DemoServer? get selectedServer =>
      demoServers.isEmpty ? null :
      demoServers[_selected.clamp(0, demoServers.length - 1)];



  // Each account uses links from its own authenticated tenant brand, never
  // a hard-coded vendor/other reseller destination.
  Future<void> _openTenantLink(String? raw, String label) async {
    final url = raw == null ? null : Uri.tryParse(raw.trim());
    final valid = url != null &&
        url.scheme == 'https' &&
        url.host.contains('.') &&
        url.userInfo.isEmpty &&
        !url.hasFragment &&
        !url.host.endsWith('.local') &&
        !url.host.endsWith('.internal') &&
        !url.host.endsWith('.localhost');
    if (!valid) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(tr('لینک $label توسط مدیریت پنل تنظیم نشده است.',
              'The $label link is not configured by your provider.')),
        ));
      }
      return;
    }
    try {
      final launched = await launchUrl(url, mode: LaunchMode.externalApplication);
      if (!launched && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(tr('بازکردن لینک $label ممکن نشد.',
              'Unable to open the $label link.')),
        ));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(tr('بازکردن لینک $label ممکن نشد.',
              'Unable to open the $label link.')),
        ));
      }
    }
  }

  String tr(String fa, String en) => _persian ? fa : en;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: widget.brand.brandName,
      debugShowCheckedModeBanner: false,
      locale: Locale(_persian ? 'fa' : 'en'),
      supportedLocales: const [Locale('fa'), Locale('en')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      themeMode: _dark ? ThemeMode.dark : ThemeMode.light,
      theme: BrandTheme.make(widget.brand, Brightness.light),
      darkTheme: BrandTheme.make(widget.brand, Brightness.dark),
      home: Builder(builder: _shell),
    );
  }

  Widget _shell(BuildContext context) {
    // Keep the authenticated desktop sidebar spacious; compact mode is only
    // for narrow windows where a full sidebar would crowd live connection cards.
    final wide = MediaQuery.sizeOf(context).width >= 980;
    final ink = _dark ? const Color(0xFFF7F4FF) : const Color(0xFF21233F);
    final sub = _dark ? const Color(0xFFABB4C9) : const Color(0xFF565D75);
    final line = _dark ? const Color(0xFF3C4564) : const Color(0xFFDADCEA);
    // Both colors are tenant-managed in the main panel and reseller studio.
    // Keep explicit overrides for dark/light while the owner's palette remains
    // authoritative across the dashboard, cards and side navigation.
    final panel = BrandTheme.surface(widget.brand,
        _dark ? Brightness.dark : Brightness.light);
    final sidebar = BrandTheme.backgroundColor(widget.brand,
        _dark ? Brightness.dark : Brightness.light);

    Text txt(String s, {double size = 13, bool bold = false, Color? color,
        TextAlign? align}) => Text(
      s, textAlign: align, overflow: TextOverflow.ellipsis,
      style: TextStyle(
        color: color ?? ink, fontSize: size,
        fontWeight: bold ? FontWeight.w700 : FontWeight.w400,
      ),
    );

    // Reusable frosted-glass surface for cards in both light and dark themes.
    // The blur samples only the background behind each translucent surface.
    Widget glassCard({
      required Widget child,
      double radius = 20,
      bool selected = false,
      EdgeInsetsGeometry padding = EdgeInsets.zero,
      Key? key,
    }) => TwinConnectGlassCard(
      key: key,
      dark: _dark,
      surfaceColor: panel,
      accentColor: purple,
      secondaryColor: BrandTheme.parse(widget.brand.secondaryColor, '#00DCEB'),
      selected: selected,
      radius: radius,
      padding: padding,
      child: child,
    );

    Widget sideNav(String page, IconData icon, String title) => Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(17),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              key: Key('devNav_$page'),
              borderRadius: BorderRadius.circular(17),
              onTap: () => setState(() => _page = page),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 230),
                padding: EdgeInsets.symmetric(
                  horizontal: wide ? 17 : 9,
                  vertical: wide ? 16 : 13),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(17),
                  gradient: LinearGradient(
                    begin: Alignment.topLeft, end: Alignment.bottomRight,
                    colors: _page == page
                        ? [purple.withValues(alpha: .52),
                           BrandTheme.parse(widget.brand.secondaryColor, '#00DCEB')
                               .withValues(alpha: .22)]
                        : [
                            (_dark ? Colors.white : purple)
                                .withValues(alpha: .16),
                            BrandTheme.parse(widget.brand.secondaryColor, '#00DCEB')
                                .withValues(alpha: .085),
                          ]),
                  border: Border.all(
                    color: _page == page
                        ? purple.withValues(alpha: .72)
                        : (_dark ? Colors.white : purple)
                            .withValues(alpha: .30)),
                  boxShadow: _page == page ? [
                    BoxShadow(color: purple.withValues(alpha: .30),
                      blurRadius: 22, spreadRadius: -4),
                  ] : const [],
                ),
                child: Row(
                  mainAxisAlignment: wide
                      ? MainAxisAlignment.start : MainAxisAlignment.center,
                  children: [
                    Icon(icon, color: _page == page
                        ? (_dark ? Colors.white : purple)
                        : (_dark ? const Color(0xFFE1D9FA)
                            : const Color(0xFF53496D)),
                      size: wide ? 24 : 21),
                    if (wide) ...[
                      const SizedBox(width: 14),
                      Expanded(child: txt(title,
                        color: _page == page ? ink
                            : (_dark ? const Color(0xFFE7E2F8)
                                : const Color(0xFF42395A)),
                        bold: true)),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );

    Widget sideBar() => Container(
      width: wide ? 258 : 74,
      padding: EdgeInsets.symmetric(
        horizontal: wide ? 17 : 7, vertical: 22),
      // Share the exact ambient gradient with the main connection view.
      // A solid sidebar fill previously made the menu look like another app.
      decoration: BoxDecoration(
        color: Colors.transparent,
        border: Border(left: BorderSide(
          color: line.withValues(alpha: .25))),
      ),
      child: Column(children: [
        Container(
          width: 42, height: 42,
          clipBehavior: Clip.antiAlias,
          decoration: BoxDecoration(
            gradient: LinearGradient(colors: [
              purple, BrandTheme.parse(widget.brand.secondaryColor, '#7051D4')]),
            borderRadius: BorderRadius.circular(13),
          ),
          child: widget.brand.logoUrl != null &&
                  Uri.tryParse(widget.brand.logoUrl!)?.scheme == 'https'
            ? Image.network(widget.brand.logoUrl!, fit: BoxFit.contain,
                errorBuilder: (_, __, ___) => const Icon(
                  Icons.all_inclusive_rounded, color: Colors.white, size: 27))
            : const Icon(Icons.all_inclusive_rounded,
                color: Colors.white, size: 27),
        ),
        if (wide) ...[
          const SizedBox(height: 9),
          txt(widget.brand.brandName, size: 17, bold: true),
        ],
        const SizedBox(height: 38),
        sideNav('home', Icons.bolt_rounded, tr('اتصال سریع', 'Quick connect')),
        sideNav('locations', Icons.place_outlined, tr('مکان‌ها', 'Locations')),
        sideNav('settings', Icons.tune_rounded, tr('تنظیمات', 'Settings')),
        sideNav('account', Icons.person_outline_rounded, tr('حساب', 'Account')),
        const SizedBox(height: 9),
        if (wide)
          Container(
            key: const Key('tenantQuickLinks'),
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 7),
            decoration: BoxDecoration(
              color: (_dark ? Colors.white : purple)
                  .withValues(alpha: _dark ? .13 : .09),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: purple.withValues(alpha: .35)),
            ),
            child: Row(children: [
              for (final item in <({String id, IconData icon, String fa,
                  String en, String? url})>[
                (id: 'support', icon: Icons.support_agent_outlined,
                    fa: 'پشتیبانی', en: 'Support', url: widget.brand.telegramUrl),
                (id: 'renewal', icon: Icons.autorenew_rounded,
                    fa: 'تمدید', en: 'Renew', url: widget.brand.renewalUrl),
                (id: 'website', icon: Icons.language_rounded,
                    fa: 'سایت', en: 'Website', url: widget.brand.websiteUrl),
              ])
                Expanded(child: Tooltip(
                  message: tr(item.fa, item.en),
                  child: InkWell(
                    key: Key('tenantLink_${item.id}'),
                    borderRadius: BorderRadius.circular(10),
                    onTap: () => _openTenantLink(
                        item.url, tr(item.fa, item.en)),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: Column(mainAxisSize: MainAxisSize.min, children: [
                        Icon(item.icon, color: purple, size: 20),
                        const SizedBox(height: 5),
                        txt(tr(item.fa, item.en), size: 9, bold: true),
                      ]),
                    ),
                  ),
                )),
            ]),
          )
        else
          PopupMenuButton<String>(
            key: const Key('tenantQuickLinksCompact'),
            tooltip: tr('پشتیبانی و پیوندها', 'Support and links'),
            icon: Icon(Icons.open_in_new_rounded, color: purple),
            onSelected: (value) {
              if (value == 'support') {
                _openTenantLink(widget.brand.telegramUrl,
                    tr('پشتیبانی', 'Support'));
              } else if (value == 'renewal') {
                _openTenantLink(widget.brand.renewalUrl,
                    tr('تمدید', 'Renew'));
              } else if (value == 'website') {
                _openTenantLink(widget.brand.websiteUrl,
                    tr('سایت', 'Website'));
              }
            },
            itemBuilder: (_) => [
              PopupMenuItem(value: 'support',
                  child: Text(tr('پشتیبانی', 'Support'))),
              PopupMenuItem(value: 'renewal',
                  child: Text(tr('تمدید', 'Renew'))),
              PopupMenuItem(value: 'website',
                  child: Text(tr('سایت', 'Website'))),
            ],
          ),
        const Spacer(),
        if (wide) glassCard(
          padding: const EdgeInsets.all(12),
          radius: 18,
          child: Column(children: [
            txt(widget.username, bold: true, size: 11),
            const SizedBox(height: 3),
            txt(tr('اشتراک فعال', 'Signed in'),
                color: sub, size: 10),
          ]),
        ),
        const SizedBox(height: 12),
        IconButton(
          key: const Key('devThemeToggle'),
          tooltip: tr('تغییر ظاهر', 'Theme'),
          icon: Icon(_dark ? Icons.light_mode_outlined
              : Icons.dark_mode_outlined, color: sub),
          onPressed: _changeAppearance,
        ),
        TextButton(
          key: const Key('devLanguageToggle'),
          onPressed: _changeLanguage,
          child: Text(_persian ? 'EN' : 'فا'),
        ),
        IconButton(
          key: const Key('devSettingsButton'),
          tooltip: tr('تنظیمات', 'Settings'),
          onPressed: () => setState(() => _page = 'settings'),
          icon: Icon(Icons.settings_outlined, color: sub),
        ),
      ]),
    );

    Widget smallPill(String s, {IconData? icon}) => Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: BoxDecoration(
        color: purple.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(30),
        border: Border.all(color: purple.withValues(alpha: 0.28))),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (icon != null) ...[
          Icon(icon, color: purple, size: 15), const SizedBox(width: 6)],
        txt(s, color: _dark ? const Color(0xFFE5CAFF)
            : const Color(0xFF6336BA), size: 11),
      ]),
    );

    Widget powerCard() => ClipRRect(
      borderRadius: BorderRadius.circular(28),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
        child: Container(
      key: const Key('liveConnectionStatus'),
      constraints: const BoxConstraints(minHeight: 415),
      padding: const EdgeInsets.fromLTRB(18, 26, 18, 25),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(29),
        gradient: LinearGradient(
          begin: Alignment.topLeft, end: Alignment.bottomRight,
          colors: _dark
              ? [
                  Color.lerp(panel, purple, .35)!.withValues(alpha: .36),
                  panel.withValues(alpha: .24),
                  Color.lerp(panel,
                    BrandTheme.parse(widget.brand.secondaryColor, '#00DCEB'),
                    .28)!.withValues(alpha: .38),
                ]
              : [
                  const Color(0xFFEDE4FF).withValues(alpha: 0.76),
                  Colors.white.withValues(alpha: 0.64),
                  const Color(0xFFE6F1FF).withValues(alpha: 0.72),
                ],
        ),
        border: Border.all(color: purple.withValues(alpha: 0.70)),
        boxShadow: [BoxShadow(
          color: purple.withValues(alpha: _dark ? 0.25 : 0.11),
          blurRadius: 38, spreadRadius: 2, offset: const Offset(0, 14)),
        ],
      ),
      child: Column(children: [
        // The primary indicator must reflect a verified tunnel, not simply
        // an adapter that Windows reports as enabled.
        AnimatedSwitcher(
          key: const Key('liveOnlineStatus'),
          duration: const Duration(milliseconds: 360),
          switchInCurve: Curves.easeOutBack,
          switchOutCurve: Curves.easeIn,
          transitionBuilder: (child, animation) => FadeTransition(
            opacity: animation,
            child: ScaleTransition(
              scale: Tween<double>(begin: .89, end: 1).animate(animation),
              child: child,
            ),
          ),
          child: Container(
            key: ValueKey<String>(_vpnBusy ? 'busy' :
                (_modernUp || _vpnVerified) ? 'online' :
                (_vpnUp || _vpnCleanup) ? 'unverified' : 'offline'),
            padding: const EdgeInsets.symmetric(horizontal: 17, vertical: 10),
            decoration: BoxDecoration(
              color: (_modernUp || _vpnVerified)
                  ? const Color(0xFF16D6A4).withValues(alpha: .15)
                  : _vpnBusy ? purple.withValues(alpha: .16)
                  : sub.withValues(alpha: .11),
              border: Border.all(
                color: (_modernUp || _vpnVerified)
                    ? const Color(0xFF36E5BB).withValues(alpha: .60)
                    : _vpnBusy ? purple.withValues(alpha: .52)
                    : sub.withValues(alpha: .24),
              ),
              borderRadius: BorderRadius.circular(30),
            ),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(
                (_modernUp || _vpnVerified)
                    ? Icons.verified_rounded
                    : _vpnBusy ? Icons.sync_rounded
                    : (_vpnUp || _vpnCleanup)
                        ? Icons.shield_outlined : Icons.power_off_rounded,
                size: 18,
                color: (_modernUp || _vpnVerified)
                    ? const Color(0xFF36E5BB) : _vpnBusy ? purple : sub,
              ),
              const SizedBox(width: 9),
              txt((_modernUp || _vpnVerified)
                  ? tr('آنلاین هستید', 'You are online')
                  : _vpnBusy
                      ? tr('در حال اتصال...', 'Connecting...')
                      : (_vpnUp || _vpnCleanup)
                          ? tr('روشن؛ در انتظار تأیید', 'On; awaiting verification')
                          : tr('آفلاین هستید', 'You are offline'),
                  bold: true, size: 13),
            ]),
          ),
        ),
        const SizedBox(height: 18),
        TweenAnimationBuilder<double>(
          key: const Key('devPowerEntranceAnimation'),
          tween: Tween(begin: .94, end: 1.0),
          duration: const Duration(milliseconds: 480),
          curve: Curves.easeOutCubic,
          builder: (context, scale, child) =>
              Transform.scale(scale: scale, child: child),
          child: Container(
            width: 250,
            padding: const EdgeInsets.all(5),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(24),
              border: Border.all(
                color: (_modernUp || _vpnVerified)
                    ? const Color(0xFF00E6B0).withValues(alpha: .72)
                    : purple.withValues(alpha: .66)),
              boxShadow: [
                BoxShadow(
                  color: (_modernUp || _vpnVerified)
                      ? const Color(0xFF00E6B0).withValues(alpha: .19)
                      : purple.withValues(alpha: .23),
                  blurRadius: 24, spreadRadius: 2),
              ],
            ),
            child: FilledButton(
              key: const Key('liveConnectionControlsButton'),
              onPressed: _vpnBusy ? null : _toggleVpn,
              style: FilledButton.styleFrom(
                minimumSize: const Size(238, 80),
                padding: const EdgeInsets.symmetric(
                    horizontal: 19, vertical: 10),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(19)),
                backgroundColor: Colors.transparent,
                foregroundColor: Colors.white,
                disabledBackgroundColor: Colors.transparent,
                elevation: 0,
              ).copyWith(
                backgroundColor: WidgetStateProperty.resolveWith((states) {
                  if (states.contains(WidgetState.disabled)) {
                    return purple.withValues(alpha: .35);
                  }
                  return (_modernUp || _vpnVerified)
                      ? const Color(0xFF0E997E)
                      : const Color(0xFF7943DF);
                }),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    width: 47, height: 47,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(14),
                      color: Colors.white.withValues(alpha: .13),
                      border: Border.all(
                          color: Colors.white.withValues(alpha: .20))),
                    child: _vpnBusy
                        ? const Padding(
                            padding: EdgeInsets.all(12),
                            child: CircularProgressIndicator(
                              strokeWidth: 2.5,
                              color: Colors.white))
                        : Icon((_vpnUp || _modernUp)
                            ? Icons.stop_rounded
                            : Icons.power_settings_new_rounded,
                            size: 28, color: Colors.white),
                  ),
                  const SizedBox(width: 13),
                  Expanded(child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(_vpnBusy
                          ? tr('در حال اتصال', 'Connecting')
                          : (_vpnUp || _modernUp)
                              ? tr('قطع اتصال', 'Disconnect')
                              : tr('اتصال سریع', 'Connect now'),
                          style: const TextStyle(color: Colors.white,
                            fontSize: 16,
                            fontWeight: FontWeight.w800)),
                      const SizedBox(height: 3),
                      Text(_vpnBusy
                          ? tr('در حال بررسی مسیر', 'Checking route')
                          : (_modernUp || _vpnVerified)
                              ? tr('تونل فعال', 'Tunnel active')
                              : (_vpnUp || _vpnCleanup)
                                  ? tr('در انتظار تأیید', 'Awaiting verification')
                                  : tr('با سرور انتخابی', 'Selected server'),
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: .77),
                          fontSize: 10.5)),
                    ],
                  )),
                  Icon(Icons.arrow_forward_ios_rounded,
                    size: 14,
                    color: Colors.white.withValues(alpha: .70)),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        AnimatedSwitcher(
          duration: const Duration(milliseconds: 280),
          child: txt(
            _vpnBusy
                ? tr('در حال برقراری اتصال', 'Establishing connection')
                : (_modernUp || _vpnVerified)
                    ? tr('اتصال امن برقرار است', 'Secure connection active')
                    : (_vpnUp || _vpnCleanup)
                        ? tr('در حال تأیید اتصال', 'Verifying connection')
                        : tr('برای اتصال لمس کنید', 'Tap to connect'),
            size: 19, bold: true),
        ),
        const SizedBox(height: 9),
        ValueListenableBuilder<int>(
          valueListenable: _connectedSeconds,
          builder: (context, elapsed, child) => AnimatedOpacity(
            duration: const Duration(milliseconds: 260),
            opacity: _verifiedConnectionActive ? 1 : .68,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.timer_outlined, size: 17,
                    color: _verifiedConnectionActive
                        ? const Color(0xFF36E5BB) : sub),
                const SizedBox(width: 7),
                txt(tr('مدت اتصال', 'Connected for'),
                    size: 12, color: sub),
                const SizedBox(width: 8),
                Text(_formatConnectedSeconds(elapsed),
                    key: const Key('liveConnectionDuration'),
                    textDirection: TextDirection.ltr,
                    style: TextStyle(
                      fontSize: 15, fontWeight: FontWeight.w700,
                      fontFeatures: const [FontFeature.tabularFigures()],
                      color: _verifiedConnectionActive
                          ? const Color(0xFF36E5BB) : sub,
                    )),
              ],
            ),
          ),
        ),
        if (_vpnUp || _modernUp) ...[
          const SizedBox(height: 6),
          txt(_modernUp
              ? tr('IP خروجی تونل تأیید شد', 'Tunnel exit IP verified')
              : _vpnVerified
                  ? tr('دست‌دهی با سرور تأیید شد', 'Server handshake verified')
                  : tr('رابط روشن است؛ دست‌دهی هنوز تأیید نشده',
                      'Interface is on; handshake is not yet verified'),
              size: 12, color: sub),
        ],
        if (_vpnError != null) ...[
          const SizedBox(height: 8),
          Text(
            switch (_vpnError!) {
              'WIREGUARD_NOT_ALLOWED' => tr(
                'این اشتراک مجوز WireGuard ندارد.',
                'WireGuard is not enabled for this subscription.'),
              'WIREGUARD_NOT_INSTALLED_OR_ADMIN_REQUIRED' => tr(
                'WireGuard رسمی را نصب کرده و برنامه را با دسترسی مدیر اجرا کنید.',
                'Install official WireGuard and run this app as Administrator.'),
              'SELECT_WIREGUARD_SERVER' => tr(
                'لطفاً یک سرور انتخاب کنید.',
                'Please select a server.'),
              'SELECT_MODERN_SERVER' => tr(
                'لطفاً یک سرور انتخاب کنید.',
                'Please select a server.'),
              'L2TP_NATIVE_START_FAILED' => tr(
                'شروع اتصال L2TP ویندوز ناموفق بود.',
                'Windows L2TP could not start.'),
              'L2TP_IPSEC_NEGOTIATION_FAILED' => tr(
                'مذاکره IPsec با سرور ناموفق بود.',
                'IPsec negotiation with the server failed.'),
              'L2TP_LOGIN_REJECTED' => tr(
                'نام کاربری یا رمز L2TP اشتباه است.',
                'L2TP authentication was rejected.'),
              'L2TP_SERVER_UNREACHABLE' => tr(
                'سرور L2TP یا UDP 500/4500 در دسترس نیست.',
                'L2TP server or UDP ports 500/4500 are unreachable.'),
              'L2TP_EGRESS_NOT_VERIFIED' => tr(
                'IP خروجی L2TP تأیید نشد.',
                'L2TP internet egress was not verified.'),
              'L2TP_CONNECT_TIMEOUT' => tr(
                'زمان اتصال L2TP به پایان رسید.',
                'L2TP connection timed out.'),
              'L2TP_HEALTH_DEGRADED' => tr(
                'اتصال L2TP پایدار نیست.',
                'L2TP tunnel health has degraded.'),
              'L2TP_HEALTH_PROBE_UNAVAILABLE' => tr(
                'وضعیت اتصال L2TP در ویندوز برقرار است، ولی بررسی IP اینترنت از دو سرویس ناموفق بود.',
                'Windows L2TP remains present, but both internet IP checks failed.'),
              'L2TP_ROUTE_BYPASS_DETECTED' => tr(
                'IP خروجی به IP قبل از اتصال برگشته؛ مسیر L2TP احتمالاً دور زده شده است.',
                'Public IP returned to the pre-VPN address; L2TP routing may have been bypassed.'),
              'L2TP_RAS_STATUS_UNAVAILABLE' => tr(
                'بررسی وضعیت L2TP در ویندوز پاسخ نداد.',
                'Windows RAS did not return an L2TP status.'),
              'L2TP_RAS_DISCONNECTED' => tr(
                'ویندوز اتصال L2TP را قطع‌شده گزارش می‌کند.',
                'Windows reports that the L2TP connection was disconnected.'),
              'L2TP_DISCONNECT_PENDING' => tr(
                'قطع اتصال L2TP هنوز کامل نشده است.',
                'Windows L2TP disconnect is pending.'),
              'OPENVPN_ENGINE_NOT_INSTALLED' => tr(
                'موتور OpenVPN همراه نصب این نسخه آماده نیست.',
                'The OpenVPN engine was not installed with this version.'),
              'OPENVPN_ENGINE_START_FAILED' => tr(
                'موتور OpenVPN هنگام شروع اتصال خطا داد.',
                'OpenVPN failed during tunnel initialization.'),
              'OPENVPN_PROCESS_EXITED' => tr(
                'موتور OpenVPN قبل از تأیید اتصال بسته شد.',
                'OpenVPN exited before the connection was verified.'),
              'OPENVPN_EGRESS_NOT_VERIFIED' => tr(
                'آدرس خروجی OpenVPN تغییر نکرد؛ اتصال تأیید نشده است.',
                'OpenVPN egress did not change; connection is unverified.'),
              'OPENVPN_HEALTH_DEGRADED' => tr(
                'مسیر شبکه OpenVPN پاسخ معتبر نمی‌دهد.',
                'OpenVPN route health is degraded.'),
              'SUDOKU_OR_TUN_ENGINE_UNAVAILABLE' => tr(
                'موتور رسمی سودوکو یا موتور تونل ویندوز در این نسخه وجود ندارد.',
                'Sudoku core or the Windows tunnel engine is unavailable.'),
              'SUDOKU_ENGINE_NOT_BUNDLED' => tr(
                'فایل اجرایی سودوکو همراه برنامه نصب نشده است.',
                'The official Sudoku executable is missing from this build.'),
              'SUDOKU_SERVER_PROFILE_MISSING' => tr(
                'کانفیگ سودوکو برای این سرور در اشتراک پیدا نشد.',
                'No Sudoku profile was delivered for this server.'),
              'SUDOKU_PROFILE_NOT_READY' => tr(
                'کانفیگ سودوکو معتبر نیست یا هنوز برای اتصال آماده نشده است.',
                'Sudoku configuration is invalid or not ready yet.'),
              'SUDOKU_ENDPOINT_DNS_UNAVAILABLE' => tr(
                'آدرس سرور سودوکو به IP عمومی معتبر تبدیل نشد.',
                'The Sudoku endpoint did not resolve to a valid public IPv4.'),
              'SUDOKU_PRIVATE_CONFIG_STAGE_FAILED' => tr(
                'ویندوز اجازه ساخت فایل موقت حفاظت‌شده سودوکو را نداد.',
                'Windows could not securely stage the temporary Sudoku configuration.'),
              'SUDOKU_PROCESS_GUARD_UNAVAILABLE' => tr(
                'محافظ پردازش سودوکو در ویندوز فعال نشد؛ اتصال برای امنیت متوقف شد.',
                'The native Sudoku process guard failed; connection was stopped.'),
              String status when status.startsWith('SUDOKU_CORE_EXIT_CODE_') => tr(
                'موتور سودوکو متوقف شد (کد خروج 0x${status.substring('SUDOKU_CORE_EXIT_CODE_'.length)})؛ تونل به‌صورت امن قطع شد.',
                'Sudoku exited with Windows code 0x${status.substring('SUDOKU_CORE_EXIT_CODE_'.length)}; the tunnel was closed safely.'),
              'SUDOKU_CONFIG_STAGE_TIMEOUT' => tr(
                'ویندوز هنگام آماده‌سازی امن کانفیگ سودوکو پاسخ نداد.',
                'Windows timed out while staging the protected Sudoku config.'),
              'SUDOKU_PROCESS_START_TIMEOUT' => tr(
                'اجرای موتور Sudoku در ویندوز بیش از حد طول کشید.',
                'Windows timed out while starting the Sudoku executable.'),
              'SUDOKU_PROCESS_GUARD_TIMEOUT' => tr(
                'محافظ پردازش سودوکو در ویندوز به‌موقع پاسخ نداد.',
                'Windows timed out while attaching the Sudoku process guard.'),
              'SUDOKU_BASELINE_IP_TIMEOUT' => tr(
                'بررسی IP اینترنت پیش از راه‌اندازی تونل پاسخ نداد؛ اتصال برای امنیت متوقف شد.',
                'Direct pre-VPN public IP check timed out; no tunnel was enabled.'),
              'SUDOKU_CORE_EXITED' => tr(
                'موتور سودوکو متوقف شد؛ تونل نیز برای جلوگیری از نشتی قطع شد.',
                'The Sudoku core stopped; the VPN tunnel was closed safely.'),
              'SUDOKU_LOCAL_PORT_CONFLICT' => tr(
                'پورت محلی سودوکو اشغال است؛ برنامه دیگری از آن استفاده می‌کند.',
                'Sudoku local listener port is already in use.'),
              'SUDOKU_CORE_ACCESS_DENIED' => tr(
                'ویندوز دسترسی لازم برای اجرای موتور سودوکو را نداد.',
                'Windows denied access to the Sudoku process or configuration.'),
              'SUDOKU_CONFIG_LOAD_FAILED' => tr(
                'موتور سودوکو نتوانست کانفیگ حفاظت‌شده را بخواند.',
                'Sudoku could not load its protected configuration.'),
              'SUDOKU_KEY_REJECTED' => tr(
                'موتور سودوکو کلید کانفیگ دریافت‌شده را نپذیرفت.',
                'Sudoku rejected the delivered profile key.'),
              'SUDOKU_CORE_EXITED_CLEANLY' => tr(
                'موتور سودوکو بدون درخواست کاربر به‌صورت عادی بسته شد؛ تونل قطع شد.',
                'Sudoku exited cleanly without a user request; VPN was disconnected.'),

              'SUDOKU_LOOPBACK_PROXY_UNAVAILABLE' => tr(
                'پروکسی محلی سودوکو بعد از اجرای موتور آماده نشد.',
                'Sudoku local SOCKS5 proxy did not become ready.'),
              'SUDOKU_REMOTE_EGRESS_UNVERIFIED' => tr(
                'ارتباط واقعی سودوکو با سرور تأیید نشد؛ اینترنت از آن عبور نکرد.',
                'Sudoku remote handshake/HTTPS egress could not be verified.'),
              'NATIVE_PROTOCOL_ENGINE_NOT_READY' => tr(
                'موتور مستقل این پروتکل هنوز آماده نیست.',
                'This protocol requires a native engine that is not ready yet.'),
              'SINGBOX_NATIVE_TUN_NOT_READY' => tr(
                'آزمایش پروکسی انجام می‌شود؛ VPN سراسری هنوز فعال نیست.',
                'Proxy check is available; system VPN is not enabled.'),
              'UNMANAGED_WIREGUARD_SERVICE' => tr(
                'سرویس WireGuard متعلق به برنامه نیست؛ تغییری ایجاد نشد.',
                'WireGuard service is not managed by this app.'),
              'SINGBOX_SERVER_TRANSPORT_UNREACHABLE' => tr(
                'آزمایش اولیه ارتباط پروتکل با سرور موفق نبود؛ اتصال جدید برقرار نشد.',
                'Selected protocol failed the transport preflight; no new connection was established.'),
              'SINGBOX_ENDPOINT_DNS_POISONED' => tr(
                'DNS آدرس خصوصی یا نامعتبر برای سرور برگرداند. پاسخ شبکه محلی مشکوک است.',
                'DNS returned a private address for the VPN endpoint; local DNS may be filtered.'),
              'SINGBOX_ENDPOINT_DNS_UNAVAILABLE' => tr(
                'نام دامنه سرور قبل از اتصال VPN قابل تبدیل به IP نبود.',
                'Could not resolve VPN server domain before starting the tunnel.'),
              'SINGBOX_TUN_INTERNET_UNREACHABLE' => tr(
                'تونل اجرا شد اما درخواست اینترنت از مسیر آن پاسخ نگرفت؛ اتصال تأیید نشد.',
                'TUN started but the internet test failed; connection not verified.'),
              'SINGBOX_TUN_HEALTH_DEGRADED' => tr(
                'کیفیت مسیر اتصال کاهش یافته؛ اینترنت را بررسی کنید.',
                'VPN route health degraded; check internet connectivity.'),
              'SINGBOX_TUN_ROUTE_NOT_VERIFIED' => tr(
                'IP اینترنت تغییر نکرد؛ مسیر TUN تأیید نشد و اتصال متوقف شد.',
                'Public IP did not change; TUN routing could not be verified.'),
              'SINGBOX_PROCESS_EXITED' => tr(
                'موتور اتصال قبل از تأیید متوقف شد.',
                'Connection engine stopped before verification.'),
              'SINGBOX_TUN_CONFIG_INVALID' => tr(
                'کانفیگ این پروتکل برای موتور ویندوز معتبر نیست.',
                'This protocol configuration was rejected by the Windows engine.'),
              'SINGBOX_TUN_ADAPTER_DOWN' => tr(
                'آداپتور مجازی ساخته شده ولی فعال نشده است؛ درایور TUN را بررسی کنید.',
                'TUN adapter exists but is not up; inspect the TUN driver.'),
              'SINGBOX_TUN_NATIVE_INSPECTION_FAILED' => tr(
                'ویندوز اجازه بررسی مستقیم وضعیت آداپتور را نداد؛ آزمایش مسیر اینترنت ادامه دارد.',
                'Windows native adapter inspection unavailable; internet route testing continues.'),
              'SINGBOX_TUN_ADAPTER_MISSING' => tr(
                'آداپتور TwinConnectSB ساخته نشد؛ درایور یا مجوز ویندوز را بررسی کنید.',
                'TwinConnectSB adapter was not created; check Windows driver and permissions.'),
              'SINGBOX_TUN_NOT_PREFERRED' => tr(
                'آداپتور VPN ساخته شده اما ویندوز اینترنت را از مسیر دیگری می‌فرستد؛ احتمال تداخل VPN یا اولویت مسیر شبکه وجود دارد.',
                'VPN adapter is present, but Windows is routing via another interface; another VPN or route priority may be interfering.'),
              'SINGBOX_TUN_DEFAULT_ROUTE_MISSING' => tr(
                'آداپتور ساخته شد، اما مسیر اینترنت از آن عبور نمی‌کند.',
                'TUN adapter exists but its default internet route is missing.'),
              'SINGBOX_TUN_ROUTE_INSPECTION_FAILED' => tr(
                'وضعیت مسیر شبکه ویندوز قابل بررسی نبود.',
                'Could not inspect Windows TUN routes.'),
              'SINGBOX_TUN_DRIVER_ERROR' => tr(
                'درایور رابط TUN در ویندوز راه‌اندازی نشد.',
                'Windows TUN driver failed to start.'),
              'SINGBOX_TUN_PERMISSION_DENIED' => tr(
                'دسترسی مدیریت برای راه‌اندازی TUN کافی نیست.',
                'Administrator permission required for TUN setup.'),
              'SINGBOX_TUN_ROUTE_INSTALL_FAILED' => tr(
                'ویندوز نتوانست مسیر شبکه TUN را نصب کند.',
                'Windows failed to install TUN routes.'),
              'SINGBOX_TUN_ADAPTER_START_FAILED' => tr(
                'ساخت رابط مجازی TUN با خطا روبه‌رو شد.',
                'Virtual TUN interface could not start.'),
              'CISCO_ENGINE_UNAVAILABLE' => tr(
                'موتور سیسکو در بسته ویندوز آماده نیست.',
                'Bundled Cisco engine is not available.'),
              'CISCO_SERVER_PROFILE_MISSING' => tr(
                'اطلاعات اتصال سیسکو برای سرور انتخاب‌شده موجود نیست.',
                'Cisco credentials for this server are unavailable.'),
              'CISCO_PROFILE_MISSING_FIELDS' => tr(
                'آدرس یا اطلاعات ورود سیسکو ناقص است.',
                'Cisco endpoint or sign-in credentials are incomplete.'),
              'CISCO_NATIVE_START_FAILED' => tr(
                'موتور Cisco/OpenConnect نتوانست اجرا شود؛ وضعیت درایور و دسترسی مدیر را بررسی کنید.',
                'Cisco/OpenConnect could not start; check driver and Administrator access.'),
              'CISCO_PROCESS_EXITED' => tr(
                'موتور Cisco/OpenConnect قبل از تأیید اتصال بسته شد.',
                'Cisco/OpenConnect exited before the connection was verified.'),
              'CISCO_CERTIFICATE_UNTRUSTED' => tr(
                'گواهی TLS سرور سیسکو تأیید نشد؛ اتصال برای امنیت متوقف شد.',
                'Cisco server TLS certificate was not trusted; connection stopped safely.'),
              'CISCO_AUTHENTICATION_FAILED' => tr(
                'سرور سیسکو نام کاربری یا رمز عبور را نپذیرفت.',
                'Cisco server rejected the account credentials.'),
              'CISCO_ROUTE_SCRIPT_FAILED' => tr(
                'اسکریپت تنظیم شبکه OpenConnect در ویندوز خطا داد.',
                'OpenConnect Windows route/DNS script failed.'),
              'CISCO_TAP_ADAPTER_FAILED' => tr(
                'راه‌اندازی آداپتور مجازی OpenConnect در ویندوز ناموفق بود.',
                'OpenConnect virtual network adapter failed to initialize.'),
              'CISCO_POST_AUTH_TUNNEL_FAILED' => tr(
                'احراز هویت سیسکو انجام شد اما تونل یا تنظیم شبکه کامل نشد.',
                'Cisco authenticated, but tunnel or network setup did not complete.'),
              'CISCO_ENGINE_DEPENDENCY_FAILED' => tr(
                'موتور OpenConnect به علت مشکل DLL یا وابستگی ویندوز اجرا نشد.',
                'OpenConnect could not load a required Windows DLL or dependency.'),
              'CISCO_GATEWAY_UNREACHABLE' => tr(
                'ارتباط با درگاه سیسکو برقرار نشد.',
                'Cisco gateway could not be reached.'),
              'CISCO_EGRESS_NOT_VERIFIED' => tr(
                'اتصال سیسکو تأیید نشد؛ ترافیک اینترنت از تونل عبور نکرد.',
                'Cisco connection was not verified: internet traffic did not use the tunnel.'),
              'CISCO_GRACEFUL_DISCONNECT_FAILED' => tr(
                'قطع امن Cisco انجام نشد؛ تونل هنوز ممکن است فعال باشد.',
                'Cisco could not disconnect safely; the tunnel may still be active.'),
              'CISCO_ROUTE_RESTORE_UNVERIFIED' => tr(
                'سیسکو بسته شد ولی بازگشت مسیر اینترنت به حالت قبلی تأیید نشد.',
                'Cisco stopped but normal network routing was not verified.'),
              'CISCO_HEALTH_DEGRADED' => tr(
                'مسیر اینترنت سیسکو پاسخ تأییدشده ندارد.',
                'Cisco internet route is no longer verified.'),
              final code => tr(
                'خطای اتصال ${(_modernProtocol ?? _filter).toUpperCase()}: $code',
                '${(_modernProtocol ?? _filter).toUpperCase()} connection error: $code'),
            },
            style: const TextStyle(color: Colors.orangeAccent, fontSize: 11),
          ),
        ],
        TextButton.icon(
          onPressed: _vpnBusy ? null : _refreshVpnStatus,
          icon: const Icon(Icons.refresh_rounded, size: 16),
          label: Text(tr('بررسی وضعیت اتصال', 'Refresh tunnel status')),
        ),
        const SizedBox(height: 12),
        ConnectionSignalArt(dark: _dark),
        const SizedBox(height: 12),
        glassCard(
          radius: 15,
          padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 12),
          child: Row(children: [
            Expanded(child: Column(children: [
              txt(tr('مکان', 'Location'), size: 10, color: sub),
              const SizedBox(height: 4),
              Row(mainAxisAlignment: MainAxisAlignment.center, mainAxisSize: MainAxisSize.min,
                children: [
                  if (selectedServer != null) CountryFlag(selectedServer!.flag, width: 24),
                  const SizedBox(width: 6),
                  Flexible(child: txt(selectedServer?.country ?? '—', size: 11, bold: true)),
                ]),
            ])),
            Expanded(child: Column(children: [
              txt(tr('آی‌پی عمومی', 'Public IP'), size: 10, color: sub),
              const SizedBox(height: 4),
              FittedBox(
                fit: BoxFit.scaleDown,
                child: txt((_vpnVerified || _modernUp) ? (_publicIp ?? '—') : '—',
                    size: 12, bold: true),
              ),
            ])),
            Expanded(child: Column(children: [
              txt(tr('پروتکل', 'Protocol'), size: 10, color: sub),
              const SizedBox(height: 4),
              txt(_modernUp ? (VpnProtocols.byCode(_modernProtocol ?? '')?.name ?? 'sing-box') : _vpnUp ? 'WireGuard' : _filter == 'all'
                  ? tr('خودکار', 'Auto')
                  : (VpnProtocols.byCode(_filter)?.name ?? '—'),
                  size: 11, bold: true),
            ])),
          ]),
        ),
      ]),
    )));

    Widget heading(String name) => Row(children: [
      Expanded(child: txt(name, size: 24, bold: true)),
      Container(
        key: const Key('devSampleNotice'),
        child: smallPill(tr('حساب واقعی', 'Live account')),
      ),
    ]);

    Widget serverRow(int index) {
      final server = demoServers[index];
      final nodeId = widget.servers!.servers[index].id;
      // Speed belongs to the currently connected tunnel only. Other nodes
      // cannot have truthful download/upload numbers without an active test.
      final activeHere = (_vpnUp && _activeNodeId == nodeId &&
              (_filter == 'wireguard' || _filter == 'all')) ||
          (_modernUp && _modernNodeId == nodeId &&
              _modernProtocol == _filter);
      return Padding(
        padding: const EdgeInsets.only(bottom: 9),
        child: glassCard(
          key: Key('devServer_$index'),
          selected: _selected == index,
          radius: 16,
          child: Material(
            color: Colors.transparent,
            child: InkWell(
          onTap: () => _selectServerAndConnect(index),
          borderRadius: BorderRadius.circular(16),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(children: [
              IconButton(
                tooltip: tr('علاقه‌مندی', 'Favorite'),
                onPressed: () => setState(() {
                  if (!_favorites.add(index)) _favorites.remove(index);
                }),
                icon: Icon(_favorites.contains(index)
                    ? Icons.star_rounded : Icons.star_border_rounded,
                    size: 20,
                    color: _favorites.contains(index)
                        ? const Color(0xFFFFC969) : sub),
              ),
              Expanded(child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    CountryFlag(server.flag, width: 28),
                    const SizedBox(width: 9),
                    Expanded(child: txt('${server.country} · ${server.city}', bold: true)),
                  ]),
                  const SizedBox(height: 3),
                  txt(server.city, size: 10, color: sub),
                  if (activeHere) ...[
                    const SizedBox(height: 6),
                    Row(children: [
                      Icon(Icons.arrow_downward_rounded,
                        size: 12, color: const Color(0xFF00DFF5)),
                      const SizedBox(width: 3),
                      Text(_rxBytesPerSecond == null
                          ? '—' : '${_formatTransferBytes(_rxBytesPerSecond!.round())}/s',
                        key: Key('activeServerDownload_$nodeId'),
                        style: TextStyle(fontSize: 10, color: sub)),
                      const SizedBox(width: 12),
                      Icon(Icons.arrow_upward_rounded,
                        size: 12, color: const Color(0xFFC765FF)),
                      const SizedBox(width: 3),
                      Text(_txBytesPerSecond == null
                          ? '—' : '${_formatTransferBytes(_txBytesPerSecond!.round())}/s',
                        key: Key('activeServerUpload_$nodeId'),
                        style: TextStyle(fontSize: 10, color: sub)),
                    ]),
                  ],
                ],
              )),
              Tooltip(
                message: switch (_nodePingErrors[widget.servers!.servers[index].id]) {
                  'NO_PROBE_ADDRESS' => tr('پنل آدرس عمومی این سرور را ارائه نکرده است.',
                    'No public ping address was supplied for this server.'),
                  'ICMP_TIMEOUT_OR_BLOCKED' => tr('پینگ پاسخ نداد؛ ممکن است ICMP مسدود باشد.',
                    'No ping reply; ICMP may be blocked.'),
                  'PING_PROGRAM_UNAVAILABLE' => tr('دستور Ping ویندوز در دسترس نیست.',
                    'Windows Ping executable is unavailable.'),
                  'PING_FAILED' => tr('تست پینگ ناموفق بود.',
                    'Ping test failed.'),
                  'APPROXIMATE_RTT' => tr('زمان تقریبی شامل سربار اجرای Ping',
                    'Approximate timing including ping startup overhead'),
                  _ => tr('پینگ سرور', 'Server ping'),
                },
                child: Text(
                  _pingingNodes.contains(widget.servers!.servers[index].id)
                    ? '…'
                    : _nodePingErrors[widget.servers!.servers[index].id]
                        == 'NO_PROBE_ADDRESS' ? tr('بدون آدرس', 'No IP')
                    : ServerLatency.label(
                        _latencyFor(widget.servers!.servers[index]),
                        approximate: _nodePingErrors[
                          widget.servers!.servers[index].id] == 'APPROXIMATE_RTT'),
                  style: TextStyle(
                    fontSize: 11, fontWeight: FontWeight.w700,
                    color: ServerLatency.color(
                      _latencyFor(widget.servers!.servers[index])),
                  ),
                ),
              ),
              IconButton(
                key: Key('probeNode_${widget.servers!.servers[index].id}'),
                tooltip: tr('تست پینگ', 'Ping server'),
                onPressed: _pingingNodes.contains(widget.servers!.servers[index].id)
                    ? null : () => _probeNode(index),
                icon: Icon(Icons.network_ping_rounded, size: 18, color: purple),
              ),
              const SizedBox(width: 8),
              Icon(((_vpnUp && _activeNodeId == widget.servers?.servers[index].id) || (_modernUp && _modernNodeId == widget.servers?.servers[index].id))
                ? Icons.verified_rounded : Icons.chevron_right_rounded,
                size: 19, color: ((_vpnUp && _activeNodeId == widget.servers?.servers[index].id) || (_modernUp && _modernNodeId == widget.servers?.servers[index].id))
                  ? const Color(0xFF33D6A6) : sub),
            ]),
          ),
        ),
          ),
        ),
      );
    }

    Widget xrayInboundRow(int index, XrayInboundProfile inbound) {
      final server = demoServers[index];
      final nodeId = widget.servers!.servers[index].id;
      final connected = _modernUp && _modernProtocol == 'v2ray' &&
          _modernNodeId == nodeId &&
          _selectedXrayInboundId == inbound.id;
      final label = switch (inbound.id) {
        'websocket_tls' => 'WS TLS',
        'xhttp_reality' => 'XHTTP Reality',
        'tcp_tls' => 'TCP TLS',
        _ => inbound.id,
      };
      return Padding(
        padding: const EdgeInsets.only(bottom: 9),
        child: glassCard(
          key: Key('xrayInbound_${nodeId}_${inbound.id}'),
          selected: connected,
          radius: 16,
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              key: Key('connectXray_${nodeId}_${inbound.id}'),
              borderRadius: BorderRadius.circular(16),
              onTap: _vpnBusy ? null : () {
                setState(() {
                  _selected = index;
                  _selectedXrayNodeId = nodeId;
                  _selectedXrayInboundId = inbound.id;
                  _filter = 'v2ray';
                  _page = 'home';
                  _autoFastest = false;
                  _vpnError = null;
                });
                _startXrayTunnel(nodeId, inboundId: inbound.id);
              },
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 14, vertical: 13),
                child: Row(children: [
                  CountryFlag(server.flag, width: 28),
                  const SizedBox(width: 10),
                  Expanded(child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      txt('${server.country} · $label', bold: true),
                      const SizedBox(height: 3),
                      txt('V2Ray / Xray', size: 10, color: sub),
                    ],
                  )),
                  const SizedBox(width: 8),
                  Tooltip(
                    message: tr(
                      'زمان برقراری TCP با پورت اینباند، نه پینگ ICMP',
                      'TCP handshake to inbound port, not ICMP ping',
                    ),
                    child: Text(
                      _xrayInboundsProbing.contains(
                          XrayInboundLatency.key(inbound))
                          ? '…'
                          : _xrayInboundRtts.containsKey(
                              XrayInboundLatency.key(inbound)) &&
                              _xrayInboundRtts[XrayInboundLatency.key(inbound)] == null
                              ? tr('بدون پاسخ', 'No reply')
                              : ServerLatency.label(
                                  _xrayInboundRtts[XrayInboundLatency.key(inbound)]),
                      key: Key('xrayRtt_${nodeId}_${inbound.id}'),
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: ServerLatency.color(
                            _xrayInboundRtts[XrayInboundLatency.key(inbound)]),
                      ),
                    ),
                  ),
                  IconButton(
                    key: Key('probeXray_${nodeId}_${inbound.id}'),
                    tooltip: tr('تست پورت اینباند', 'Probe inbound TCP port'),
                    onPressed: _xrayInboundsProbing.contains(
                            XrayInboundLatency.key(inbound))
                        ? null : () => _probeXrayInbound(inbound),
                    icon: Icon(Icons.network_ping_rounded,
                        color: purple, size: 18),
                  ),
                  const SizedBox(width: 4),
                  Icon(connected ? Icons.verified_rounded :
                    Icons.power_settings_new_rounded,
                    size: 20,
                    color: connected ? const Color(0xFF33D6A6) : purple),
                ]),
              ),
            ),
          ),
        ),
      );
    }

    // All 16 chips remain visible. Admin-selected protocols will replace
    // the preview's complete catalog after an authenticated panel session.
    Widget fastestServerControl() => Container(
      key: const Key('liveAutoFastestServer'),
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 5),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: purple.withValues(alpha: _dark ? .12 : .06),
        border: Border.all(color: purple.withValues(alpha: .32)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(Icons.auto_awesome_rounded, color: purple, size: 17),
        const SizedBox(width: 6),
        Text(tr('سریع‌ترین سرور', 'Fastest server'),
          style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700,
            color: ink)),
        const SizedBox(width: 4),
        Tooltip(
          message: _filter == 'all'
            ? tr('ابتدا یک پروتکل انتخاب کنید', 'Choose a protocol first')
            : _fastestKnownIndex == null
            ? tr('پینگ معتبر موجود نیست', 'No measured server latency')
            : tr('انتخاب بر اساس پینگ اندازه‌گیری‌شده',
                 'Select by measured server latency'),
          child: Switch(
            key: const Key('autoFastestServerToggle'),
            value: _autoFastest,
            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            onChanged: _vpnBusy || _vpnUp || _modernUp
                ? null : (enabled) {
              if (enabled && _filter == 'all') {
                ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                  content: Text(tr('ابتدا یک پروتکل انتخاب کنید.',
                    'Choose a protocol before enabling fastest server.'))));
                return;
              }
              final allowed = widget.catalog?.entries.any((entry) =>
                entry.protocol.code == _filter && entry.selected &&
                entry.configRecordPresent) ?? false;
              if (enabled && !allowed) {
                ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                  content: Text(tr('کانفیگ مجاز این پروتکل موجود نیست.',
                    'No authorized configuration for this protocol.'))));
                return;
              }
              final best = _fastestKnownIndex;
              if (enabled && best == null) {
                ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                  content: Text(tr('برای انتخاب خودکار، پینگ معتبر لازم است.',
                    'Measured server latency is required.'))));
                return;
              }
              setState(() {
                _autoFastest = enabled;
                if (enabled) {
                  _selected = best!;
                }
              });
            },
          ),
        ),
      ]),
    );

    Widget filters() => Container(
      key: const Key('devProtocolFilters'),
      width: double.infinity,
      alignment: AlignmentDirectional.centerStart,
      child: Wrap(
        alignment: WrapAlignment.start,
        runSpacing: 8,
        spacing: 7,
        children: [
          for (final entry in <(String, String)>[
            ('all', tr('همه', 'All')),
            for (final p in VpnProtocols.all) (p.code, p.name),
          ])
            ChoiceChip(
              key: Key('devFilter_${entry.$1}'),
              label: txt(entry.$2, size: 11,
                color: _filter == entry.$1 ? Colors.white : ink),
              selected: _filter == entry.$1,
              showCheckmark: false,
              selectedColor: _dark
                  ? const Color(0xFF7640C9) : const Color(0xFF7844C7),
              backgroundColor: panel,
              side: BorderSide(color: _filter == entry.$1 ? purple : line),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12)),
              onSelected: (_) {
                setState(() {
                  // An automatic choice is valid only for its selected protocol.
                  _filter = entry.$1;
                  _autoFastest = false;
                });
                if (entry.$1 == 'v2ray') _loadXrayGroups();
              },
            ),
        ],
      ),
    );

    Widget locations() {
      final query = _search.trim().toLowerCase();
      final matching = <int>[
        for (int i = 0; i < demoServers.length; i++)
          if (query.isEmpty ||
              ('${demoServers[i].country} ${demoServers[i].city} '
               '${_countryLabel(demoServers[i].flag)}')
                .toLowerCase().contains(query))
            i,
      ];
      final grouped = <String, List<int>>{};
      for (final i in matching) {
        final country = CountryFlag.normalizedCode(demoServers[i].flag);
        grouped.putIfAbsent(country, () => <int>[]).add(i);
      }
      Widget countryGroup(String country, List<int> indices) {
        final inboundCount = _filter == 'v2ray'
            ? indices.fold<int>(0, (total, i) => total +
                _inboundsForNode(widget.servers!.servers[i].id).length)
            : indices.length;
        final opened = query.isNotEmpty || _expandedCountries.contains(country);
        final connectedInGroup = indices.any((i) {
          final id = widget.servers?.servers[i].id;
          return (_vpnUp && _activeNodeId == id) ||
              (_modernUp && _modernNodeId == id);
        });
        return Padding(
          key: Key('countryGroup_$country'),
          padding: const EdgeInsets.only(bottom: 10),
          child: glassCard(
            radius: 17,
            child: Column(children: [
              Material(
                color: Colors.transparent,
                child: InkWell(
                  key: Key('countryToggle_$country'),
                  borderRadius: BorderRadius.circular(16),
                  onTap: () => setState(() {
                    if (!_expandedCountries.add(country)) {
                      _expandedCountries.remove(country);
                    }
                  }),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 15, vertical: 15),
                    child: Row(children: [
                      CountryFlag(country, width: 30),
                      const SizedBox(width: 12),
                      Expanded(child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          txt(_countryLabel(country), bold: true, size: 14),
                          const SizedBox(height: 3),
                          txt(tr('$inboundCount سرور', '$inboundCount servers'),
                              size: 11, color: sub),
                        ],
                      )),
                      if (connectedInGroup)
                        Icon(Icons.verified_rounded,
                            color: const Color(0xFF32D5A5), size: 20),
                      const SizedBox(width: 10),
                      AnimatedRotation(
                        turns: opened ? .5 : 0,
                        duration: const Duration(milliseconds: 230),
                        child: Icon(Icons.keyboard_arrow_down_rounded,
                            color: sub, size: 25),
                      ),
                    ]),
                  ),
                ),
              ),
              AnimatedSize(
                duration: const Duration(milliseconds: 260),
                curve: Curves.easeInOutCubic,
                alignment: Alignment.topCenter,
                child: opened
                    ? Padding(
                        padding: const EdgeInsets.fromLTRB(9, 0, 9, 7),
                        child: Column(children: [
                          Divider(color: line),
                          for (final i in indices)
                             if (_filter == 'v2ray')
                               for (final inbound in
                                   _inboundsForNode(widget.servers!.servers[i].id))
                                 xrayInboundRow(i, inbound)
                             else
                               serverRow(i),
                        ]),
                      )
                    : const SizedBox(width: double.infinity),
              ),
            ]),
          ),
        );
      }
      return glassCard(
        key: const Key('devLocationListingCard'),
        radius: 23,
        padding: const EdgeInsets.all(16),
        child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          heading(tr('مکان‌ها', 'Locations')),
          const SizedBox(height: 16),
          Row(children: [
            Expanded(child: SizedBox(height: 46, child: TextField(
              key: const Key('devProtocolSearch'),
              onChanged: (value) => setState(() => _search = value),
              decoration: InputDecoration(
                isDense: true,
                hintText: tr('جستجوی سرور', 'Search servers'),
                prefixIcon: const Icon(Icons.search_rounded),
                filled: true,
                fillColor: panel,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(13)),
              ),
            ))),
            const SizedBox(width: 6),
            IconButton(
              key: const Key('devRefreshServers'),
              tooltip: tr('به‌روزرسانی', 'Refresh'),
              onPressed: () {
                widget.onRefresh();
                if (_filter == 'v2ray') _loadXrayGroups(refresh: true);
                _probeAllNodes();
              },
              icon: const Icon(Icons.refresh_rounded),
            ),
          ]),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: _pingAllBusy ? null : () {
              _probeAllNodes();
              if (_filter == 'v2ray') _probeAllXrayInbounds();
            },
            icon: const Icon(Icons.network_ping_rounded),
            label: Text(tr('تست پینگ همه سرورها', 'Ping all servers')),
          ),
          const SizedBox(height: 13),
          filters(),
          const SizedBox(height: 10),
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: fastestServerControl(),
          ),
          const SizedBox(height: 12),
          if (_filter == 'v2ray' && _xrayGroupsLoading)
            const Padding(
              padding: EdgeInsets.all(12),
              child: Center(child: CircularProgressIndicator()),
            ),
          if (_filter == 'v2ray' && _xrayGroupsError != null)
            TextButton.icon(
              onPressed: () => _loadXrayGroups(refresh: true),
              icon: const Icon(Icons.refresh_rounded),
              label: Text(tr('دریافت دوباره اینباندها', 'Retry loading inbounds')),
            ),
          for (final country in grouped.keys)
            countryGroup(country, grouped[country]!),
          if (widget.serverRefreshError != null)
            Padding(
              padding: const EdgeInsets.all(18),
              child: Column(children: [
                txt(widget.serverRefreshError == 'APP_SESSION_EXPIRED'
                  ? tr('نشست ورود منقضی شده است. برای دریافت سرورها دوباره وارد حساب شوید.',
                       'Session expired. Sign in again to restore servers.')
                  : tr('دریافت فهرست سرورها ناموفق بود. اتصال پنل را بررسی و دوباره تلاش کنید.',
                       'Server refresh failed. Check panel access and retry.'),
                  align: TextAlign.center, color: const Color(0xFFFFBE67)),
                const SizedBox(height: 8),
                OutlinedButton.icon(
                  onPressed: widget.onRefresh,
                  icon: const Icon(Icons.refresh_rounded),
                  label: Text(tr('تلاش دوباره', 'Retry')),
                ),
              ]),
            )
          else if (matching.isEmpty)
            Padding(
              padding: const EdgeInsets.all(22),
              child: txt(widget.servers == null
                ? tr('در حال دریافت سرورها...', 'Loading servers...')
                : tr('سروری پیدا نشد', 'No servers found'),
                align: TextAlign.center, color: sub),
            ),
        ],
        ),
      );
    }

    Widget metric(IconData icon, String title, String value,
        {String? detail}) => glassCard(
      radius: 17,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(icon, color: purple, size: 18),
            const SizedBox(width: 8),
            Expanded(child: txt(title, size: 11, color: sub)),
          ]),
          const SizedBox(height: 16),
          txt(value, size: 18, bold: true),
          if (detail != null) ...[
            const SizedBox(height: 4),
            txt(detail, size: 10, color: sub),
          ],
        ],
      ),
    );

    Widget trafficCard(IconData icon, String label,
        double? bytesPerSecond, List<double> history, String total,
        Color color) => glassCard(
      radius: 19,
      padding: const EdgeInsets.fromLTRB(12, 13, 12, 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(9),
                color: color.withValues(alpha: .13)),
              child: Icon(icon, color: color, size: 19)),
            const SizedBox(width: 7),
            Expanded(child: Text(label, overflow: TextOverflow.ellipsis,
              style: TextStyle(color: ink, fontSize: 12,
                fontWeight: FontWeight.w700))),
          ]),
          const SizedBox(height: 10),
          Text(bytesPerSecond == null ? '—'
              : _formatTransferBytes(bytesPerSecond.round()) + '/s',
            maxLines: 1, overflow: TextOverflow.ellipsis,
            style: TextStyle(color: ink, fontSize: 19,
              fontWeight: FontWeight.w800)),
          const SizedBox(height: 9),
          TunnelTrafficChart(samples: history,
            color: color, dark: _dark, height: 49),
          const SizedBox(height: 7),
          Text(tr('کل این اتصال: ', 'Session total: ') + total,
            maxLines: 1, overflow: TextOverflow.ellipsis,
            style: TextStyle(color: sub, fontSize: 10)),
        ],
      ),
    );

    Widget connectionStats() => glassCard(
      key: const Key('devConnectionStats'),
      radius: 23,
      padding: const EdgeInsets.all(22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Expanded(child: txt(tr('وضعیت شبکه', 'Network status'),
              size: 17, bold: true)),
            smallPill(_modernUp ? tr('تونل فعال', 'Tunnel active') :
                _vpnVerified ? tr('دست‌دهی تأیید شد', 'Handshake verified') :
                _vpnUp ? tr('رابط فعال', 'Interface active') :
                tr('قطع', 'Disconnected')),
          ]),
          const SizedBox(height: 23),
          Row(children: [
            Expanded(child: glassCard(
              radius: 17,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Icon(Icons.speed_rounded, color: purple, size: 18),
                    const SizedBox(width: 8),
                    Expanded(child: txt(tr('پینگ سرور', 'Server ping'),
                        size: 11, color: sub)),
                  ]),
                  const SizedBox(height: 16),
                  Text(ServerLatency.label(_connectedServerRtt),
                    style: TextStyle(
                      fontSize: 18, fontWeight: FontWeight.bold,
                      color: ServerLatency.color(_connectedServerRtt))),
                  const SizedBox(height: 5),
                  Text(_vpnVerified && _httpsLatencyMs != null
                    ? 'HTTPS: $_httpsLatencyMs ms'
                    : _modernUp && _modernProtocol == 'v2ray' &&
                          _connectedServerRtt != null
                          ? tr('زمان برقراری TCP اینباند', 'Inbound TCP handshake time')
                          : tr('زمان پاسخ ICMP', 'ICMP round-trip time'),
                    style: TextStyle(fontSize: 10, color: sub)),
                ],
              ),
            )),
            const SizedBox(width: 10),
            Expanded(child: metric(Icons.public_rounded,
              tr('آی‌پی عمومی', 'Public IP'),
              (_vpnVerified || _modernUp) ? (_publicIp ?? '—') : '—')),
          ]),
          const SizedBox(height: 18),
          Row(children: [
            Expanded(child: trafficCard(
              Icons.arrow_downward_rounded,
              tr('دانلود', 'Download'),
              _rxBytesPerSecond, _rxHistory,
              _modernUp
                  ? (_modernRx == null ? '—'
                      : _formatTransferBytes(_modernRx!))
                  : _vpnUp ? _formatTransferBytes(_vpnRx) : '—',
              const Color(0xFF00DFF5))),
            const SizedBox(width: 10),
            Expanded(child: trafficCard(
              Icons.arrow_upward_rounded,
              tr('آپلود', 'Upload'),
              _txBytesPerSecond, _txHistory,
              _modernUp
                  ? (_modernTx == null ? '—'
                      : _formatTransferBytes(_modernTx!))
                  : _vpnUp ? _formatTransferBytes(_vpnTx) : '—',
              const Color(0xFFC765FF))),
          ]),
          const SizedBox(height: 25),
          glassCard(
            radius: 14,
            padding: const EdgeInsets.all(12),
            child: Row(children: [
              if (selectedServer != null) CountryFlag(selectedServer!.flag, width: 30),
              const SizedBox(width: 9),
              Expanded(child: txt(selectedServer?.country ?? '—', bold: true)),
              txt(tr('از پنل', 'Panel'), color: sub, size: 10),
            ]),
          ),
        ],
      ),
    );

    // Main connection page: compact, real subscription lifecycle details.
    // The account page still owns the full breakdown and edit/refresh actions.
    // A missing snapshot displays dashes, never fictitious quota/dates.
    Widget homeSubscriptionSummary() {
      final account = widget.account;
      final used = account?.trafficUsedBytes ?? 0;
      final limit = account?.trafficLimitBytes ?? 0;
      final unlimited = account != null && limit <= 0;
      final fraction = account == null || limit <= 0
          ? 0.0 : (used / limit).clamp(0.0, 1.0);
      final expiry = account?.expiresAt;
      final days = expiry?.difference(DateTime.now()).inDays;
      final total = account == null ? '—'
          : unlimited ? tr('نامحدود', 'Unlimited') : _formatBytes(limit);
      final remaining = account == null ? '—'
          : unlimited ? tr('نامحدود', 'Unlimited')
          : _formatBytes((limit - used).clamp(0, limit).toInt());
      final daysLabel = account == null ? '—' : expiry == null
          ? (account.activationDurationDays != null &&
                 account.activationDurationDays! > 0
              ? tr('پس از اولین اتصال', 'After first connection')
              : tr('نامحدود', 'Unlimited'))
          : days == null ? '—' : days < 0
              ? tr('منقضی', 'Expired')
              : tr('${days + 1} روز', '${days + 1} days');
      const cyan = Color(0xFF00DCF5);
      const magenta = Color(0xFFC965FF);

      Widget infoTile(Key key, IconData icon, String label,
          String value, Color accent) => Container(
        key: key,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          color: accent.withValues(alpha: _dark ? .075 : .045),
          border: Border.all(color: accent.withValues(alpha: .22)),
        ),
        child: Row(children: [
          Icon(icon, color: accent, size: 20),
          const SizedBox(width: 9),
          Expanded(child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, maxLines: 1, overflow: TextOverflow.ellipsis,
                style: TextStyle(color: sub, fontSize: 10)),
              const SizedBox(height: 4),
              Text(value, maxLines: 1, overflow: TextOverflow.ellipsis,
                style: TextStyle(color: ink, fontSize: 14,
                  fontWeight: FontWeight.w800)),
            ],
          )),
        ]),
      );

      final usage = Container(
        key: const Key('liveHomeUsageCompact'),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          color: purple.withValues(alpha: _dark ? .12 : .05),
          border: Border.all(color: purple.withValues(alpha: .23)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min, children: [
            Row(children: [
              Icon(Icons.data_usage_rounded, color: purple, size: 19),
              const SizedBox(width: 7),
              Expanded(child: Text(tr('حجم مصرفی', 'Data usage'),
                maxLines: 1, overflow: TextOverflow.ellipsis,
                style: TextStyle(color: sub, fontSize: 10))),
            ]),
            const SizedBox(height: 5),
            Row(children: [
              Flexible(child: Text(
                account == null ? '—' : _formatBytes(used),
                maxLines: 1, overflow: TextOverflow.ellipsis,
                style: TextStyle(color: ink, fontSize: 16,
                  fontWeight: FontWeight.w800))),
              const SizedBox(width: 5),
              Flexible(child: Text('/ $total',
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: sub, fontSize: 10))),
            ]),
            const SizedBox(height: 7),
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: LinearProgressIndicator(
                key: const Key('liveHomeDataProgress'),
                value: fraction,
                minHeight: 5,
                color: fraction >= .9
                  ? const Color(0xFFFFB26B) : purple,
                backgroundColor: purple.withValues(alpha: .16))),
            const SizedBox(height: 5),
            Text(tr('باقی‌مانده: ', 'Remaining: ') + remaining,
              maxLines: 1, overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: cyan, fontSize: 10)),
          ]),
      );

      final expiryTile = infoTile(const Key('liveHomeExpiryChip'),
        Icons.event_outlined, tr('تاریخ انقضا', 'Expiry date'),
        _expiryLabel(), magenta);
      final daysTile = infoTile(const Key('liveHomeTimeChip'),
        Icons.timelapse_rounded, tr('زمان باقی‌مانده', 'Time remaining'),
        daysLabel, cyan);

      return glassCard(
        key: const Key('liveHomeSubscriptionSummary'),
        radius: 20,
        padding: const EdgeInsets.fromLTRB(13, 11, 13, 13),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min, children: [
            Row(children: [
              Icon(Icons.shield_outlined, color: purple, size: 19),
              const SizedBox(width: 8),
              Expanded(child: txt(tr('وضعیت اشتراک', 'Subscription details'),
                size: 13, bold: true)),
              if (account != null)
                Text(unlimited ? tr('نامحدود', 'Unlimited')
                    : tr('حجمی', 'Metered'),
                  style: const TextStyle(color: cyan, fontSize: 10)),
              const SizedBox(width: 4),
              IconButton(
                key: const Key('liveHomeRefreshAccount'),
                tooltip: tr('به‌روزرسانی اشتراک', 'Refresh subscription'),
                onPressed: widget.onRefreshAccount,
                visualDensity: VisualDensity.compact,
                constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                icon: Icon(Icons.refresh_rounded, size: 19, color: purple)),
            ]),
            const SizedBox(height: 6),
            LayoutBuilder(builder: (context, constraints) {
              if (constraints.maxWidth < 620) {
                return Column(children: [
                  usage, const SizedBox(height: 8),
                  Row(children: [
                    Expanded(child: expiryTile), const SizedBox(width: 8),
                    Expanded(child: daysTile),
                  ]),
                ]);
              }
              return Row(crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Expanded(flex: 5, child: usage),
                  const SizedBox(width: 9),
                  Expanded(flex: 3, child: expiryTile),
                  const SizedBox(width: 9),
                  Expanded(flex: 3, child: daysTile),
                ]);
            }),
            if (widget.accountError != null) ...[
              const SizedBox(height: 7),
              txt(tr('اطلاعات اشتراک در دسترس نیست؛ دوباره تلاش کنید.',
                'Account details unavailable. Please refresh.'),
                size: 10, color: const Color(0xFFFFB878)),
            ],
          ],
        ),
      );
    }


    Widget home() => Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        heading(tr('اتصال سریع', 'Quick connect')),
        const SizedBox(height: 16),
        LayoutBuilder(builder: (context, constraints) {
          final split = constraints.maxWidth >= 740;
          if (!split) {
            return Column(children: [
              powerCard(),
              const SizedBox(height: 12),
              connectionStats(),
            ]);
          }
          return Directionality(
            textDirection: TextDirection.ltr,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(flex: 5, child: Directionality(
                  textDirection: _persian ? TextDirection.rtl : TextDirection.ltr,
                  child: powerCard(),
                )),
                const SizedBox(width: 14),
                Expanded(flex: 5, child: Directionality(
                  textDirection: _persian ? TextDirection.rtl : TextDirection.ltr,
                  child: connectionStats(),
                )),
              ],
            ),
          );
        }),
        const SizedBox(height: 15),
        homeSubscriptionSummary(),

      ],
    );

    Widget settingLine(IconData icon, String title,
        {bool disabled = true, VoidCallback? onTap}) => Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: glassCard(
        radius: 17,
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Material(
          color: Colors.transparent,
          child: ListTile(
            leading: Container(
              width: 37,
              height: 37,
              decoration: BoxDecoration(
                color: purple.withValues(alpha: _dark ? .17 : .10),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: purple, size: 20),
            ),
            title: txt(title, bold: true),
            subtitle: disabled
                ? txt(tr('در این نسخه غیرفعال', 'Unavailable in preview'),
                    color: sub, size: 10)
                : null,
            trailing: disabled
                ? const Switch(value: false, onChanged: null)
                : Icon(Icons.chevron_right_rounded, color: sub),
            onTap: onTap,
          ),
        ),
      ),
    );

    Widget settings() => Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        heading(tr('تنظیمات', 'Settings')),
        const SizedBox(height: 15),
        glassCard(
          key: const Key('devSettingsGlassHeader'),
          radius: 22,
          padding: const EdgeInsets.symmetric(horizontal: 19, vertical: 19),
          child: Row(children: [
            Container(
              height: 48, width: 48,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                color: purple.withValues(alpha: .17),
              ),
              child: Icon(Icons.tune_rounded, color: purple, size: 24),
            ),
            const SizedBox(width: 13),
            Expanded(child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                txt(tr('تنظیمات اتصال', 'Connection preferences'),
                    size: 16, bold: true),
                const SizedBox(height: 5),
                txt(tr('قابلیت‌های امنیتی فقط پس از تأیید موتور ویندوز فعال می‌شوند',
                       'Security controls require verified Windows engine support'),
                    size: 11, color: sub),
              ],
            )),
          ]),
        ),
        const SizedBox(height: 17),
        settingLine(
          Icons.shield_outlined,
          tr('تنظیمات امنیت و VPN', 'VPN and security settings'),
          disabled: false,
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => VpnSettingsScreen(
                tenant: widget.panel.namespace,
                account: widget.username,
              ),
            ),
          ),
        ),
        glassCard(
          key: const Key('settingsSecurityStatus'),
          radius: 18,
          padding: const EdgeInsets.all(15),
          child: Row(children: [
            const Icon(Icons.gpp_maybe_outlined,
                color: Color(0xFFFFB66A), size: 23),
            const SizedBox(width: 12),
            Expanded(child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                txt(tr('Kill Switch هنوز تأیید نشده',
                    'Kill Switch not yet enforced'),
                    size: 13, bold: true),
                const SizedBox(height: 4),
                txt(tr('تا زمانی که محافظت شبکه در ویندوز اجرا و تأیید نشود،'
                       ' این کلید فعال نخواهد شد.',
                       'The switch stays unavailable until OS-level traffic'
                       ' blocking is implemented and verified.'),
                       color: sub, size: 11),
              ],
            )),
          ]),
        ),
        const SizedBox(height: 14),
        settingLine(
          Icons.hub_outlined,
          tr('بررسی نصب موتور پروتکل‌های مدرن', 'Check modern engine installation'),
          disabled: false,
          onTap: () async {
            final installed = await WindowsSingBoxPreflight.enginePresent();
            if (!context.mounted) return;
            ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text(installed
                  ? tr('موتور sing-box نصب است؛ کنترل تونل هنوز فعال نشده است.',
                       'sing-box is installed, but the native tunnel controller is not enabled.')
                  : tr('موتور sing-box در نصب فعلی پیدا نشد.',
                       'sing-box was not found in this installation.')),
            ));
          },
        ),
        settingLine(
          Icons.speed_rounded,
          tr('بررسی وضعیت واقعی اتصال', 'Check live VPN status'),
          disabled: false,
          onTap: () {
            _refreshVpnStatus();
            setState(() => _page = 'home');
          },
        ),
        settingLine(
          Icons.auto_awesome_rounded,
          tr('انتخاب سریع‌ترین سرور', 'Fastest server selection'),
          disabled: false,
          onTap: () {
            setState(() => _page = 'home');
            if (_fastestKnownIndex == null) {
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                content: Text(tr('ابتدا از بخش مکان‌ها پینگ سرورها را تست کنید.',
                    'Test server latencies in Locations first.'))));
            }
          },
        ),
        settingLine(
          Icons.refresh_rounded,
          tr('به‌روزرسانی اطلاعات حساب و سرورها',
             'Refresh account and servers'),
          disabled: false,
          onTap: () {
            widget.onRefreshAccount();
            widget.onRefresh();
            _probeAllNodes();
            ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text(tr('درخواست به‌روزرسانی ارسال شد.',
                'Refresh requested.')),
            ));
          },
        ),
        const SizedBox(height: 16),
        ShareVpnPreview(
          key: const Key('devShareVpnSection'),
          dark: _dark,
          persian: _persian,
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          key: const Key('settingsSignOut'),
          onPressed: _vpnBusy ? null : _disconnectAndSignOut,
          icon: const Icon(Icons.logout_rounded),
          label: Text(tr('خروج از حساب', 'Sign out')),
        ),
        if (_vpnUp || _vpnCleanup || _vpnBusy)
          Padding(
            padding: const EdgeInsets.only(top: 7),
            child: Text(tr('خروج، ابتدا اتصال VPN را قطع می‌کند.',
                'Signing out will disconnect the VPN first.'),
                style: TextStyle(color: sub, fontSize: 11)),
          ),
        const SizedBox(height: 16),
        glassCard(
          key: const Key('devSettingsAppearanceCard'),
          radius: 20,
          padding: const EdgeInsets.fromLTRB(15, 12, 15, 12),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              txt(tr('شخصی‌سازی', 'Personalization'), size: 15, bold: true),
              const SizedBox(height: 10),
              settingLine(Icons.language_rounded, tr('زبان', 'Language'),
                  disabled: false,
                  onTap: _changeLanguage),
              settingLine(Icons.palette_outlined, tr('ظاهر', 'Appearance'),
                  disabled: false,
                  onTap: _changeAppearance),
              settingLine(Icons.sync_rounded,
                  tr('دریافت برند از پنل: ${widget.brand.brandName}',
                     'Sync panel brand: ${widget.brand.brandName}'),
                  disabled: widget.onBrandRefresh == null,
                  onTap: () async {
                    final success = await widget.onBrandRefresh?.call() ?? false;
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(success
                        ? tr('برند از پنل دریافت شد.',
                             'Brand synchronized from the panel.')
                        : tr('دریافت برند ناموفق بود؛ آخرین تنظیمات معتبر حفظ شد.',
                             'Could not sync brand; last verified brand kept.')),
                    ));
                  }),
            ],
          ),
        ),
      ],
    );


    Widget account() {
      final current = widget.account;
      final limit = current?.trafficLimitBytes ?? 0;
      final used = current?.trafficUsedBytes ?? 0;
      final hasLimit = current != null && limit > 0;
      final fraction = hasLimit ? (used / limit).clamp(0.0, 1.0) : 0.0;
      final daysLeft = current?.expiresAt?.difference(DateTime.now()).inDays;
      final expiryText = _expiryLabel();
      final deviceText = widget.plan == null ? '—' :
          widget.plan!.deviceLimit == 0 ? tr('نامحدود', 'Unlimited')
          : '${widget.plan!.deviceLimit}';
      final active = current?.status.toLowerCase() == 'active';
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Expanded(child: heading(tr('حساب من', 'My account'))),
            IconButton(
              tooltip: tr('به‌روزرسانی حساب', 'Refresh account'),
              onPressed: widget.onRefreshAccount,
              icon: Icon(Icons.refresh_rounded, color: purple),
            ),
          ]),
          const SizedBox(height: 16),
          glassCard(
            key: const Key('accountIdentityCard'),
            radius: 25,
            padding: const EdgeInsets.all(23),
            child: Row(children: [
              Container(
                height: 64, width: 64,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(19),
                  gradient: const LinearGradient(
                    colors: [Color(0xFFAA7AFF), Color(0xFF6953D7)],
                  ),
                ),
                child: const Icon(Icons.shield_outlined,
                    color: Colors.white, size: 33),
              ),
              const SizedBox(width: 16),
              Expanded(child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(widget.username, maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(color: ink,
                      fontSize: 16, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 9),
                  Row(children: [
                    Icon(active ? Icons.verified_rounded : Icons.info_outline,
                        size: 16, color: active
                            ? const Color(0xFF31D3B4) : purple),
                    const SizedBox(width: 5),
                    Flexible(child: txt(current == null
                        ? tr('دریافت اطلاعات حساب', 'Loading account details')
                        : active ? tr('اشتراک فعال', 'Active subscription')
                        : current.status,
                        size: 12, color: sub)),
                  ]),
                ],
              )),
            ]),
          ),
          const SizedBox(height: 15),
          glassCard(
            key: const Key('accountTrafficCard'),
            radius: 24,
            padding: const EdgeInsets.all(23),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: purple.withValues(alpha: .17),
                      borderRadius: BorderRadius.circular(13)),
                    child: Icon(Icons.data_usage_rounded, color: purple),
                  ),
                  const SizedBox(width: 12),
                  Expanded(child: txt(tr('حجم مصرف‌شده', 'Data usage'),
                      size: 15, bold: true)),
                  if (current != null && !hasLimit)
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 7),
                      decoration: BoxDecoration(
                        color: const Color(0xFF2ACFAE).withValues(alpha: .13),
                        borderRadius: BorderRadius.circular(30)),
                      child: Text(tr('نامحدود', 'Unlimited'),
                        style: const TextStyle(color: Color(0xFF33D9B9),
                          fontSize: 11, fontWeight: FontWeight.bold)),
                    ),
                ]),
                const SizedBox(height: 20),
                // Always show used / total. An unlimited subscription
                // must explicitly read "Unlimited", not "Total usage".
                Wrap(
                  crossAxisAlignment: WrapCrossAlignment.center,
                  spacing: 9,
                  runSpacing: 4,
                  children: [
                    Text(current == null ? '—' : _formatBytes(used),
                      style: TextStyle(color: ink, fontSize: 30,
                        fontWeight: FontWeight.w800)),
                    Text('/',
                      style: TextStyle(color: sub, fontSize: 20)),
                    Text(current == null ? '—' :
                        hasLimit ? _formatBytes(limit)
                          : tr('نامحدود', 'Unlimited'),
                      style: TextStyle(color: hasLimit ? ink
                        : const Color(0xFF33D9B9), fontSize: 18,
                        fontWeight: FontWeight.w700)),
                  ],
                ),
                const SizedBox(height: 8),
                Row(children: [
                  Icon(Icons.account_balance_wallet_outlined,
                    color: hasLimit ? purple
                      : const Color(0xFF33D9B9), size: 17),
                  const SizedBox(width: 8),
                  Expanded(child: Text(
                    current == null
                      ? tr('باقی‌مانده: نامشخص', 'Remaining: unavailable')
                      : hasLimit
                        ? tr('باقی‌مانده: ${_formatBytes((limit - used).clamp(0, limit).toInt())}',
                             'Remaining: ${_formatBytes((limit - used).clamp(0, limit).toInt())}')
                        : tr('باقی‌مانده: نامحدود', 'Remaining: Unlimited'),
                    style: TextStyle(color: sub, fontSize: 13,
                        fontWeight: FontWeight.w600),
                  )),
                ]),
                const SizedBox(height: 18),
                ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: LinearProgressIndicator(
                    minHeight: 9,
                    value: hasLimit ? fraction : 0,
                    backgroundColor: purple.withValues(alpha: .13),
                    valueColor: AlwaysStoppedAnimation<Color>(
                      hasLimit && fraction >= .9
                          ? const Color(0xFFFFB26B)
                          : const Color(0xFF9B6CF1)),
                  ),
                ),
                const SizedBox(height: 10),
                txt(current == null
                    ? tr('در حال دریافت حجم از پنل', 'Fetching usage from panel')
                    : hasLimit
                        ? tr('${(fraction * 100).toStringAsFixed(1)}٪ مصرف‌شده',
                            '${(fraction * 100).toStringAsFixed(1)}% used')
                        : tr('بدون سقف ترافیک', 'No traffic cap'),
                    size: 11, color: sub),
              ],
            ),
          ),
          const SizedBox(height: 15),
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(child: glassCard(
              key: const Key('accountExpiryCard'),
              radius: 22,
              padding: const EdgeInsets.all(19),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.calendar_month_rounded, color: purple,
                    size: 25),
                  const SizedBox(height: 14),
                  txt(tr('تاریخ انقضا', 'Expires on'), size: 12, color: sub),
                  const SizedBox(height: 6),
                  Text(expiryText, maxLines: 2,
                    style: TextStyle(fontWeight: FontWeight.bold,
                      color: ink, fontSize: 16)),
                  if (daysLeft != null) ...[
                    const SizedBox(height: 6),
                    Text(daysLeft < 0 ? tr('منقضی‌شده', 'Expired')
                      : tr('${daysLeft + 1} روز باقی‌مانده',
                           '${daysLeft + 1} days remaining'),
                      style: TextStyle(fontSize: 11,
                        color: daysLeft < 0
                          ? const Color(0xFFFFAC80) : sub)),
                  ],
                ],
              ),
            )),
            const SizedBox(width: 12),
            Expanded(child: glassCard(
              key: const Key('accountDeviceCard'),
              radius: 22,
              padding: const EdgeInsets.all(19),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.devices_other_rounded, color: purple,
                    size: 25),
                  const SizedBox(height: 14),
                  txt(tr('دستگاه‌های مجاز', 'Device limit'),
                    size: 12, color: sub),
                  const SizedBox(height: 6),
                  Text(deviceText, style: TextStyle(color: ink,
                    fontSize: 22, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 6),
                  txt(tr('براساس پلن اشتراک', 'From subscription plan'),
                    size: 11, color: sub),
                ],
              ),
            )),
          ]),
          if (widget.accountError != null) ...[
            const SizedBox(height: 12),
            Text(tr('دریافت اطلاعات حساب ناموفق بود؛ دوباره تلاش کنید.',
                    'Account details unavailable. Please refresh.'),
                style: const TextStyle(color: Colors.orangeAccent)),
          ],
          const SizedBox(height: 18),
          OutlinedButton.icon(
            onPressed: _vpnBusy ? null : _disconnectAndSignOut,
            icon: const Icon(Icons.logout_rounded),
            label: Text(tr('خروج از حساب', 'Sign out')),
          ),
          if (_vpnUp || _vpnBusy || _vpnCleanup)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: txt(tr('با خروج، اتصال VPN ابتدا به‌صورت امن قطع می‌شود.',
                    'Signing out safely disconnects VPN first.'),
                  color: sub, size: 11)),
        ],
      );
    }

    Widget content() => switch (_page) {
      'locations' => locations(),
      'settings' => settings(),
      'account' => account(),
      _ => home(),
    };

    return Scaffold(
      body: TwinConnectAmbientBackground(
        dark: _dark,
        backgroundColor: sidebar,
        child: Row(children: [
          Expanded(child: SafeArea(child: ListView(
            padding: EdgeInsets.symmetric(
                horizontal: wide ? 30 : 17, vertical: 25),
            children: [
              Center(child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1000),
                child: AnimatedSwitcher(
                  key: const Key('devPageTransition'),
                  duration: const Duration(milliseconds: 360),
                  reverseDuration: const Duration(milliseconds: 210),
                  switchInCurve: Curves.easeOutCubic,
                  switchOutCurve: Curves.easeInCubic,
                  transitionBuilder: (child, animation) => FadeTransition(
                    opacity: animation,
                    child: SlideTransition(
                      position: Tween<Offset>(
                        begin: const Offset(0, .025),
                        end: Offset.zero,
                      ).animate(animation),
                      child: child,
                    ),
                  ),
                  child: KeyedSubtree(
                    key: ValueKey<String>(_page),
                    child: content(),
                  ),
                ),
              )),
            ],
          ))),
          sideBar(),
        ]),
      ),
    );
  }
}
