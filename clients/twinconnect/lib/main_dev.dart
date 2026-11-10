import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'brand_theme.dart';
import 'native_vpn_bridge.dart';
import 'protocols.dart';
import 'vpn_settings.dart';
import 'windows_preview_fixture.dart';

/// Local UI-only development entrypoint. Not included in production main.dart.
/// No license, session, share token, VPN configuration or private endpoint is
/// fabricated. This screen cannot connect to a VPN.
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

  @override
  Widget build(BuildContext context) {
    final brand = WindowsPreviewFixture.brand();
    final protocols = WindowsPreviewFixture.protocolCatalog().entries.where(
      (item) => (_section == 'all' || item.protocol.engine.name == _section) &&
          item.protocol.name.toLowerCase().contains(_search.toLowerCase()),
    ).toList();
    String label(String fa, String en) => _persian ? fa : en;
    final accent = BrandTheme.parse(brand.primaryColor, '#7358DF');

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
        final isWide = MediaQuery.sizeOf(context).width >= 800;
        final isDark = Theme.of(context).brightness == Brightness.dark;
        final surface = Theme.of(context).colorScheme.surface;
        final textColor = Theme.of(context).colorScheme.onSurface;
        final options = <String, String>{
          'all': label('همه', 'All'),
          'openvpn': 'OpenVPN',
          'wireguard': 'WireGuard',
          'openconnect': 'Cisco',
          'xray': 'Xray',
          'singbox': 'Sing-box',
        };

        Widget statusPanel() => Container(
          key: const Key('devConnectionStatus'),
          padding: const EdgeInsets.all(22),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                Color.lerp(surface, accent, isDark ? 0.19 : 0.07)!,
                surface,
              ],
            ),
            borderRadius: BorderRadius.circular(26),
            border: Border.all(color: accent.withValues(alpha: 0.28)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(13),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: accent.withValues(alpha: 0.14),
                    ),
                    child: Icon(Icons.power_settings_new_rounded,
                        size: 32, color: accent),
                  ),
                  const SizedBox(width: 16),
                  Expanded(child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(label('متصل نیست', 'Disconnected'),
                          style: const TextStyle(
                              fontSize: 23, fontWeight: FontWeight.w800)),
                      const SizedBox(height: 3),
                      Text(label('موتور VPN ویندوز آماده نیست',
                              'Windows VPN engine unavailable'),
                          style: TextStyle(color: textColor.withValues(alpha: 0.65))),
                    ],
                  )),
                ],
              ),
              const SizedBox(height: 20),
              FilledButton.icon(
                key: const Key('devConnectButton'),
                onPressed: null,
                icon: const Icon(Icons.power_settings_new),
                label: Text(label('اتصال', 'Connect')),
              ),
            ],
          ),
        );

        Widget protocolList() => Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            color: surface,
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: textColor.withValues(alpha: 0.09)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Expanded(child: Text(label('پروتکل‌ها', 'Protocols'),
                    style: const TextStyle(
                      fontSize: 19, fontWeight: FontWeight.w700,
                    ))),
                Text('${protocols.length} / 16',
                    style: TextStyle(color: textColor.withValues(alpha: 0.62))),
              ]),
              const SizedBox(height: 14),
              TextField(
                key: const Key('devProtocolSearch'),
                onChanged: (value) => setState(() => _search = value),
                decoration: InputDecoration(
                  hintText: label('جستجوی پروتکل', 'Search protocols'),
                  prefixIcon: const Icon(Icons.search_rounded),
                  filled: true,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(15),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(children: [
                  for (final option in options.entries) ...[
                    ChoiceChip(
                      key: Key('devFilter_${option.key}'),
                      label: Text(option.value),
                      selected: _section == option.key,
                      onSelected: (_) => setState(() => _section = option.key),
                    ),
                    const SizedBox(width: 8),
                  ],
                ]),
              ),
              const SizedBox(height: 10),
              for (final item in protocols)
                ListTile(
                  key: Key('devProtocol_${item.protocol.code}'),
                  contentPadding: EdgeInsets.zero,
                  leading: Container(
                    height: 38,
                    width: 38,
                    decoration: BoxDecoration(
                      color: accent.withValues(alpha: 0.10),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(Icons.hub_outlined, size: 19, color: accent),
                  ),
                  title: Text(item.protocol.name),
                  subtitle: Text(label('موتور آماده نیست', 'Engine unavailable'),
                      style: TextStyle(color: textColor.withValues(alpha: 0.58))),
                  trailing: const Icon(Icons.lock_outline_rounded, size: 18),
                ),
            ],
          ),
        );

        return Scaffold(
          appBar: AppBar(
            title: Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.bolt_rounded, color: accent),
              const SizedBox(width: 8),
              const Text('TwinConnect',
                  style: TextStyle(fontWeight: FontWeight.w800)),
            ]),
            actions: [
              IconButton(
                key: const Key('devThemeToggle'),
                tooltip: label('تغییر ظاهر', 'Toggle theme'),
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
                tooltip: label('تنظیمات', 'Settings'),
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => VpnSettingsScreen(
                    tenant: '', account: '', brand: brand,
                  ),
                )),
                icon: const Icon(Icons.tune_rounded),
              ),
              const SizedBox(width: 12),
            ],
          ),
          body: BrandBackground(
            brand: brand,
            child: SafeArea(
              child: ListView(
                padding: const EdgeInsets.all(22),
                children: [
                  Center(child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 1120),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(label('داشبورد', 'Dashboard'),
                            style: const TextStyle(
                              fontSize: 27, fontWeight: FontWeight.w800,
                            )),
                        const SizedBox(height: 8),
                        Text(label('نمایش آزمایشی · بدون اطلاعات واقعی',
                                'UI preview · Sample data only'),
                            key: const Key('devSampleNotice'),
                            style: TextStyle(
                              color: textColor.withValues(alpha: 0.60),
                            )),
                        const SizedBox(height: 22),
                        if (isWide)
                          Row(crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Expanded(flex: 4, child: statusPanel()),
                              const SizedBox(width: 18),
                              Expanded(flex: 5, child: protocolList()),
                            ],
                          )
                        else ...[
                          statusPanel(),
                          const SizedBox(height: 18),
                          protocolList(),
                        ],
                        const SizedBox(height: 16),
                        Text(label(
                          'اتصال واقعی پس از اتصال موتور بومی و احراز هویت اشتراک فعال می‌شود.',
                          'Real connections require the native engine and an authorized subscription.',
                        ), style: TextStyle(
                          fontSize: 12,
                          color: textColor.withValues(alpha: 0.55),
                        )),
                      ],
                    ),
                  )),
                ],
              ),
            ),
          ),
        );
      }),
    );
  }
}
