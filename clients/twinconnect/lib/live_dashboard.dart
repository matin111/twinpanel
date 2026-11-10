import 'dart:ui' show ImageFilter;
import 'dart:io' show Platform, HttpClient, InternetAddress, Process;
import 'dart:convert' show utf8;
import 'dart:async' show Timer;

import 'package:flutter/services.dart' show PlatformException;

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'protocols.dart';
import 'server_inventory.dart';
import 'connection_bootstrap.dart';
import 'tenant_api.dart';
import 'vpn_policy_store.dart';
import 'windows_wireguard.dart';
import 'tenant_models.dart';
import 'plan_classification.dart';
import 'account_snapshot.dart';
import 'native_vpn_bridge.dart';
import 'country_flag.dart';
import 'ambient_background.dart';
import 'interactive_glass_card.dart';
import 'share_vpn_preview.dart';
import 'connection_signal_art.dart';
import 'vpn_settings.dart';

/// Authenticated application uses the original visual dashboard layout with live data.

class TwinConnectLiveDashboard extends StatefulWidget {
  const TwinConnectLiveDashboard({
    required this.panel,
    required this.username,
    required this.sessionToken,
    required this.catalog,
    required this.servers,
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
  final String sessionToken;
  final PanelProtocolCatalog? catalog;
  final AppServerInventory? servers;
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
  final VpnPolicyStore _vpnPolicy = const VpnPolicyStore();
  bool _vpnBusy = false;
  bool _vpnUp = false;
  bool _vpnVerified = false;
  bool _vpnReady = false;
  bool _vpnUnmanaged = false;
  bool _vpnCleanup = false;
  int _vpnRx = 0;
  int _vpnTx = 0;
  String? _vpnError;
  String? _publicIp;
  int? _httpsLatencyMs;
  bool _autoFastest = false;
  bool _networkRefreshing = false;
  int _networkEpoch = 0;
  Timer? _networkTimer;
  String? _activeNodeId;

  final Map<String, int?> _nodePings = {};
  final Map<String, String> _nodePingErrors = {};
  final Set<String> _pingingNodes = {};
  bool _pingAllBusy = false;
  int? _latencyFor(AppServer node) => _nodePings.containsKey(node.id)
    ? _nodePings[node.id] : node.latencyMs;

  Future<void> _probeNode(int index) async {
    final nodes = widget.servers?.servers;
    if (!Platform.isWindows || nodes == null || index < 0 ||
        index >= nodes.length) return;
    final node = nodes[index];
    if (_pingingNodes.contains(node.id)) return;
    if (node.probeIp == null) {
      if (mounted) setState(() {
        _nodePings[node.id] = null;
        _nodePingErrors[node.id] = 'NO_PROBE_ADDRESS';
      });
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
          caseSensitive: false).hasMatch(output)) latency = 1;
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
      if (mounted) setState(() {
        _nodePings[node.id] = latency;
        if (error == null) {
          _nodePingErrors.remove(node.id);
        } else {
          _nodePingErrors[node.id] = error;
        }
        _pingingNodes.remove(node.id);
      });
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
      final latency = _latencyFor(node);
      if (!node.nodeOnline || latency == null) continue;
      if (best == null || latency < _latencyFor(servers[best])!) {
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

  Future<void> _selectServerAndConnect(int index) async {
    final nodes = widget.servers?.servers;
    if (nodes == null || index < 0 || index >= nodes.length ||
        _vpnBusy || !Platform.isWindows) return;

    final targetId = nodes[index].id;
    if (_vpnUp && _activeNodeId == targetId) {
      setState(() { _selected = index; _page = 'home'; });
      return;
    }
    if (_vpnUnmanaged) {
      setState(() => _vpnError = 'UNMANAGED_WIREGUARD_SERVICE');
      return;
    }
    if (!_vpnReady || !_wireGuardAllowed) {
      setState(() => _vpnError = !_wireGuardAllowed
          ? 'WIREGUARD_NOT_ALLOWED'
          : 'WIREGUARD_NOT_INSTALLED_OR_ADMIN_REQUIRED');
      return;
    }

    // Validate the target and obtain only its authorized profile BEFORE
    // removing the working tunnel. A failed preflight keeps it running.
    setState(() { _vpnBusy = true; _vpnError = null; });
    try {
      final policy = await _vpnPolicy.load(
          widget.panel.namespace, widget.username);
      final capabilities = await NativeVpnBridge.probe();
      final native = await NativeVpnBridge.protocolReadiness();
      final candidate = await ConnectionBootstrap(
          api: TenantApi.fromBuildConfig()).prepare(
        panel: widget.panel,
        sessionToken: widget.sessionToken,
        serverId: targetId,
        protocolCode: 'wireguard',
        policy: policy,
        capabilities: capabilities,
        nativeProtocols: native,
      );
      final node = WindowsWireGuardController.configForSingleNode(
          candidate.profiles, targetId);
      if (!mounted) return;

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
    _resetNetworkStats();
    super.dispose();
  }


  bool get _wireGuardAllowed => widget.catalog?.entries.any((entry) =>
      entry.protocol.code == 'wireguard' && entry.selected &&
      entry.configRecordPresent) ?? false;

  String? get _selectedServerId {
    final servers = widget.servers?.servers;
    if (servers == null || servers.isEmpty || _selected < 0 ||
        _selected >= servers.length) return null;
    return servers[_selected].id;
  }

  String _errorText(Object error) {
    if (error is PlatformException) return error.code;
    if (error is TenantApiException) return error.message;
    if (error is ConnectionBootstrapException) return error.code;
    if (error is FormatException) return error.message;
    if (error is StateError) return 'NATIVE_ENGINE_UNAVAILABLE';
    return 'VPN_CONNECTION_FAILED';
  }

  @override
  void initState() {
    super.initState();
    _refreshVpnStatus();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && (widget.servers?.servers.isNotEmpty ?? false)) {
        _probeAllNodes();
      }
    });
  }

  @override
  void didUpdateWidget(covariant TwinConnectLiveDashboard oldWidget) {
    super.didUpdateWidget(oldWidget);
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
    if (!Platform.isWindows || _vpnBusy) return;
    final wasUp = _vpnUp;
    try {
      final status = await _vpn.status();
      final native = await NativeVpnBridge.protocolReadiness();
      if (!mounted) return;
      setState(() {
        _vpnUp = status['state'] == 'interface_up' ||
            status['state'] == 'peer_verified';
        _vpnVerified = status['state'] == 'peer_verified' &&
            status['peerHandshakeVerified'] == true;
        _vpnCleanup = status['state'] == 'needs_cleanup';
        _vpnUnmanaged = status['state'] == 'unmanaged_service';
        _vpnRx = status['rxBytes'] is int ? status['rxBytes'] as int : 0;
        _vpnTx = status['txBytes'] is int ? status['txBytes'] as int : 0;
        _vpnReady = native.supports('wireguard');
        _vpnError = null;
        if (!_vpnUp) _resetNetworkStats();
      });
      if (_vpnUp && (!wasUp || _networkTimer == null)) _startNetworkStats();
      if (_vpnUp && _vpnVerified && _publicIp == null) _readNetworkStats();
    } catch (error) {
      if (mounted) setState(() {
        _vpnReady = false;
        _vpnUp = false;
        _vpnVerified = false;
        _vpnError = _errorText(error);
        _resetNetworkStats();
      });
    }
  }

  Future<void> _toggleVpn() async {
    if (_vpnBusy || !Platform.isWindows) return;
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
          final best = _fastestKnownIndex;
          if (best == null) throw const FormatException('NO_MEASURED_SERVER');
          _selected = best;
        }
        final selectedId = _selectedServerId!;
        final policy = await _vpnPolicy.load(
            widget.panel.namespace, widget.username);
        final capabilities = await NativeVpnBridge.probe();
        final native = await NativeVpnBridge.protocolReadiness();
        final candidate = await ConnectionBootstrap(
            api: TenantApi.fromBuildConfig()).prepare(
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
  String _page = 'home';
  String _filter = 'all';
  String _search = '';
  int _selected = 0;
  final Set<int> _favorites = <int>{};

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

  static const purple = Color(0xFFA46AFF);
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



  String tr(String fa, String en) => _persian ? fa : en;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TwinConnect',
      debugShowCheckedModeBanner: false,
      locale: Locale(_persian ? 'fa' : 'en'),
      supportedLocales: const [Locale('fa'), Locale('en')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      themeMode: _dark ? ThemeMode.dark : ThemeMode.light,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: purple,
          brightness: Brightness.light,
          surface: const Color(0xFFFFFFFF),
        ),
        scaffoldBackgroundColor: const Color(0xFFF5F3FD),
      ),
      darkTheme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: purple,
          brightness: Brightness.dark,
          surface: const Color(0xFF1B253C),
        ),
        scaffoldBackgroundColor: const Color(0xFF10162B),
      ),
      home: Builder(builder: _shell),
    );
  }

  Widget _shell(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 870;
    final ink = _dark ? const Color(0xFFF7F4FF) : const Color(0xFF21233F);
    final sub = _dark ? const Color(0xFFABB4C9) : const Color(0xFF565D75);
    final line = _dark ? const Color(0xFF3C4564) : const Color(0xFFDADCEA);
    final panel = _dark ? const Color(0xFF202B43) : const Color(0xFFFFFFFF);
    final sidebar = _dark ? const Color(0xFF11182F) : const Color(0xFFF0EDFB);

    Text txt(String s, {double size = 13, bool bold = false, Color? color,
        TextAlign? align}) => Text(
      s, textAlign: align, overflow: TextOverflow.ellipsis,
      style: TextStyle(
        color: color ?? ink, fontSize: size,
        fontWeight: bold ? FontWeight.w700 : FontWeight.w400,
      ),
    );

    BoxDecoration tile({bool selected = false, double radius = 17}) =>
        BoxDecoration(
          color: selected
              ? purple.withValues(alpha: _dark ? 0.17 : 0.10)
              : (_dark ? const Color(0xFF344360) : const Color(0xFFFDFDFF))
                  .withValues(alpha: _dark ? 0.55 : 0.76),
          borderRadius: BorderRadius.circular(radius),
          border: Border.all(
            color: selected
                ? purple.withValues(alpha: 0.80)
                : (_dark ? Colors.white : const Color(0xFF6971AC))
                    .withValues(alpha: _dark ? 0.20 : 0.19),
          ),
          boxShadow: [
            BoxShadow(
              color: (selected ? purple : Colors.black)
                  .withValues(alpha: selected ? 0.14 : 0.08),
              blurRadius: selected ? 26 : 20,
              offset: const Offset(0, 10),
            ),
          ],
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
      selected: selected,
      radius: radius,
      padding: padding,
      child: child,
    );

    void notification() => ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(tr(
        'برای دریافت سرورها از به‌روزرسانی استفاده کنید',
        'Refresh to fetch updated servers',
      ))),
    );

    Widget sideNav(String page, IconData icon, String title) => Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Material(
        borderRadius: BorderRadius.circular(13),
        color: _page == page ? purple.withValues(alpha: 0.19)
            : Colors.transparent,
        child: InkWell(
          key: Key('devNav_$page'),
          borderRadius: BorderRadius.circular(13),
          onTap: () => setState(() => _page = page),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: wide ? 15 : 8, vertical: 13),
            child: Row(
              mainAxisAlignment: wide ? MainAxisAlignment.start
                  : MainAxisAlignment.center,
              children: [
                Icon(icon, color: _page == page ? purple : sub, size: 21),
                if (wide) ...[
                  const SizedBox(width: 12),
                  Expanded(child: txt(title,
                    color: _page == page ? ink : sub,
                    bold: _page == page)),
                ],
              ],
            ),
          ),
        ),
      ),
    );

    Widget sideBar() => Container(
      width: wide ? 195 : 74,
      padding: EdgeInsets.symmetric(
        horizontal: wide ? 13 : 7, vertical: 22),
      decoration: BoxDecoration(color: sidebar,
        border: Border(left: BorderSide(color: line))),
      child: Column(children: [
        Container(
          width: 42, height: 42,
          decoration: BoxDecoration(
            gradient: const LinearGradient(colors: [
              Color(0xFFC68AFF), Color(0xFF7051D4)]),
            borderRadius: BorderRadius.circular(13),
          ),
          child: const Icon(Icons.all_inclusive_rounded,
            color: Colors.white, size: 27),
        ),
        if (wide) ...[
          const SizedBox(height: 9),
          txt('TwinConnect', size: 17, bold: true),
        ],
        const SizedBox(height: 34),
        sideNav('home', Icons.bolt_rounded, tr('اتصال سریع', 'Quick connect')),
        sideNav('locations', Icons.place_outlined, tr('مکان‌ها', 'Locations')),
        sideNav('settings', Icons.tune_rounded, tr('تنظیمات', 'Settings')),
        sideNav('account', Icons.person_outline_rounded, tr('حساب', 'Account')),
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
          onPressed: () => setState(() => _dark = !_dark),
        ),
        TextButton(
          key: const Key('devLanguageToggle'),
          onPressed: () => setState(() => _persian = !_persian),
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
        filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
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
                  const Color(0xFF362A5E).withValues(alpha: 0.78),
                  const Color(0xFF253754).withValues(alpha: 0.70),
                  const Color(0xFF23364B).withValues(alpha: 0.70),
                ]
              : [
                  const Color(0xFFEDE4FF).withValues(alpha: 0.79),
                  Colors.white.withValues(alpha: 0.74),
                  const Color(0xFFE6F1FF).withValues(alpha: 0.76),
                ],
        ),
        border: Border.all(color: purple.withValues(alpha: 0.56)),
        boxShadow: [BoxShadow(
          color: purple.withValues(alpha: _dark ? 0.19 : 0.11),
          blurRadius: 38, spreadRadius: 2, offset: const Offset(0, 14)),
        ],
      ),
      child: Column(children: [
        AnimatedSwitcher(
          duration: const Duration(milliseconds: 240),
          child: KeyedSubtree(
            key: const ValueKey('dev-disconnected'),
            child: smallPill(_vpnVerified
                ? tr('دست‌دهی تأیید شد', 'Handshake verified')
                : _vpnUp ? tr('رابط فعال', 'Interface active')
                : _vpnBusy ? tr('در حال اجرا', 'Working')
                : tr('قطع', 'Disconnected'), icon: Icons.circle),
          ),
        ),
        const SizedBox(height: 13),
        TweenAnimationBuilder<double>(
          key: const Key('devPowerEntranceAnimation'),
          tween: Tween(begin: .86, end: 1),
          duration: const Duration(milliseconds: 620),
          curve: Curves.easeOutBack,
          builder: (context, value, child) => Transform.scale(
            scale: value,
            child: child,
          ),
          child: SizedBox(
            width: 94, height: 94,
            child: FilledButton(
              key: const Key('liveConnectionControlsButton'),
              onPressed: _vpnBusy ? null : _toggleVpn,
              style: FilledButton.styleFrom(
                backgroundColor: Colors.transparent,
                foregroundColor: Colors.white,
                disabledBackgroundColor: Colors.transparent,
                padding: EdgeInsets.zero,
                shape: const CircleBorder(),
                elevation: 0,
              ),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 340),
                curve: Curves.easeInOut,
                width: 94, height: 94,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: _vpnVerified
                      ? const [Color(0xFF34E8BD), Color(0xFF0EADBA)]
                      : const [Color(0xFFC393FF), Color(0xFF7351E9)],
                  ),
                  border: Border.all(
                    width: 2,
                    color: Colors.white.withValues(alpha: 0.45),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: (_vpnVerified
                        ? const Color(0xFF29E4BD) : purple)
                        .withValues(alpha: 0.42),
                      blurRadius: 28, spreadRadius: 3,
                    ),
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.16),
                      blurRadius: 11,
                      offset: const Offset(0, 7),
                    ),
                  ],
                ),
                child: Center(
                  child: _vpnBusy
                    ? const SizedBox.square(dimension: 28,
                        child: CircularProgressIndicator(
                          strokeWidth: 3, color: Colors.white))
                    : Icon(_vpnUp ? Icons.stop_rounded
                        : Icons.power_settings_new_rounded,
                        size: 43, color: Colors.white),
                ),
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        txt(tr('اتصال سریع', 'Quick connect'), size: 20, bold: true),
        const SizedBox(height: 5),
        txt(_vpnVerified
              ? tr('دست‌دهی با سرور تأیید شد', 'Server handshake verified')
              : _vpnUp ? tr('رابط فعال است؛ دست‌دهی هنوز تأیید نشده',
                  'Interface active; handshake not verified')
              : tr('سرور را انتخاب کنید؛ اتصال مستقیم فعلاً WireGuard است',
                  'Select a server; direct connection currently supports WireGuard'),
            size: 12, color: sub),
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
                'در مکان‌ها سرور WireGuard انتخاب کنید.',
                'Select a WireGuard server in Locations.'),
              'UNMANAGED_WIREGUARD_SERVICE' => tr(
                'سرویس WireGuard متعلق به برنامه نیست؛ تغییری ایجاد نشد.',
                'WireGuard service is not managed by this app.'),
              final code => tr('خطای اتصال: $code', 'Connection error: $code'),
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
        Container(
          decoration: tile(radius: 15),
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
                child: txt(_vpnVerified ? (_publicIp ?? '—') : '—',
                    size: 12, bold: true),
              ),
            ])),
            Expanded(child: Column(children: [
              txt(tr('پروتکل', 'Protocol'), size: 10, color: sub),
              const SizedBox(height: 4),
              txt(_vpnUp ? 'WireGuard' : _filter == 'all'
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
      return Padding(
        padding: const EdgeInsets.only(bottom: 9),
        child: glassCard(
          key: Key('devServer_$index'),
          selected: _selected == index,
          radius: 16,
          child: Material(
            color: Colors.transparent,
            child: InkWell(
          onTap: _vpnBusy ? null : () => _selectServerAndConnect(index),
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
                    : _latencyFor(widget.servers!.servers[index]) == null
                      ? (_nodePingErrors[widget.servers!.servers[index].id]
                          == 'NO_PROBE_ADDRESS' ? tr('بدون آدرس', 'No IP')
                          : '— ms')
                      : '${_nodePingErrors[widget.servers!.servers[index].id]
                          == 'APPROXIMATE_RTT' ? '≈' : ''}${_latencyFor(widget.servers!.servers[index])} ms',
                  style: TextStyle(fontSize: 11, color: sub),
                ),
              ),
              IconButton(
                key: Key('probeNode_${widget.servers!.servers[index].id}'),
                tooltip: tr('تست پینگ', 'Ping server'),
                onPressed: _pingingNodes.contains(widget.servers!.servers[index].id)
                    ? null : () => _probeNode(index),
                icon: const Icon(Icons.network_ping_rounded, size: 18, color: purple),
              ),
              const SizedBox(width: 8),
              Icon(_vpnUp && _activeNodeId == widget.servers?.servers[index].id
                ? Icons.verified_rounded : Icons.chevron_right_rounded,
                size: 19, color: _vpnUp && _activeNodeId == widget.servers?.servers[index].id
                  ? const Color(0xFF33D6A6) : sub),
            ]),
          ),
        ),
          ),
        ),
      );
    }

    // All 16 chips remain visible. Admin-selected protocols will replace
    // the preview's complete catalog after an authenticated panel session.
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
              onSelected: (_) => setState(() => _filter = entry.$1),
            ),
        ],
      ),
    );

    Widget locations() {
      final matching = <int>[
        for (int i = 0; i < demoServers.length; i++)
          if ((_filter == 'all' ||
                  (widget.catalog?.entries.any((entry) => entry.protocol.code == _filter && entry.selected) ?? false)) &&
              '${demoServers[i].country} ${demoServers[i].city}'
                .toLowerCase().contains(_search.toLowerCase()))
            i,
      ];
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
                _probeAllNodes();
              },
              icon: const Icon(Icons.refresh_rounded),
            ),
          ]),
          const SizedBox(height: 10),
          OutlinedButton.icon(
            onPressed: _pingAllBusy ? null : _probeAllNodes,
            icon: const Icon(Icons.network_ping_rounded),
            label: Text(tr('تست پینگ همه سرورها', 'Ping all servers')),
          ),
          const SizedBox(height: 13),
          filters(),
          const SizedBox(height: 12),
          for (final i in matching) serverRow(i),
          if (matching.isEmpty)
            Padding(
              padding: const EdgeInsets.all(22),
              child: txt(tr('سروری پیدا نشد', 'No servers found'),
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
            smallPill(_vpnVerified ? tr('دست‌دهی تأیید شد', 'Handshake verified') :
                _vpnUp ? tr('رابط فعال', 'Interface active') :
                tr('قطع', 'Disconnected')),
          ]),
          const SizedBox(height: 23),
          Row(children: [
            Expanded(child: metric(Icons.speed_rounded,
              tr('تاخیر HTTPS', 'HTTPS latency'),
              _vpnVerified && _httpsLatencyMs != null
                ? '$_httpsLatencyMs ms' : '— ms')),
            const SizedBox(width: 10),
            Expanded(child: metric(Icons.public_rounded,
              tr('آی‌پی عمومی', 'Public IP'),
              _vpnVerified ? (_publicIp ?? '—') : '—')),
          ]),
          const SizedBox(height: 18),
          Row(children: [
            Expanded(child: metric(Icons.arrow_downward_rounded,
              tr('دریافت', 'Received'), _vpnUp ? _formatTransferBytes(_vpnRx) : '—',
              detail: tr('مجموع رابط', 'Interface total'))),
            const SizedBox(width: 10),
            Expanded(child: metric(Icons.arrow_upward_rounded,
              tr('ارسال', 'Sent'), _vpnUp ? _formatTransferBytes(_vpnTx) : '—',
              detail: tr('مجموع رابط', 'Interface total'))),
          ]),
          const SizedBox(height: 25),
          Container(
            decoration: tile(radius: 14),
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
        glassCard(
          key: const Key('liveAutoFastestServer'),
          radius: 19,
          padding: const EdgeInsets.symmetric(horizontal: 17, vertical: 10),
          child: Row(children: [
            const Icon(Icons.auto_awesome_rounded, size: 22, color: purple),
            const SizedBox(width: 12),
            Expanded(child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                txt(tr('انتخاب سریع‌ترین سرور', 'Select fastest server'),
                    size: 13, bold: true),
                const SizedBox(height: 4),
                txt(_fastestKnownIndex == null
                    ? tr('تاخیر قابل‌اندازه‌گیری موجود نیست',
                        'No measured server latency available')
                    : tr('بر اساس تاخیر گزارش‌شده پنل',
                        'Based on panel-reported server latency'),
                    size: 11, color: sub),
              ],
            )),
            Switch(
              key: const Key('autoFastestServerToggle'),
              value: _autoFastest,
              onChanged: _vpnBusy || _vpnUp ? null : (enabled) {
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
                    _filter = 'wireguard';
                  }
                });
              },
            ),
          ]),
        ),
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
              child: const Icon(Icons.tune_rounded, color: purple, size: 24),
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
          onPressed: _vpnUp || _vpnCleanup || _vpnBusy ? null : widget.onLogout,
          icon: const Icon(Icons.logout_rounded),
          label: Text(tr('خروج از حساب', 'Sign out')),
        ),
        if (_vpnUp || _vpnCleanup || _vpnBusy)
          Padding(
            padding: const EdgeInsets.only(top: 7),
            child: Text(tr('ابتدا اتصال VPN را قطع کنید.',
                'Disconnect VPN before signing out.'),
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
                  onTap: () => setState(() => _persian = !_persian)),
              settingLine(Icons.palette_outlined, tr('ظاهر', 'Appearance'),
                  disabled: false,
                  onTap: () => setState(() => _dark = !_dark)),
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
              icon: const Icon(Icons.refresh_rounded, color: purple),
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
                    child: const Icon(Icons.data_usage_rounded, color: purple),
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
                Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  Flexible(child: Text(
                    current == null ? '—' : _formatBytes(used),
                    maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: TextStyle(color: ink, fontSize: 31,
                      fontWeight: FontWeight.w800),
                  )),
                  const SizedBox(width: 10),
                  Padding(
                    padding: const EdgeInsets.only(bottom: 5),
                    child: Text(hasLimit ? '/ ${_formatBytes(limit)}' :
                        tr('مصرف کل', 'Total usage'),
                        style: TextStyle(color: sub, fontSize: 12)),
                  ),
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
                  const Icon(Icons.calendar_month_rounded, color: purple,
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
                  const Icon(Icons.devices_other_rounded, color: purple,
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
            onPressed: _vpnUp || _vpnBusy || _vpnCleanup
                ? null : widget.onLogout,
            icon: const Icon(Icons.logout_rounded),
            label: Text(tr('خروج از حساب', 'Sign out')),
          ),
          if (_vpnUp || _vpnBusy || _vpnCleanup)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: txt(tr('برای خروج ابتدا VPN را قطع کنید.',
                    'Disconnect VPN before signing out.'),
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
      body: Row(children: [
        Expanded(child: TwinConnectAmbientBackground(
          dark: _dark,
          child: SafeArea(child: ListView(
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
          )),
        )),
        sideBar(),
      ]),
    );
  }
}
