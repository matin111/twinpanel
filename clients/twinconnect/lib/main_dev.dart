import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'brand_theme.dart';
import 'vpn_settings.dart';
import 'windows_preview_fixture.dart';

/// Isolated offline UI build; it cannot authenticate or start VPN connections.
void main() => runApp(const TwinConnectDevApp());

class TwinConnectDevApp extends StatefulWidget {
  const TwinConnectDevApp({super.key});

  @override
  State<TwinConnectDevApp> createState() => _TwinConnectDevAppState();
}

class _TwinConnectDevAppState extends State<TwinConnectDevApp> {
  bool _persian = true;
  bool _dark = true;
  String _search = '';
  String _section = 'all';
  String _page = 'home';

  String t(String fa, String en) => _persian ? fa : en;

  @override
  Widget build(BuildContext context) {
    final brand = WindowsPreviewFixture.brand();
    final accent = BrandTheme.parse(brand.primaryColor, '#7358DF');
    final entries = WindowsPreviewFixture.protocolCatalog().entries;
    final filtered = entries.where((item) =>
      (_section == 'all' || item.protocol.engine.name == _section) &&
      item.protocol.name.toLowerCase().contains(_search.toLowerCase())
    ).toList();

    return MaterialApp(
      title: 'TwinConnect Dev',
      debugShowCheckedModeBanner: false,
      locale: Locale(_persian ? 'fa' : 'en'),
      supportedLocales: const [Locale('fa'), Locale('en')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      theme: BrandTheme.make(brand, Brightness.light),
      darkTheme: BrandTheme.make(brand, Brightness.dark),
      themeMode: _dark ? ThemeMode.dark : ThemeMode.light,
      home: Builder(builder: (context) {
        final theme = Theme.of(context);
        final dark = theme.brightness == Brightness.dark;
        final foreground = theme.colorScheme.onSurface;
        final muted = foreground.withValues(alpha: 0.56);
        final surface = theme.colorScheme.surface;
        final wide = MediaQuery.sizeOf(context).width >= 920;
        final medium = MediaQuery.sizeOf(context).width >= 650;
        final navBg = dark ? const Color(0xFF101629) : const Color(0xFFF4F5FB);
        final border = foreground.withValues(alpha: 0.08);
        final options = <String, String>{
          'all': t('همه', 'All'),
          'openvpn': 'OpenVPN',
          'wireguard': 'WireGuard',
          'openconnect': 'Cisco',
          'xray': 'Xray',
          'singbox': 'Sing-box',
        };

        Widget tab(String code, IconData icon, String title) => Material(
          color: _page == code ? accent.withValues(alpha: 0.16) : Colors.transparent,
          borderRadius: BorderRadius.circular(15),
          child: InkWell(
            borderRadius: BorderRadius.circular(15),
            onTap: () {
              if (code == 'settings') {
                Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => VpnSettingsScreen(
                    tenant: '', account: '', brand: brand,
                  ),
                ));
              } else {
                setState(() => _page = code);
              }
            },
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: wide ? 15 : 8, vertical: 14),
              child: Row(children: [
                Icon(icon, color: _page == code ? accent : muted, size: wide ? 22 : 20),
                if (wide) ...[
                  const SizedBox(width: 13),
                  Expanded(child: Text(title, style: TextStyle(
                    fontWeight: _page == code ? FontWeight.w700 : FontWeight.w500,
                    color: _page == code ? foreground : muted,
                  ))),
                ],
              ]),
            ),
          ),
        );

        Widget hero() => Container(
          key: const Key('devConnectionStatus'),
          constraints: const BoxConstraints(minHeight: 308),
          padding: const EdgeInsets.all(28),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(30),
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: dark
                  ? [const Color(0xFF30235B), const Color(0xFF1C2648), const Color(0xFF17283B)]
                  : [const Color(0xFFEEE7FF), const Color(0xFFE1EEFF), const Color(0xFFF3F5FF)],
            ),
            border: Border.all(color: accent.withValues(alpha: 0.28)),
            boxShadow: [BoxShadow(
              color: accent.withValues(alpha: dark ? 0.13 : 0.09),
              blurRadius: 45, offset: const Offset(0, 18),
            )],
          ),
          child: Column(
            children: [
              Row(children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                  decoration: BoxDecoration(
                    color: foreground.withValues(alpha: 0.07),
                    borderRadius: BorderRadius.circular(40),
                  ),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    const Icon(Icons.circle, size: 8, color: Color(0xFFFFB464)),
                    const SizedBox(width: 8),
                    Text(t('آفلاین', 'Offline'), style: const TextStyle(fontSize: 12)),
                  ]),
                ),
                const Spacer(),
                const Icon(Icons.more_horiz_rounded),
              ]),
              const SizedBox(height: 21),
              Container(
                width: 104, height: 104,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: accent.withValues(alpha: 0.25), width: 2),
                  boxShadow: [BoxShadow(color: accent.withValues(alpha: 0.21),
                    blurRadius: 36, spreadRadius: 3)],
                  gradient: LinearGradient(colors: [
                    accent.withValues(alpha: 0.26),
                    accent.withValues(alpha: 0.08),
                  ]),
                ),
                child: Icon(Icons.power_settings_new_rounded, size: 49, color: accent),
              ),
              const SizedBox(height: 20),
              Text(t('متصل نیست', 'Not connected'),
                style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 27)),
              const SizedBox(height: 5),
              Text(t('موتور ویندوز آماده نیست', 'Windows engine unavailable'),
                style: TextStyle(color: muted, fontSize: 12)),
              const SizedBox(height: 20),
              Tooltip(
                message: t('پس از اتصال موتور و دریافت پینگ واقعی فعال می‌شود',
                           'Requires native engine and measured latency'),
                child: Row(mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.auto_awesome_rounded, size: 16),
                    const SizedBox(width: 7),
                    Text(t('انتخاب خودکار بهترین سرور',
                           'Auto-select best server'),
                         style: TextStyle(color: muted, fontSize: 12)),
                  ]),
              ),
              const SizedBox(height: 12),
              SizedBox(
                width: 230, height: 47,
                child: FilledButton.icon(
                  key: const Key('devConnectButton'),
                  onPressed: null,
                  icon: const Icon(Icons.power_settings_new_rounded, size: 19),
                  label: Text(t('اتصال', 'Connect')),
                  style: FilledButton.styleFrom(
                    disabledBackgroundColor: accent.withValues(alpha: 0.35),
                    disabledForegroundColor: foreground.withValues(alpha: 0.70),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(15)),
                  ),
                ),
              ),
            ],
          ),
        );

        Widget summaryCard(IconData icon, String title, String value) => Expanded(
          child: Container(
            padding: const EdgeInsets.all(15),
            decoration: BoxDecoration(
              color: surface, borderRadius: BorderRadius.circular(18),
              border: Border.all(color: border),
            ),
            child: Row(children: [
              Container(
                width: 38, height: 38,
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(12)),
                child: Icon(icon, color: accent, size: 19)),
              const SizedBox(width: 11),
              Expanded(child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 11, color: muted)),
                  const SizedBox(height: 3),
                  Text(value, maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
                ],
              )),
            ]),
          ),
        );

        Widget protocols() => Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: surface, borderRadius: BorderRadius.circular(25),
            border: Border.all(color: border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(children: [
                Expanded(child: Text(t('مکان‌ها', 'Locations'),
                  style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800))),
                IconButton(
                  key: const Key('devRefreshServers'),
                  tooltip: t('به‌روزرسانی سرورها', 'Refresh servers'),
                  icon: const Icon(Icons.refresh_rounded),
                  onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text(t('برای دریافت سرورها وارد حساب شوید',
                      'Sign in to fetch updated servers')))),
                ),
              ]),
              const SizedBox(height: 11),
              TextField(
                key: const Key('devProtocolSearch'),
                onChanged: (v) => setState(() => _search = v),
                decoration: InputDecoration(
                  hintText: t('جستجوی پروتکل', 'Search protocol'),
                  prefixIcon: const Icon(Icons.search_rounded),
                  filled: true,
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
                ),
              ),
              const SizedBox(height: 12),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(children: [
                  for (final entry in options.entries) ...[
                    ChoiceChip(
                      key: Key('devFilter_\${entry.key}'),
                      label: Text(entry.value),
                      selected: _section == entry.key,
                      onSelected: (_) => setState(() => _section = entry.key),
                      showCheckmark: false,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12)),
                    ),
                    const SizedBox(width: 8),
                  ],
                ]),
              ),
              const SizedBox(height: 14),
              SizedBox(height: 39, child: ListView(
                scrollDirection: Axis.horizontal,
                children: [
                  for (final item in filtered)
                    Container(
                      key: Key('devProtocol_\${item.protocol.code}'),
                      alignment: Alignment.center,
                      margin: const EdgeInsetsDirectional.only(end: 8),
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      decoration: BoxDecoration(
                        color: accent.withValues(alpha: 0.09),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: border),
                      ),
                      child: Text(item.protocol.name, style: const TextStyle(fontSize: 11)),
                    ),
                ],
              )),
              const SizedBox(height: 18),
              for (final location in const [
                ('🇩🇪', 'Germany · Frankfurt'),
                ('🇳🇱', 'Netherlands · Amsterdam'),
                ('🇬🇧', 'United Kingdom · London'),
                ('🇺🇸', 'United States · New York'),
                ('🇸🇬', 'Singapore'),
              ])
                Container(
                  margin: const EdgeInsets.only(bottom: 9),
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  decoration: BoxDecoration(
                    color: foreground.withValues(alpha: 0.045),
                    borderRadius: BorderRadius.circular(15),
                    border: Border.all(color: border),
                  ),
                  child: Row(children: [
                    Text(location.$1, style: const TextStyle(fontSize: 22)),
                    const SizedBox(width: 12),
                    Expanded(child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(location.$2, style: const TextStyle(
                          fontWeight: FontWeight.w700, fontSize: 13)),
                        Text(t('نمونه نمایشی', 'Sample only'),
                          style: TextStyle(fontSize: 10, color: muted)),
                      ],
                    )),
                    Text('— ms', style: TextStyle(fontSize: 11, color: muted)),
                    const SizedBox(width: 8),
                    const Icon(Icons.lock_outline_rounded, size: 17),
                  ]),
                ),
            ],
          ),
        );

        Widget dashboard() => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(children: [
              Expanded(child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t('اتصال سریع', 'Quick connect'),
                    style: const TextStyle(fontSize: 27, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 5),
                  Text(t('پیش‌نمایش رابط کاربری', 'Interface preview'),
                    key: const Key('devSampleNotice'),
                    style: TextStyle(color: muted, fontSize: 12)),
                ],
              )),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.11),
                  borderRadius: BorderRadius.circular(20)),
                child: Text('DEV', style: TextStyle(
                  color: accent, fontSize: 11, fontWeight: FontWeight.w800)),
              ),
            ]),
            const SizedBox(height: 23),
            if (medium)
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(flex: 5, child: hero()),
                const SizedBox(width: 17),
                Expanded(flex: 4, child: Column(children: [
                  Row(children: [
                    summaryCard(Icons.language_rounded,
                      t('کشورها', 'Countries'), '—'),
                    const SizedBox(width: 10),
                    summaryCard(Icons.dns_rounded,
                      t('سرورها', 'Servers'), '—'),
                  ]),
                  const SizedBox(height: 13),
                  Container(
                    height: 205,
                    padding: const EdgeInsets.all(22),
                    decoration: BoxDecoration(
                      color: surface, borderRadius: BorderRadius.circular(22),
                      border: Border.all(color: border),
                    ),
                    child: Center(child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.public_off_outlined, size: 34, color: muted),
                        const SizedBox(height: 11),
                        Text(t('سرور واقعی دریافت نشده', 'No live servers'),
                          style: const TextStyle(fontWeight: FontWeight.w700)),
                        const SizedBox(height: 5),
                        Text(t('بعد از اتصال حساب نمایش داده می‌شود',
                               'Available after account sign-in'),
                          textAlign: TextAlign.center,
                          style: TextStyle(color: muted, fontSize: 11)),
                      ],
                    )),
                  ),
                ])),
              ])
            else ...[
              hero(),
              const SizedBox(height: 15),
              Row(children: [
                summaryCard(Icons.language_rounded, t('کشورها', 'Countries'), '—'),
                const SizedBox(width: 10),
                summaryCard(Icons.dns_rounded, t('سرورها', 'Servers'), '—'),
              ]),
            ],
            const SizedBox(height: 23),
            protocols(),
          ],
        );

        return Scaffold(
          body: Row(children: [
            Container(
              width: wide ? 214 : 70,
              decoration: BoxDecoration(
                color: navBg, border: Border(right: BorderSide(color: border)),
              ),
              child: SafeArea(child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 20),
                child: Column(children: [
                  Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    Container(
                      width: 38, height: 38,
                      decoration: BoxDecoration(
                        gradient: LinearGradient(colors: [
                          accent, theme.colorScheme.secondary,
                        ]),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Icon(Icons.bolt_rounded,
                        color: Colors.white, size: 25),
                    ),
                    if (wide) ...[
                      const SizedBox(width: 9),
                      const Expanded(child: Text('TwinConnect',
                        style: TextStyle(fontWeight: FontWeight.w800,
                          fontSize: 17))),
                    ],
                  ]),
                  const SizedBox(height: 39),
                  tab('home', Icons.grid_view_rounded, t('خانه', 'Home')),
                  const SizedBox(height: 8),
                  tab('protocols', Icons.hub_outlined, t('پروتکل‌ها', 'Protocols')),
                  const SizedBox(height: 8),
                  tab('settings', Icons.tune_rounded, t('تنظیمات', 'Settings')),
                  const Spacer(),
                  IconButton(
                    key: const Key('devThemeToggle'),
                    tooltip: t('تغییر ظاهر', 'Theme'),
                    onPressed: () => setState(() => _dark = !_dark),
                    icon: Icon(_dark ? Icons.light_mode_outlined
                        : Icons.dark_mode_outlined),
                  ),
                  TextButton(
                    key: const Key('devLanguageToggle'),
                    onPressed: () => setState(() => _persian = !_persian),
                    child: Text(_persian ? 'EN' : 'فا'),
                  ),
                  IconButton(
                    key: const Key('devSettingsButton'),
                    tooltip: t('تنظیمات', 'Settings'),
                    onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => VpnSettingsScreen(
                        tenant: '', account: '', brand: brand),
                    )),
                    icon: const Icon(Icons.settings_outlined),
                  ),
                ]),
              )),
            ),
            Expanded(child: BrandBackground(
              brand: brand,
              child: SafeArea(child: ListView(
                padding: EdgeInsets.symmetric(
                  horizontal: wide ? 32 : 18, vertical: 27),
                children: [
                  Center(child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 1200),
                    child: _page == 'protocols'
                        ? protocols()
                        : dashboard(),
                  )),
                ],
              )),
            )),
          ]),
        );
      }),
    );
  }
}
