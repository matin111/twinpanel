import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'protocols.dart';
import 'country_flag.dart';
import 'ambient_background.dart';
import 'interactive_glass_card.dart';

/// Visual-only desktop preview. No real VPN session, ping or account is created.
void main() => runApp(const TwinConnectDevApp());

class TwinConnectDevApp extends StatefulWidget {
  const TwinConnectDevApp({super.key});
  @override
  State<TwinConnectDevApp> createState() => _TwinConnectDevAppState();
}

class _DemoServer {
  const _DemoServer(this.flag, this.country, this.city, this.protocols);
  final String flag;
  final String country;
  final String city;
  final List<String> protocols;
}

class _TwinConnectDevAppState extends State<TwinConnectDevApp> {
  bool _persian = true;
  bool _dark = true;
  String _page = 'home';
  String _filter = 'all';
  String _search = '';
  int _selected = 0;
  final Set<int> _favorites = <int>{};

  static const purple = Color(0xFFA46AFF);
  static const demoServers = <_DemoServer>[
    _DemoServer('DE', 'Germany', 'Frankfurt',
        ['openvpn', 'v2ray', 'hysteria2', 'shadowtls', 'sudoku']),
    _DemoServer('NL', 'Netherlands', 'Amsterdam',
        ['wireguard', 'tuic', 'naive', 'trusttunnel']),
    _DemoServer('GB', 'United Kingdom', 'London',
        ['cisco', 'anytls', 'snell', 'amneziawg']),
    _DemoServer('US', 'United States', 'New York',
        ['l2tp', 'socks5', 'mieru']),
    _DemoServer('SG', 'Singapore', 'Singapore', [
        'openvpn', 'wireguard', 'v2ray', 'hysteria2', 'tuic', 'anytls',
        'naive', 'shadowtls', 'snell', 'socks5', 'mieru',
        'trusttunnel', 'amneziawg', 'sudoku', 'cisco', 'l2tp',
    ]),
  ];

  String tr(String fa, String en) => _persian ? fa : en;

