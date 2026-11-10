import 'package:flutter/material.dart';

import 'ambient_background.dart';
import 'connection_signal_art.dart';
import 'country_flag.dart';
import 'interactive_glass_card.dart';
import 'protocol_catalog_view.dart';
import 'protocols.dart';
import 'server_inventory.dart';
import 'tenant_api.dart';
import 'tenant_models.dart';
import 'windows_connection_card.dart';
import 'android_connection_card.dart';
import 'share_vpn_preview.dart';
import 'native_vpn_bridge.dart';
import 'vpn_settings.dart';

/// Production-data shell matching the previously approved four-page design.
/// No demo servers, invented latency, false "connected" labels or fake traffic.
class AuthenticatedDashboard extends StatefulWidget {
  const AuthenticatedDashboard({
    required this.panel,
    required this.username,
    required this.sessionToken,
    required this.brand,
    required this.servers,
    required this.catalog,
    required this.nativeProtocols,
    required this.refreshServers,
    required this.refreshingServers,
    required this.protocolCatalogUnavailable,
    required this.onLogout,
    super.key,
  });

  final PanelDirectoryEntry panel;
  final String username;
  final String sessionToken;
  final BrandPreview brand;
  final AppServerInventory? servers;
  final PanelProtocolCatalog? catalog;
  final NativeProtocolReadiness nativeProtocols;
  final VoidCallback refreshServers;
  final bool refreshingServers;
  final bool protocolCatalogUnavailable;
  final VoidCallback onLogout;

  @override
  State<AuthenticatedDashboard> createState() => _AuthenticatedDashboardState();
}

class _AuthenticatedDashboardState extends State<AuthenticatedDashboard> {
  static const purple = Color(0xFFA46AFF);
  String _page = 'home';
  String _search = '';
  String? _selectedId;
  final Set<String> _favorites = <String>{};

  bool get _dark => Theme.of(context).brightness == Brightness.dark;
  bool get _persian => Localizations.localeOf(context).languageCode == 'fa';
  String tr(String fa, String en) => _persian ? fa : en;
  List<AppServer> get _servers => widget.servers?.servers ?? const <AppServer>[];

  AppServer? get _selected {
    for (final server in _servers) {
      if (server.id == _selectedId) return server;
    }
    return _servers.isEmpty ? null : _servers.first;
  }

  Widget _label(String value, {double size = 13, bool bold = false,
    Color? color}) => Text(value, maxLines: 2,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(color: color ??
        Theme.of(context).colorScheme.onSurface, fontSize: size,
        fontWeight: bold ? FontWeight.w700 : FontWeight.w400));

  Widget _glass(Widget child, {Key? key, bool selected = false,
      EdgeInsetsGeometry padding = const EdgeInsets.all(17),
      double radius = 22}) => TwinConnectGlassCard(
        key: key, dark: _dark, selected: selected,
        radius: radius, padding: padding, child: child);

