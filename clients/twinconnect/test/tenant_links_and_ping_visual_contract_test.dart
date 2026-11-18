import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Support, Renew and Website load from the active authenticated panel', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final api = File('lib/tenant_api.dart').readAsStringSync();
    final model = File('lib/tenant_models.dart').readAsStringSync();
    expect(api, contains("'/v1/central-app/session/brand'"));
    expect(model, contains("telegramUrl: optional('telegram_url')"));
    expect(model, contains("renewalUrl: optional('renewal_url')"));
    expect(model, contains("websiteUrl: optional('website_url')"));
    expect(dashboard, contains('loadSessionBrand('));
    expect(dashboard, contains('_tenantLinkFromBrand(brand, kind)'));
    expect(dashboard, contains("_openTenantLink('support'"));
    expect(dashboard, contains("_openTenantLink('renewal'"));
    expect(dashboard, contains("_openTenantLink('website'"));
    expect(dashboard, contains('item.id, tr(item.fa, item.en)'));
    expect(dashboard, contains('TENANT_BRAND_MISMATCH'));
    expect(dashboard, contains('LaunchMode.externalApplication'));
  });

  test('tenant links accept Telegram handles and show missing-link feedback', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("_safeTenantLink(String? raw, String kind)"));
    expect(dashboard, contains("candidate = 'https://t.me/"));
    expect(dashboard, contains('brand = fresh;'));
    expect(dashboard, contains("_tenantLinkFromBrand(brand, kind)"));
    expect(dashboard, contains('App Brand Studio'));
    expect(dashboard, contains('uri.scheme != \'https\''));
    expect(dashboard, contains('uri.userInfo.isNotEmpty'));
  });

  test('connecting screen keeps status, connection control and clock without redundant captions', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("Key('liveConnectionStatus')"));
    expect(dashboard, contains("Key('liveConnectionControlsButton')"));
    expect(dashboard, contains("Key('liveConnectionDuration')"));
    expect(dashboard, isNot(contains("tr('اتصال امن برقرار است', 'Secure connection active')")));
    expect(dashboard, isNot(contains("tr('دست‌دهی با سرور تأیید شد', 'Server handshake verified')")));
  });

  test('connection fabric moves for active connection without fabricating throughput', () {
    final wave = File('lib/twinconnect_wave_indicator.dart').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(wave, contains('if (_animate)'));
    expect(wave, contains('if (!_animate && _motion.isAnimating)'));
    expect(dashboard, contains('connected: _verifiedConnectionActive'));
    expect(dashboard, contains("Key('liveConnectionDataFabric')"));
    expect(wave, contains('bool get _animate => widget.connected || widget.connecting;'));
    expect(wave, contains('final active = connected;'));
    expect(wave, isNot(contains('Icons.lock_rounded')));
    expect(dashboard, contains("Key('liveRefreshTunnelStatus')"));
  });

  test('language selector uses professional glass cards with six saved locales', () {
    final picker = File('lib/twin_language_picker.dart').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains('showTwinLanguagePicker('));
    expect(dashboard, contains('await prefs.setString(_languagePreference, selected)'));
    expect(picker, contains("Key('devLanguageDialog')"));
    expect(picker, contains('GridView.builder('));
    expect(picker, contains('Icons.translate_rounded'));
    expect(picker, contains('Icons.check_circle_rounded'));
    expect(picker, contains('rtl ? TextDirection.rtl : TextDirection.ltr'));
    expect(picker, contains('item.code == \'ar\''));
    expect(picker, contains('Color(0xFFF4FAFB)'));
    expect(picker, contains('Color(0xFF13232F)'));
    for (final code in ['fa', 'en', 'tr', 'ar', 'de', 'fr']) {
      expect(picker, contains("code: '$code'"));
    }
  });

  test('desktop connection cards share height and network location opens servers', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("Key('liveBalancedConnectionPanels')"));
    expect(dashboard, contains('crossAxisAlignment: CrossAxisAlignment.stretch'));
    expect(
      RegExp(r'powerCard\s*\(\s*subscriptionContent:\s*homeSubscriptionSummary\(\)\s*\)')
          .hasMatch(dashboard),
      isTrue,
    );
    expect(dashboard, contains("Key('liveOpenLocationsFromNetwork')"));
    expect(dashboard, contains("onTap: () => setState(() => _page = 'locations')"));
    expect(dashboard, contains("tr('مکان‌ها', 'Locations')"));
    expect(dashboard, isNot(contains("tr('از پنل', 'Panel')")));
  });

  test('fastest server toggle immediately probes selects and connects', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final begin = dashboard.indexOf('Future<void> _enableFastestAndConnect()');
    final end = dashboard.indexOf('void _resetNetworkStats()', begin);
    expect(begin, greaterThan(0));
    expect(end, greaterThan(begin));
    final action = dashboard.substring(begin, end);
    expect(action, contains('await _probeAllNodes()'));
    expect(action, contains('final best = _fastestKnownIndex'));
    expect(action, contains('entry.selected && entry.configRecordPresent'));
    expect(action, contains('_selected = best'));
    expect(action, contains('_autoFastest = true'));
    expect(action, contains('await _toggleVpn()'));
    expect(action, contains('NO_MEASURED_SERVER'));
    expect(dashboard, contains('_enableFastestAndConnect();'));
    expect(dashboard, contains("Key('autoFastestServerToggle')"));
  });

  test('settings show native policy inline without duplicate navigation', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final policy = File('lib/vpn_settings.dart').readAsStringSync();
    expect(dashboard, contains('Widget settings() => Column('));
    expect(dashboard, contains("Key('inlineVpnSettings')"));
    expect(dashboard, contains("Key('inlineVpnSettings')"));
    expect(dashboard, contains('embedded: true'));
    expect(dashboard, isNot(contains("Key('devShareVpnDisclosure')")));
    expect(policy, contains('final bool embedded;'));
    expect(policy, contains('if (widget.embedded) return content;'));
    expect(dashboard, contains('widget.onRefreshAccount()'));
    expect(dashboard, contains('widget.onRefresh()'));
    expect(dashboard, contains('_disconnectAndSignOut'));
  });

  test('Persian dashboard is RTL and English dashboard is LTR', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("textDirection: _rtl ? TextDirection.rtl : TextDirection.ltr"));
    expect(dashboard, contains("key: ValueKey<String>(_rtl ? 'dashboard-rtl' : 'dashboard-ltr')"));
    // Windows retains its desktop sidebar; Android owns a bottom navigation.
    expect(dashboard, contains('child: Column(children: ['));
    expect(dashboard, contains('Expanded(child: Row(children: ['));
    expect(dashboard, contains('if (!Platform.isAndroid) sideBar(),'));
    expect(dashboard, contains('if (Platform.isAndroid)'));
    expect(dashboard, contains("Key('androidMainNavigation')"));
    expect(dashboard, contains("const ['home', 'locations', 'settings', 'account']"));
    expect(dashboard, isNot(contains('textDirection: TextDirection.ltr,\n            child: Row(')));
    expect(dashboard, contains('textDirection: TextDirection.ltr,'));
  });

  test('Android location selection feeds exact native WireGuard node ID', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final androidCard = File('lib/android_connection_card.dart').readAsStringSync();
    expect(dashboard, contains('if (Platform.isAndroid) _androidExplicitNodeSelected = true;'));
    expect(dashboard, contains('selectedNodeId: _androidExplicitNodeSelected'));
    expect(dashboard, contains('if (Platform.isAndroid) {'));
    expect(androidCard, contains("item['node_id']?.toString()"));
    expect(androidCard, contains('selectedNodeId != null && id != selectedNodeId'));
    expect(androidCard, contains('SELECTED_WIREGUARD_NODE_UNAVAILABLE'));
    expect(androidCard, contains('_candidateNodes(profiles, selectedNodeId)'));
    expect(androidCard, contains('peerVerified = await _awaitPeerHandshake()'));
    expect(androidCard, contains('await _controller.stop()'));
    expect(androidCard, contains('WIREGUARD_PEER_HANDSHAKE_TIMEOUT'));
    expect(androidCard, contains('candidates.take(3)'));
    expect(androidCard, contains('candidates.take(1)'));
  });

  test('Android connection status follows active native tunnel not protocol filter', () {
    final card = File('lib/android_connection_card.dart').readAsStringSync();
    expect(card, contains("final protocolName = chosen?.protocol.name"));
    expect(card, contains("Key('androidSeparateActiveProtocol')"));
    expect(card, contains("Key('androidDisconnectPreviousTunnel')"));
    expect(card, contains('final internetVerified = _activeVerifiedTransport && _publicIp != null;'));
    expect(card, contains('Internet reachable while VPN active'));
    expect(card, contains("Key('androidNoHandshakeDiagnostic')"));
    expect(card, contains('WG_INTERFACE_UP_NO_HANDSHAKE'));
    expect(card, contains('Tunnel interface up; server connection unverified'));
  });

  test('Android Connect tab preserves selected protocol and node', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("selectedProtocolCode: _filter == 'all' ? null : _filter"));
    expect(dashboard, contains('Navigation does not rewrite the chosen protocol or node'));
    expect(dashboard, isNot(contains('widget.native.supports(_filter)')));
  });

  test('Android modern native engine does not reuse WireGuard or Cisco', () {
    final modern = File('lib/android_singbox_tunnel.dart').readAsStringSync();
    final card = File('lib/android_connection_card.dart').readAsStringSync();
    expect(modern, contains('package:sing_box/sing_box.dart'));
    for (final code in ['hysteria2', 'tuic', 'anytls', 'socks5']) {
      expect(modern, contains("'$code'"));
    }
    expect(modern, contains('SingBoxProfileValidator.validateOutbound('));
    expect(modern, contains('SingBox.instance.connect(config)'));
    expect(card, contains('Future<void> _connectModern('));
    expect(card, contains('Future<void> _disconnectModern()'));
    expect(card, contains('loadSessionNativeProfiles('));
    expect(card, contains('AndroidSingBoxTunnel.instance.connect('));
    final activity = File(
      'native/android/kotlin/com/twinpanel/twinconnect/MainActivity.kt',
    ).readAsStringSync();
    expect(modern, contains("'forgetSingBoxEphemeralConfig'"));
    expect(modern, contains('SINGBOX_OUTBOUND_UNREACHABLE'));
    expect(activity, contains('"sing_box.last_input"'));
    expect(activity, contains('"sing-box/last_config.json"'));
  });

  test('Android offers all entitled protocols without claiming missing engines', () {
    final android = File('lib/android_connection_card.dart').readAsStringSync();
    final native = File('native/android/kotlin/com/twinpanel/twinconnect/MainActivity.kt')
        .readAsStringSync();
    expect(android, contains("widget.catalog.entries"));
    // Selection also excludes protocols intentionally hidden on Android.
    expect(android, contains('.where((entry) => entry.selected &&'));
    expect(android, contains('AndroidProtocolVisibility.visible('));
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("Key('devProtocolFilters')"));
    expect(dashboard, contains("Key('androidChooseLocation')"));
    expect(dashboard, contains("Key('androidNativeConnectionGlass')"));
    expect(android, contains("Key('androidPrimaryConnect')"));
    expect(android, contains("Key('androidSharedConnectionDataFabric')"));
    expect(android, contains('TwinConnectWaveIndicator('));
    expect(android, contains("Key('androidSharedPowerCard')"));
    expect(android, contains("Key('androidNetworkOverview')"));
    expect(android, contains("Key('androidVerifiedStatus')"));
    expect(android, contains('selectedProtocolCode'));
    // Auto-connect must never silently default to a protocol with no native
    // engine just because that protocol comes first in the catalog.
    expect(android, contains('final readyOptions = available.where'));
    expect(android, contains('widget.native.supports(entry.protocol.code)'));
    expect(android, contains('readyOptions.firstOrNull'));
    expect(android, contains('Engine not installed'));
    expect(android, contains('Disconnect active tunnel first'));
    expect(android, contains('This protocol engine is not ready on Android yet.'));
    expect(android, isNot(contains("Key('androidProtocolChooser')")));
    expect(native, contains('listOf("wireguard")'));
    expect(android, isNot(contains("if ((wireguard?.selected != true) && (cisco?.selected != true))")));
  });

  test('Android quick connect shows real native diagnostics and no fake network figures', () {
    final card = File('lib/android_connection_card.dart').readAsStringSync();
    final native = File(
      'native/android/kotlin/com/twinpanel/twinconnect/WireGuardRuntime.kt',
    ).readAsStringSync();
    final activity = File(
      'native/android/kotlin/com/twinpanel/twinconnect/MainActivity.kt',
    ).readAsStringSync();
    expect(card, contains('loadFailClosed('));
    expect(card, contains("Key('androidNetworkOverview')"));
    expect(card, contains("'VPN error: "));
    expect(native, contains('WIREGUARD_CONFIG_PARSE_FAILED'));
    expect(native, contains('WIREGUARD_NATIVE_START_FAILED'));
    expect(activity, contains('WIREGUARD_NATIVE_START_FAILED'));
    expect(card, contains('wireGuardNoConfigs'));
  });

  test('Android quick connect never shows the raw node picker', () {
    final card = File('lib/android_connection_card.dart').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(card, contains('List<WireGuardNode> _candidateNodes('));
    expect(card, contains('widget.servers?.servers'));
    expect(card, contains('matching.nodeOnline'));
    expect(card, contains('selectedNodeId != null && id != selectedNodeId'));
    expect(card, contains('candidates.sort('));
    expect(card, isNot(contains('showDialog<WireGuardNode>')));
    expect(dashboard, contains('servers: widget.servers'));
  });

  test('Android HTTPS probe requires live transport and never disables TLS', () {
    final card = File('lib/android_connection_card.dart').readAsStringSync();
    expect(card, contains("_probeHttps('api.ipify.org', '/')"));
    expect(card, contains("_probeHttps('icanhazip.com', '/')"));
    expect(card, contains("_probeHttps('www.cloudflare.com', '/cdn-cgi/trace'"));
    expect(card, contains('Uri.https(host, path)'));
    expect(card, contains('Future.wait(['));
    expect(card, contains('(_up && _handshake) || _openVpnUp || _ciscoUp ||'));
    expect(card, contains('_activeVerifiedTransport ? ip : null'));
    expect(card, contains('_activeVerifiedTransport ? latency : null'));
    expect(card, contains('generation == _networkProbeGeneration'));
    expect(card, contains('VPN routing not independently verified'));
    expect(card, isNot(contains('badCertificateCallback')));
  });

  test('Android native engine understands panel split IPv4 routing', () {
    final native = File(
      'native/android/kotlin/com/twinpanel/twinconnect/WireGuardRuntime.kt',
    ).readAsStringSync();
    expect(native, contains('hasFullIpv4Route(raw)'));
    expect(native, contains('hasFullRoute(raw, "0.0.0.0/1")'));
    expect(native, contains('hasFullRoute(raw, "128.0.0.0/1")'));
    expect(native, contains('protectIpv6Route(configText)'));
    expect(native, contains('match.groupValues[2].trimEnd() + ", ::/0"'));
    expect(native, contains('validateStrictProfile(protectedProfile)'));
    expect(native, contains('require(hasFullRoute(raw, "::/0"))'));
  });

  test('Android WireGuard network data comes from actual JNI and HTTPS probes', () {
    final card = File('lib/android_connection_card.dart').readAsStringSync();
    final native = File(
      'native/android/kotlin/com/twinpanel/twinconnect/WireGuardRuntime.kt',
    ).readAsStringSync();
    final service = File(
      'native/android/kotlin/com/twinpanel/twinconnect/SharedTunVpnService.kt',
    ).readAsStringSync();
    expect(service, contains('WireGuardJni.getConfig(handle)'));
    expect(service, contains('WireGuardJni.turnOn(nativeFd, settings)'));
    expect(native, contains('line.startsWith("rx_bytes=")'));
    expect(native, contains('line.startsWith("tx_bytes=")'));
    expect(native, contains('line.startsWith("last_handshake_time_sec=")'));
    expect(native, contains('latestHandshakeEpochMillis'));
    expect(card, contains("status['rxBytes']"));
    expect(card, contains("status['txBytes']"));
    expect(card, contains("status['peerHandshakeVerified']"));
    expect(card, contains('Uri.https(host, path)'));
    expect(card, contains("_probeHttps('api.ipify.org', '/')"));
    expect(card, contains("_probeHttps('icanhazip.com', '/')"));
    expect(card, contains("_probeHttps('www.cloudflare.com', '/cdn-cgi/trace'"));
    expect(card, contains("_speed(_downloadBps)"));
    expect(card, contains("_speed(_uploadBps)"));
    expect(card, contains("Icons.bolt, 'HTTPS'"));
    expect(card, contains('_telemetryTimer?.cancel()'));
  });

  test('failed WireGuard startup releases the VPN slot unless the guard is on', () {
    final service = File(
      'native/android/kotlin/com/twinpanel/twinconnect/SharedTunVpnService.kt',
    ).readAsStringSync();
    expect(service, contains('ownsFailedStart = true'));
    expect(service, contains('if (!persistentBlock) shutdown()'));
    expect(service, isNot(contains('if (!persistentBlock) persistentBlock = true')));
    // wgGetConfig and wgTurnOff share the same lock: concurrent native map
    // access while disconnecting must not cause a process-level Go crash.
    expect(service, contains('fun wireGuardStats(): String? = synchronized(lock)'));
    expect(service, contains('WireGuardJni.turnOff(handle)'));
  });

  test('OpenConnect keeps the native failure visible during shutdown', () {
    final service = File(
      'native/android/java/com/axevpn/flutter/openconnect/AxeOpenConnectVpnService.java',
    ).readAsStringSync();
    expect(service, contains('if (lastFailureCode != null && !lastFailureCode.isEmpty())'));
    expect(service, contains('broadcastStage("error")'));
    expect(service, contains('broadcastStage("disconnected")'));
  });

  test('Cisco Android uses shared TUN ownership without WireGuard JNI', () {
    final controller = File('lib/android_tunnel.dart').readAsStringSync();
    final card = File('lib/android_connection_card.dart').readAsStringSync();
    final native = File(
      'native/android/kotlin/com/twinpanel/twinconnect/MainActivity.kt',
    ).readAsStringSync();
    final cisco = File('lib/android_cisco_tunnel.dart').readAsStringSync();
    final bridge = File('lib/native_vpn_bridge.dart').readAsStringSync();
    expect(controller, contains("nativeProtocols.supports('cisco')"));
    expect(card, contains('CiscoOpenConnectProfile.fromItem(item)'));
    expect(card, contains('AndroidCiscoTunnel.validatedServerTrust(profile)'));
    expect(card, contains("loadSessionNativeProfiles("));
    expect(card, contains('AndroidCiscoTunnel.instance.connect(profile)'));
    expect(card, contains('NativeVpnBridge.requireAndroidCiscoSafeToConnect(policy)'));
    expect(bridge, contains('static void requireAndroidCiscoSafeToConnect(VpnPolicy policy)'));
    expect(bridge, isNot(contains('CISCO_SHARED_GUARD_NOT_IMPLEMENTED')));
    expect(card, contains('_releaseDisconnectedGuard(allowSharedTun: true);\n      await AndroidCiscoTunnel.instance.connect(profile)'));
    expect(card, contains('AndroidCiscoTunnel.instance.status()'));
    expect(cisco, contains('com.axevpn.flutter.openconnect/vpncontrol'));
    expect(cisco, contains("'servercert': pin"));
    expect(cisco, contains("'isRunning'"));
    expect(cisco, contains('CISCO_SHA256_PIN_INVALID'));
    expect(native, contains('OpenConnectFlutterPlugin()'));
    expect(native, contains('listOf("wireguard")'));
  });

  test('Cisco and WireGuard use one Android VpnService for disconnect guard', () {
    final shared = File(
      'native/android/kotlin/com/twinpanel/twinconnect/SharedTunVpnService.kt',
    ).readAsStringSync();
    final plugin = File(
      'native/android/java/com/axevpn/flutter/openconnect/OpenConnectFlutterPlugin.java',
    ).readAsStringSync();
    final adapter = File(
      'native/android/java/com/axevpn/flutter/openconnect/SharedOpenConnectEngine.java',
    ).readAsStringSync();
    final installer = File('tools/install_android_native.py').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(plugin, contains('new Intent(context, SharedTunVpnService.class)'));
    expect(plugin, contains('SharedTunVpnService.ACTION_CONNECT_CISCO'));
    expect(plugin, contains('SharedTunVpnService.ACTION_DISCONNECT_CISCO'));
    expect(plugin, isNot(contains('new Intent(context, AxeOpenConnectVpnService.class)')));
    expect(adapter, contains('owner.establishCiscoTun('));
    expect(adapter, contains('new NativeOpenConnectSession('));
    expect(adapter, contains('owner.onCiscoEngineStopped(this)'));
    expect(shared, contains('fun establishCiscoTun('));
    expect(shared, contains('check(ciscoEngine == null) { "TUNNEL_ALREADY_RUNNING" }'));
    expect(shared, contains('val previous = tun'));
    expect(shared, contains('ParcelFileDescriptor.dup(replacement.fileDescriptor)'));
    expect(shared, contains('if (!persistentBlock && wireGuardHandle < 0) shutdown()'));
    expect(installer, contains('"SharedOpenConnectEngine.java"'));
    expect(installer, isNot(contains('Independent pinned Cisco CSTP/TLS VpnService')));
    final startCisco = dashboard.indexOf('Future<void> _startCiscoTunnel(');
    expect(dashboard.substring(startCisco, startCisco + 220),
        contains('_requireVerifiedGuardIfRequested(sharedWireGuard: true)'));
  });

  test('six dashboard locales and Arabic right-to-left are supported', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final localizer = File('lib/app_strings.dart').readAsStringSync();
    for (final code in ['fa', 'en', 'tr', 'ar', 'de', 'fr']) {
      expect(dashboard, contains("'$code'"));
    }
    expect(dashboard, contains("_languageCode == 'ar'"));
    expect(localizer, contains('static const Map<String, Map<String, String>> _translations'));
  });

  test('network ping uses latency-colored neon lightning, not gauge', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains("Key('livePingLightningIcon')"));
    expect(dashboard, contains('Icons.bolt_rounded'));
    expect(dashboard, contains('ServerLatency.color(_connectedServerRtt)'));
  });

  test('light mode has visible branded luminous geometry', () {
    final ambient = File('lib/ambient_background.dart').readAsStringSync();
    final theme = File('lib/brand_theme.dart').readAsStringSync();
    expect(ambient, contains('final bounds = Offset.zero & size;'));
    expect(ambient, contains('for (var i = 0; i < 39; i++)'));
    expect(ambient, contains('for (var i = 0; i < 13; i++)'));
    expect(ambient, contains('dark ? .10 : .075'));
    expect(theme, contains('Color(0xFFF3F7F8), 0.97'));
  });

  test('Android server ping probes numeric inventory IP without Windows-only gate', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains('(!Platform.isWindows && !Platform.isAndroid)'));
    expect(dashboard, contains("'/system/bin/ping'"));
    expect(dashboard, contains('Socket.connect('));
    expect(dashboard, contains("'TCP_CONNECT_RTT'"));
    expect(dashboard, contains("Key('probeNode_"));
    expect(dashboard, contains('TCP connection to the configured service port, not ICMP.'));
  });

  test('all server ping actions use lightning instead of the old network icon', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, isNot(contains('Icons.network_ping_rounded')));
    expect(dashboard, contains('Icons.bolt_rounded'));
    expect(dashboard, contains("tooltip: tr('تست پینگ', 'Ping server')"));
    expect(dashboard, contains("tr('تست پینگ همه سرورها', 'Ping all servers')"));
    expect(dashboard, contains("Key('livePingLightningIcon')"));
  });

  test('shared background takes real per-tenant primary and secondary colors', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    final ambient = File('lib/ambient_background.dart').readAsStringSync();
    expect(dashboard, contains('primaryColor: purple'));
    expect(dashboard, contains('BrandTheme.secondaryAccent(widget.brand)'));
    expect(ambient, contains('final Color primaryColor'));
    expect(ambient, contains('final Color secondaryColor'));
    expect(ambient, contains('duration: const Duration(milliseconds: 1250)'));
  });
}