  @override
  Widget build(BuildContext context) {
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
        'برای دریافت سرورها وارد حساب شوید',
        'Sign in to fetch updated servers',
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
            txt(tr('حساب آزمایشی', 'Demo account'), bold: true, size: 11),
            const SizedBox(height: 3),
            txt(tr('بدون اشتراک واقعی', 'No live subscription'),
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
      key: const Key('devConnectionStatus'),
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 15),
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
            child: smallPill(tr('آفلاین', 'Offline'), icon: Icons.circle),
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
          child: Container(
            height: 94, width: 94,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: purple, width: 2.5),
              gradient: RadialGradient(colors: [
                purple.withValues(alpha: 0.42),
                purple.withValues(alpha: 0.05),
              ]),
              boxShadow: [
                BoxShadow(color: purple.withValues(alpha: 0.32),
                  blurRadius: 43, spreadRadius: 4),
              ],
            ),
            child: const Icon(Icons.power_settings_new_rounded,
                size: 45, color: purple),
          ),
        ),
        const SizedBox(height: 12),
        txt(tr('اتصال سریع', 'Quick connect'), size: 20, bold: true),
        const SizedBox(height: 5),
        txt(tr('موتور اتصال آماده نیست', 'Connection engine unavailable'),
            size: 12, color: sub),
        const SizedBox(height: 12),
        SizedBox(
          width: 215, height: 43,
          child: FilledButton.icon(
            key: const Key('devConnectButton'),
            onPressed: null,
            style: FilledButton.styleFrom(
              disabledBackgroundColor: purple.withValues(alpha: 0.40),
              disabledForegroundColor: ink.withValues(alpha: 0.73),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(15)),
            ),
            icon: const Icon(Icons.bolt_rounded),
            label: Text(tr('اتصال', 'Connect')),
          ),
        ),
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
                  CountryFlag(demoServers[_selected].flag, width: 24),
                  const SizedBox(width: 6),
                  Flexible(child: txt(demoServers[_selected].country, size: 11, bold: true)),
                ]),
            ])),
            Expanded(child: Column(children: [
              txt(tr('آی‌پی', 'IP'), size: 10, color: sub),
              const SizedBox(height: 4),
              txt('—', size: 11, bold: true),
            ])),
            Expanded(child: Column(children: [
              txt(tr('پروتکل', 'Protocol'), size: 10, color: sub),
              const SizedBox(height: 4),
              txt(_filter == 'all'
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
        child: smallPill('DEV'),
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
          onTap: () => setState(() => _selected = index),
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
                  txt(tr('نمونه آزمایشی', 'Sample server'), size: 10, color: sub),
                ],
              )),
              txt('— ms', size: 11, color: sub),
              const SizedBox(width: 8),
              Icon(Icons.lock_outline, size: 17, color: sub),
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
                  demoServers[i].protocols.contains(_filter)) &&
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
              onPressed: notification,
              icon: const Icon(Icons.refresh_rounded),
            ),
          ]),
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
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(icon, color: purple, size: 18),
            const SizedBox(width: 8),
            Expanded(child: txt(title, size: 11, color: sub)),
          ]),
          const SizedBox(height: 10),
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
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Expanded(child: txt(tr('وضعیت شبکه', 'Network status'),
              size: 17, bold: true)),
            smallPill(tr('بدون اتصال', 'Disconnected')),
          ]),
          const SizedBox(height: 16),
          Row(children: [
            Expanded(child: metric(Icons.speed_rounded,
              tr('پینگ', 'Ping'), '— ms')),
            const SizedBox(width: 10),
            Expanded(child: metric(Icons.public_rounded,
              tr('آی‌پی', 'IP address'), '—')),
          ]),
          const SizedBox(height: 10),
          Row(children: [
            Expanded(child: metric(Icons.arrow_downward_rounded,
              tr('دانلود', 'Download'), '— B/s',
              detail: tr('مصرف: —', 'Used: —'))),
            const SizedBox(width: 10),
            Expanded(child: metric(Icons.arrow_upward_rounded,
              tr('آپلود', 'Upload'), '— B/s',
              detail: tr('مصرف: —', 'Used: —'))),
          ]),
          const SizedBox(height: 14),
          Container(
            decoration: tile(radius: 14),
            padding: const EdgeInsets.all(12),
            child: Row(children: [
              CountryFlag(demoServers[_selected].flag, width: 30),
              const SizedBox(width: 9),
              Expanded(child: txt(demoServers[_selected].country, bold: true)),
              txt(tr('نمونه', 'Demo'), color: sub, size: 10),
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
          key: const Key('devAutoSelectCard'),
          radius: 19,
          padding: const EdgeInsets.symmetric(horizontal: 17, vertical: 8),
          child: Row(children: [
            const Icon(Icons.auto_awesome_rounded, size: 19, color: purple),
            const SizedBox(width: 11),
            Expanded(child: txt(tr('انتخاب خودکار بهترین سرور',
                'Automatic best server'), size: 13, bold: true)),
            const Switch(
              key: Key('devAutoBestServer'),
              value: false,
              onChanged: null,
            ),
          ]),
        ),
        const SizedBox(height: 15),
        glassCard(
          key: const Key('devLocationsCard'),
          radius: 23,
          padding: const EdgeInsets.fromLTRB(15, 11, 15, 10),
          child: Column(children: [
            Row(children: [
              Expanded(child: txt(tr('مکان‌ها', 'Locations'),
                size: 18, bold: true)),
              TextButton(
                onPressed: () => setState(() => _page = 'locations'),
                child: Text(tr('نمایش همه', 'View all')),
              ),
            ]),
            const SizedBox(height: 5),
            for (int i = 0; i < 2; i++) serverRow(i),
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
                txt(tr('تنظیمات سیستم پس از نصب موتور فعال می‌شوند',
                       'System options unlock after engine installation'),
                    size: 11, color: sub),
              ],
            )),
          ]),
        ),
        const SizedBox(height: 17),
        settingLine(Icons.shield_outlined, 'Kill Switch'),
        settingLine(Icons.dns_outlined, tr('حفاظت DNS', 'DNS protection')),
        settingLine(Icons.security_outlined,
            tr('حفاظت IPv6', 'IPv6 protection')),
        settingLine(Icons.auto_awesome_rounded,
            tr('اتصال خودکار', 'Auto-connect')),
        const SizedBox(height: 9),
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

    Widget account() => Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        heading(tr('حساب', 'Account')),
        const SizedBox(height: 16),
        ClipRRect(
          borderRadius: BorderRadius.circular(26),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
            child: Container(
              padding: const EdgeInsets.all(25),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(26),
                gradient: LinearGradient(colors: _dark
                    ? [const Color(0xFF3B275E).withValues(alpha: 0.75),
                       const Color(0xFF252746).withValues(alpha: 0.70)]
                    : [const Color(0xFFEDE1FF).withValues(alpha: 0.80),
                       Colors.white.withValues(alpha: 0.74)]),
                border: Border.all(color: purple.withValues(alpha: 0.45)),
              ),
              child: Row(children: [
            Container(
              width: 76, height: 76,
              decoration: BoxDecoration(
                color: purple.withValues(alpha: 0.17),
                borderRadius: BorderRadius.circular(20)),
              child: const Icon(Icons.workspace_premium_rounded,
                  size: 43, color: purple),
            ),
            const SizedBox(width: 18),
            Expanded(child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                txt(tr('حساب آزمایشی', 'Demo account'), size: 22, bold: true),
                const SizedBox(height: 6),
                txt(tr('اشتراک واقعی دریافت نشده', 'No live subscription'),
                    color: sub, size: 12),
              ],
            )),
          ]),
            ),
          ),
        ),
        const SizedBox(height: 17),
        Row(children: [
          for (final entry in [
            (Icons.devices_rounded, tr('دستگاه‌ها', 'Devices')),
            (Icons.data_usage_rounded, tr('ترافیک', 'Traffic')),
            (Icons.event_outlined, tr('انقضا', 'Expiry')),
          ]) ...[
            Expanded(child: glassCard(
              padding: const EdgeInsets.symmetric(vertical: 18),
              radius: 18,
              child: Column(children: [
                Icon(entry.$1, color: purple),
                const SizedBox(height: 8),
                txt('—', size: 20, bold: true),
                txt(entry.$2, size: 11, color: sub),
              ]),
            )),
            const SizedBox(width: 8),
          ],
        ]),
      ],
    );

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
