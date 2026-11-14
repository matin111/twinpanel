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

  test('connection fabric animates only on verified traffic', () {
    final wave = File('lib/twinconnect_wave_indicator.dart').readAsStringSync();
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(wave, contains('if (_animate)'));
    expect(wave, contains('if (!_animate && _motion.isAnimating)'));
    expect(dashboard, contains('connected: _verifiedConnectionActive'));
    expect(dashboard, contains("Key('liveConnectionDataFabric')"));
    expect(wave, contains('widget.connected && _trafficPresent'));
    expect(wave, contains('maxRx > 0 || maxTx > 0'));
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
    expect(androidCard, contains('_autoNode(profiles, selectedNodeId)'));
  });

  test('Android Connect tab clears unsupported Servers protocol selection', () {
    final dashboard = File('lib/live_dashboard.dart').readAsStringSync();
    expect(dashboard, contains('if (index == 0) {'));
    expect(dashboard, contains("_filter = 'all';"));
    expect(dashboard, contains('_androidExplicitNodeSelected = false;'));
    expect(dashboard, contains("widget.native.supports(_filter)"));
    expect(dashboard, contains("selectedProtocolCode: _filter != 'all' &&"));
  });

  test('Android offers all entitled protocols without claiming missing engines', () {
    final android = File('lib/android_connection_card.dart').readAsStringSync();
    final native = File('native/android/kotlin/com/twinpanel/twinconnect/MainActivity.kt')
        .readAsStringSync();
    expect(android, contains("widget.catalog.entries"));
    expect(android, contains(".where((entry) => entry.selected)"));
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
    expect(android, contains('Connection unavailable'));
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
    expect(card, contains('WireGuardNode? _autoNode('));
    expect(card, contains('widget.servers?.servers'));
    expect(card, contains('matching.nodeOnline'));
    expect(card, contains('selectedNodeId != null && id != selectedNodeId'));
    expect(card, contains('candidates.sort('));
    expect(card, isNot(contains('showDialog<WireGuardNode>')));
    expect(dashboard, contains('servers: widget.servers'));
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
    expect(native, contains('getStatistics(tunnel)'));
    expect(native, contains('statistics.totalRx()'));
    expect(native, contains('statistics.totalTx()'));
    expect(native, contains('latestHandshakeEpochMillis()'));
    expect(card, contains("status['rxBytes']"));
    expect(card, contains("status['txBytes']"));
    expect(card, contains("status['peerHandshakeVerified']"));
    expect(card, contains("Uri.https('api.ipify.org', '/')"));
    expect(card, contains("_speed(_downloadBps)"));
    expect(card, contains("_speed(_uploadBps)"));
    expect(card, contains("Icons.bolt, 'HTTPS'"));
    expect(card, contains('_telemetryTimer?.cancel()'));
  });

  test('Cisco Android uses an isolated engine, not a WireGuard tunnel', () {
    final controller = File('lib/android_tunnel.dart').readAsStringSync();
    final card = File('lib/android_connection_card.dart').readAsStringSync();
    final native = File(
      'native/android/kotlin/com/twinpanel/twinconnect/MainActivity.kt',
    ).readAsStringSync();
    expect(controller, contains("nativeProtocols.supports('cisco')"));
    expect(controller, contains("'startOpenConnect'"));
    expect(controller, contains("'stopOpenConnect'"));
    expect(controller, contains("'getOpenConnectStatus'"));
    expect(controller, contains("'trafficRoutingVerified'"));
    expect(card, contains('CiscoOpenConnectProfile.fromItem(item)'));
    expect(card, contains("loadSessionNativeProfiles("));
    expect(card, contains("_controller.connectCisco("));
    expect(card, contains("_controller.ciscoStatus()"));
    expect(native, contains('"OPENCONNECT_CORE_NOT_INSTALLED"'));
    expect(native, contains('listOf("wireguard")'));
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