  Widget _nav(String page, IconData icon, String name) => Padding(
    padding: const EdgeInsets.only(bottom: 7),
    child: Material(
      color: page == _page ? purple.withValues(alpha: .18) : Colors.transparent,
      borderRadius: BorderRadius.circular(13),
      child: InkWell(
        key: Key('liveNav_$page'),
        borderRadius: BorderRadius.circular(13),
        onTap: () => setState(() => _page = page),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 13),
          child: Row(children: [
            Icon(icon, size: 20,
                color: page == _page ? purple : Colors.blueGrey.shade300),
            const SizedBox(width: 10),
            Expanded(child: _label(name, bold: page == _page)),
          ]),
        ),
      ),
    ),
  );

  Widget _sidebar() => Container(
    width: 192,
    padding: const EdgeInsets.fromLTRB(12, 22, 12, 15),
    color: (_dark ? const Color(0xFF11182F) : const Color(0xFFF0EDFB))
        .withValues(alpha: .85),
    child: Column(children: [
      Container(width: 43, height: 43,
        decoration: BoxDecoration(
          gradient: const LinearGradient(colors: [
            Color(0xFFC68AFF), Color(0xFF7051D4)]),
          borderRadius: BorderRadius.circular(12)),
        child: const Icon(Icons.all_inclusive_rounded, color: Colors.white)),
      const SizedBox(height: 9),
      _label('TwinConnect', bold: true, size: 17),
      const SizedBox(height: 30),
      _nav('home', Icons.bolt_rounded, tr('اتصال سریع', 'Quick connect')),
      _nav('locations', Icons.place_outlined, tr('مکان‌ها', 'Locations')),
      _nav('settings', Icons.tune_rounded, tr('تنظیمات', 'Settings')),
      _nav('account', Icons.person_outline_rounded, tr('حساب', 'Account')),
      const Spacer(),
      _glass(Column(children: [
        _label(tr('اشتراک فعال', 'Active subscription'), bold: true, size: 11),
        _label(widget.panel.namespace, size: 10),
      ]), padding: const EdgeInsets.all(12), radius: 17),
      IconButton(
        key: const Key('liveLogout'),
        tooltip: tr('خروج', 'Sign out'),
        onPressed: widget.onLogout,
        icon: const Icon(Icons.logout_rounded)),
    ]),
  );

  Widget _serverTile(AppServer node) => Padding(
    padding: const EdgeInsets.only(bottom: 9),
    child: _glass(Row(children: [
      CountryFlag(node.countryCode, width: 29),
      const SizedBox(width: 10),
      Expanded(child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _label(node.name, bold: true, size: 12),
          _label(node.nodeOnline
              ? tr('نود آنلاین؛ VPN تأیید نشده', 'Node online; VPN unverified')
              : tr('وضعیت نود نامشخص', 'Node status unverified'),
              size: 10, color: Colors.blueGrey.shade300),
        ])),
      _label(node.latencyMs == null ? '— ms' : '${node.latencyMs} ms',
          size: 11),
      IconButton(
        tooltip: tr('علاقه‌مندی', 'Favorite'),
        onPressed: () => setState(() {
          if (!_favorites.add(node.id)) _favorites.remove(node.id);
        }),
        icon: Icon(_favorites.contains(node.id)
            ? Icons.star_rounded : Icons.star_border_rounded, color: purple)),
    ]), key: Key('liveServer_${node.id}'),
        selected: _selected?.id == node.id, radius: 17,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8)),
  );

  Widget _serversView({bool search = false}) {
    final nodes = _servers.where((node) =>
        !search || _search.isEmpty ||
        node.name.toLowerCase().contains(_search.toLowerCase()) ||
        node.countryCode.toLowerCase().contains(_search.toLowerCase())).toList();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Row(children: [
        Expanded(child: _label(tr('مکان‌ها', 'Locations'), size: 17, bold: true)),
        IconButton(
          key: const Key('liveRefreshServers'),
          onPressed: widget.refreshingServers ? null : widget.refreshServers,
          icon: widget.refreshingServers
              ? const SizedBox.square(dimension: 16,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.refresh_rounded)),
      ]),
      if (search) ...[
        const SizedBox(height: 7),
        TextField(
          key: const Key('liveServerSearch'),
          decoration: InputDecoration(
            prefixIcon: const Icon(Icons.search_rounded),
            hintText: tr('جستجوی سرور', 'Search servers'),
            border: const OutlineInputBorder()),
          onChanged: (text) => setState(() => _search = text)),
        const SizedBox(height: 12),
      ],
      if (widget.servers == null)
        _glass(_label(tr('دریافت سرورها...', 'Loading servers...')))
      else if (nodes.isEmpty)
        _glass(_label(tr('سروری برای نمایش وجود ندارد', 'No assigned servers')))
      else
        for (final node in nodes) InkWell(
          onTap: () => setState(() => _selectedId = node.id),
          child: _serverTile(node)),
    ]);
  }

  Widget _quickCard() => _glass(Column(children: [
    _label(tr('وضعیت VPN تأیید نشده', 'VPN not verified'), size: 11),
    const SizedBox(height: 15),
    Container(width: 98, height: 98,
      decoration: BoxDecoration(shape: BoxShape.circle,
        border: Border.all(color: purple, width: 2.5),
        gradient: RadialGradient(colors: [
          purple.withValues(alpha: .34), purple.withValues(alpha: .05)])),
      child: const Icon(Icons.power_settings_new_rounded,
          size: 46, color: purple)),
    const SizedBox(height: 14),
    _label(tr('اتصال سریع', 'Quick connect'), size: 20, bold: true),
    const SizedBox(height: 5),
    _label(tr('برای اتصال از بخش پروتکل‌های مجاز استفاده کنید',
        'Use an available protocol below'), size: 11),
    const SizedBox(height: 12),
    ConnectionSignalArt(dark: _dark),
    const SizedBox(height: 13),
    _glass(Row(children: [
      if (_selected != null) ...[
        CountryFlag(_selected!.countryCode, width: 23),
        const SizedBox(width: 8),
        Expanded(child: _label(_selected!.name, bold: true, size: 11)),
      ] else
        Expanded(child: _label(tr('سروری انتخاب نشده', 'No assigned server'))),
      _label('— ms', size: 11),
    ]), radius: 15, padding: const EdgeInsets.all(10)),
  ]), key: const Key('liveQuickConnectCard'), radius: 28);

  Widget _networkCard() => _glass(Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      _label(tr('وضعیت شبکه', 'Network status'), size: 17, bold: true),
      const SizedBox(height: 5),
      _label(tr('اطلاعات اتصال هنوز اندازه‌گیری نشده',
          'Connection metrics not measured'), size: 10),
      const SizedBox(height: 14),
      GridView.count(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        crossAxisCount: 2, childAspectRatio: 2.0,
        crossAxisSpacing: 9, mainAxisSpacing: 9,
        children: [
          for (final item in [
            [tr('پینگ', 'Ping'), '— ms', Icons.speed_rounded],
            [tr('آی‌پی', 'Exit IP'), '—', Icons.public_rounded],
            [tr('دانلود', 'Download'), '— B/s', Icons.arrow_downward_rounded],
            [tr('آپلود', 'Upload'), '— B/s', Icons.arrow_upward_rounded],
          ])
            _glass(Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Row(children: [
                  Icon(item[2] as IconData, size: 16, color: purple),
                  const SizedBox(width: 6),
                  Expanded(child: _label(item[0] as String, size: 11)),
                ]),
                const SizedBox(height: 6),
                _label(item[1] as String, bold: true, size: 15),
              ]), padding: const EdgeInsets.symmetric(horizontal: 11),
              radius: 15),
        ],
      ),
    ]), key: const Key('liveNetworkCard'));

  Widget _connectionControls() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (widget.catalog != null) ...[
        _glass(ProtocolCatalogCard(catalog: widget.catalog!,
            native: widget.nativeProtocols)),
        const SizedBox(height: 12),
        AndroidConnectionCard(
          panel: widget.panel, username: widget.username,
          sessionToken: widget.sessionToken,
          catalog: widget.catalog!, native: widget.nativeProtocols),
        if (widget.servers != null)
          WindowsConnectionCard(
            panel: widget.panel, username: widget.username,
            sessionToken: widget.sessionToken,
            catalog: widget.catalog!, servers: widget.servers!),
      ] else
        _glass(_label(widget.protocolCatalogUnavailable
            ? tr('دریافت پروتکل‌های اشتراک ناموفق بود',
                'Could not load subscription protocols')
            : tr('دریافت پروتکل‌ها...', 'Loading protocols...'))),
    ],
  );

  Widget _home() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _label(tr('اتصال سریع', 'Quick connect'), size: 23, bold: true),
      const SizedBox(height: 17),
      LayoutBuilder(builder: (context, constraints) {
        if (constraints.maxWidth < 700) return Column(children: [
          _quickCard(), const SizedBox(height: 13), _networkCard(),
        ]);
        return Row(crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(child: _quickCard()),
            const SizedBox(width: 14),
            Expanded(child: _networkCard()),
          ]);
      }),
      const SizedBox(height: 15),
      _serversView(),
      const SizedBox(height: 14),
      _connectionControls(),
    ]);

  Widget _locations() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _label(tr('مکان‌ها', 'Locations'), size: 23, bold: true),
      const SizedBox(height: 17),
      _glass(_serversView(search: true)),
      const SizedBox(height: 12),
      _connectionControls(),
    ]);

  Widget _settings() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _label(tr('تنظیمات', 'Settings'), size: 23, bold: true),
      const SizedBox(height: 15),
      ShareVpnPreview(dark: _dark, persian: _persian),
      const SizedBox(height: 15),
      _glass(ListTile(
        leading: const Icon(Icons.tune_rounded, color: purple),
        title: _label(tr('تنظیمات اتصال', 'VPN settings')),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute<void>(builder: (_) => VpnSettingsScreen(
            brand: widget.brand,
            tenant: widget.panel.namespace,
            account: widget.username)),
        ),
      )),
    ]);

  Widget _account() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _label(tr('حساب', 'Account'), size: 23, bold: true),
      const SizedBox(height: 15),
      _glass(Column(
        crossAxisAlignment: CrossAxisAlignment.start, children: [
          _label(tr('اشتراک فعال', 'Active subscription'), bold: true,
              size: 17),
          const SizedBox(height: 12),
          _label(widget.brand.brandName, size: 16),
          const SizedBox(height: 8),
          SelectableText(widget.username, textDirection: TextDirection.ltr),
          const SizedBox(height: 8),
          _label(widget.panel.namespace),
          const SizedBox(height: 16),
          OutlinedButton.icon(
            onPressed: widget.onLogout,
            icon: const Icon(Icons.logout_rounded),
            label: Text(tr('خروج از حساب', 'Sign out'))),
        ]),
      ),
    ]);

  @override
  Widget build(BuildContext context) {
    final view = switch (_page) {
      'locations' => _locations(),
      'settings' => _settings(),
      'account' => _account(),
      _ => _home(),
    };
    return Scaffold(
      body: TwinConnectAmbientBackground(
        dark: _dark,
        child: SafeArea(
          child: Row(children: [
            _sidebar(),
            Expanded(child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(24, 25, 24, 35),
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 260),
                child: KeyedSubtree(
                  key: ValueKey(_page),
                  child: view,
                ),
              ),
            )),
          ]),
        ),
      ),
    );
  }
}
