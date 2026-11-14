import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'account_snapshot.dart';
import 'brand_theme.dart';
import 'plan_classification.dart';
import 'protocols.dart';
import 'server_inventory.dart';
import 'tenant_models.dart';

/// Reusable iPhone shell shared by the authenticated app and the simulator
/// showcase. Preview data is supplied only by ios_preview_main.dart.
/// This widget never claims to establish a VPN tunnel.
class TwinConnectIphoneShell extends StatefulWidget {
  const TwinConnectIphoneShell({
    required this.brand,
    required this.username,
    this.inventory,
    this.catalog,
    this.account,
    this.plan,
    this.previewMode = false,
    this.autoTour = false,
    this.onRefresh,
    this.onLogout,
    super.key,
  });

  final BrandPreview brand;
  final String username;
  final AppServerInventory? inventory;
  final PanelProtocolCatalog? catalog;
  final AppAccountSnapshot? account;
  final AppPlanClassification? plan;
  final bool previewMode;
  final bool autoTour;
  final VoidCallback? onRefresh;
  final VoidCallback? onLogout;

  @override
  State<TwinConnectIphoneShell> createState() => _TwinConnectIphoneShellState();
}

class _TwinConnectIphoneShellState extends State<TwinConnectIphoneShell> {
  static const _sky = Color(0xFF68D6E3);
  static const _mint = Color(0xFF71F4D1);
  static const _muted = Color(0xFFA6C4D1);
  static const _white = Color(0xFFF3FCFF);
  int _page = 0;
  String _protocol = 'all';
  String? _selectedNode;
  final Set<String> _expandedCountries = {};
  Timer? _tour;

  bool get _rtl => true;

  @override
  void initState() {
    super.initState();
    if (widget.previewMode && widget.autoTour) {
      _tour = Timer.periodic(const Duration(seconds: 12), (_) {
        if (!mounted) return;
        setState(() => _page = (_page + 1) % 4);
      });
    }
  }

  @override
  void dispose() {
    _tour?.cancel();
    super.dispose();
  }

  void _go(int page) {
    _tour?.cancel();
    setState(() => _page = page);
  }

  String _country(String code) => switch (code.toUpperCase()) {
    'TR' => 'ترکیه',
    'DE' => 'آلمان',
    'US' => 'آمریکا',
    'GB' || 'UK' => 'انگلیس',
    'FI' => 'فنلاند',
    'FR' => 'فرانسه',
    'IR' => 'ایران',
    'NL' => 'هلند',
    _ => code,
  };

  String _flag(String code) => switch (code.toUpperCase()) {
    'TR' => '🇹🇷', 'DE' => '🇩🇪', 'US' => '🇺🇸', 'GB' || 'UK' => '🇬🇧',
    'FI' => '🇫🇮', 'FR' => '🇫🇷', 'IR' => '🇮🇷', 'NL' => '🇳🇱', _ => '🌐',
  };

  Widget _card({required Widget child, EdgeInsets? padding}) => Container(
    width: double.infinity,
    padding: padding ?? const EdgeInsets.all(18),
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(24),
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0x663D7486), Color(0x3A173845)],
      ),
      border: Border.all(color: const Color(0x5569C6D8)),
      boxShadow: const [
        BoxShadow(color: Color(0x26000C16), blurRadius: 25, offset: Offset(0, 12)),
      ],
    ),
    child: child,
  );

  Text _label(String value, {double size = 13, Color color = _white,
      FontWeight weight = FontWeight.w500, TextAlign? align}) =>
    Text(value, textAlign: align,
      style: TextStyle(fontSize: size, color: color, fontWeight: weight,
          height: 1.4));

  Widget _section(String title, {String? subtitle}) => Padding(
    padding: const EdgeInsets.only(bottom: 14, top: 8),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _label(title, size: 21, weight: FontWeight.w800),
      if (subtitle != null) _label(subtitle, size: 11, color: _muted),
    ]),
  );

  Widget _pill(String label, {IconData? icon, bool active = false}) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(20),
      color: active ? _sky.withValues(alpha: .19) : Colors.white.withValues(alpha: .07),
      border: Border.all(color: active ? _sky.withValues(alpha: .65)
          : Colors.white.withValues(alpha: .13))),
    child: Row(mainAxisSize: MainAxisSize.min, children: [
      if (icon != null) ...[Icon(icon, color: active ? _sky : _muted, size: 13),
        const SizedBox(width: 5)],
      _label(label, size: 10, color: active ? _sky : _muted),
    ]),
  );

  Widget _metric(String value, String text, IconData icon) => Expanded(
    child: Column(children: [
      Icon(icon, size: 19, color: _sky),
      const SizedBox(height: 8),
      _label(value, size: 15, weight: FontWeight.w800),
      _label(text, size: 10, color: _muted),
    ]),
  );

  String _bytes(int value) => value <= 0 ? '۰ گیگ'
      : '${(value / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';

  Widget _overview() {
    final account = widget.account;
    final used = account?.trafficUsedBytes ?? 0;
    final limit = account?.trafficLimitBytes ?? 0;
    final fraction = limit <= 0 ? 0.0 : (used / limit).clamp(0.0, 1.0);
    final expiry = account?.expiresAt;
    final days = expiry == null ? '—'
        : math.max(0, expiry.difference(DateTime.now()).inDays).toString();
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _section('اتصال سریع', subtitle: 'مدیریت امن و یکپارچه VPN'),
      _card(child: Column(children: [
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          _pill(widget.previewMode ? 'پیش‌نمایش رابط' : 'حساب متصل به پنل',
              icon: Icons.verified_user_outlined, active: true),
          _pill('آفلاین', icon: Icons.circle_outlined),
        ]),
        const SizedBox(height: 30),
        Container(
          width: 150, height: 150,
          decoration: BoxDecoration(shape: BoxShape.circle,
            boxShadow: [BoxShadow(color: _sky.withValues(alpha: .21),
              blurRadius: 45, spreadRadius: 1)],
            gradient: const RadialGradient(colors: [
              Color(0xFF336C7D), Color(0xFF163645), Color(0xFF0D2637)]),
            border: Border.all(color: _sky.withValues(alpha: .62), width: 2)),
          child: const Icon(Icons.power_settings_new_rounded,
              color: _white, size: 69),
        ),
        const SizedBox(height: 24),
        _label('اتصال برقرار نیست', size: 21, weight: FontWeight.w800),
        const SizedBox(height: 5),
        _label('موتور VPN آیفون هنوز فعال نشده است',
            size: 11, color: _muted, align: TextAlign.center),
        const SizedBox(height: 20),
        SizedBox(width: double.infinity, child: FilledButton.icon(
          key: const Key('iphoneConnectDisabled'),
          onPressed: null,
          style: FilledButton.styleFrom(
            minimumSize: const Size.fromHeight(53),
            disabledBackgroundColor: const Color(0xFF306072),
            disabledForegroundColor: const Color(0xFFB5DDE8)),
          icon: const Icon(Icons.lock_outline),
          label: const Text('اتصال پس از تکمیل موتور iOS'),
        )),
      ])),
      const SizedBox(height: 18),
      _card(child: Row(children: [
        _metric('—', 'پینگ', Icons.bolt_rounded),
        _metric('۰ KB', 'دانلود', Icons.south_rounded),
        _metric('۰ KB', 'آپلود', Icons.north_rounded),
      ])),
      const SizedBox(height: 18),
      _card(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          _label('اطلاعات اشتراک', size: 15, weight: FontWeight.w800),
          const Icon(Icons.data_usage_rounded, color: _sky, size: 21),
        ]),
        const SizedBox(height: 13),
        LinearProgressIndicator(value: fraction, minHeight: 7,
          backgroundColor: const Color(0xFF163344), color: _mint,
          borderRadius: BorderRadius.circular(8)),
        const SizedBox(height: 13),
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          _label('مصرف: ${_bytes(used)}', color: _muted, size: 11),
          _label('کل: ${limit == 0 ? 'نامحدود' : _bytes(limit)}',
              size: 11),
        ]),
        const Divider(color: Color(0x335CC7D6), height: 25),
        Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          _label('اعتبار باقی‌مانده', color: _muted, size: 11),
          _label(expiry == null ? 'نامشخص' : '$days روز',
              color: _mint, weight: FontWeight.w700),
        ]),
      ])),
    ]);
  }

  Widget _locations() {
    final servers = widget.inventory?.servers ?? const <AppServer>[];
    final groups = <String, List<AppServer>>{};
    for (final node in servers) {
      groups.putIfAbsent(node.countryCode, () => []).add(node);
    }
    final protocols = widget.catalog?.entries
            .where((e) => e.selected && e.configRecordPresent)
            .map((e) => e.protocol.code).toList() ?? const <String>[];
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _section('مکان‌ها', subtitle: '${servers.length} سرور در فهرست اشتراک'),
      _card(padding: const EdgeInsets.all(14), child: Row(children: [
        const Icon(Icons.search_rounded, size: 20, color: _muted),
        const SizedBox(width: 10),
        Expanded(child: _label('سرورهای موجود در اشتراک',
            color: _muted, size: 12)),
        IconButton(onPressed: widget.previewMode ? null : widget.onRefresh,
          icon: const Icon(Icons.refresh_rounded, color: _sky)),
      ])),
      const SizedBox(height: 13),
      SingleChildScrollView(scrollDirection: Axis.horizontal, child: Row(children: [
        for (final code in <String>['all', ...protocols]) ...[
          GestureDetector(onTap: () => setState(() => _protocol = code),
            child: _pill(code == 'all' ? 'همه پروتکل‌ها'
              : (VpnProtocols.byCode(code)?.name ?? code),
              active: _protocol == code)),
          const SizedBox(width: 8),
        ],
      ])),
      const SizedBox(height: 17),
      if (groups.isEmpty)
        _card(child: _label('سروری برای نمایش وجود ندارد.',
            color: _muted, align: TextAlign.center)),
      for (final entry in groups.entries) ...[
        GestureDetector(onTap: () => setState(() {
          if (!_expandedCountries.add(entry.key)) {
            _expandedCountries.remove(entry.key);
          }
        }), child: _card(padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 14),
          child: Row(children: [
            Text(_flag(entry.key), style: const TextStyle(fontSize: 29)),
            const SizedBox(width: 11),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _label(_country(entry.key), weight: FontWeight.w800),
                _label('${entry.value.length} سرور', color: _muted, size: 10),
              ])),
            Icon(_expandedCountries.contains(entry.key)
                ? Icons.keyboard_arrow_up_rounded
                : Icons.keyboard_arrow_down_rounded, color: _sky),
          ]))),
        if (_expandedCountries.contains(entry.key))
          for (final node in entry.value)
            Padding(padding: const EdgeInsets.only(top: 7, right: 10, left: 10),
              child: GestureDetector(onTap: () {
                setState(() => _selectedNode = node.id);
                ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                  content: Text('سرور انتخاب شد؛ اتصال VPN در این نسخه فعال نیست.')));
              }, child: _card(padding: const EdgeInsets.all(13), child: Row(children: [
                Icon(Icons.dns_rounded,
                    color: node.nodeOnline ? _mint : _muted, size: 20),
                const SizedBox(width: 11),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _label(node.name, size: 12),
                    _label(node.nodeOnline ? 'در دسترس پنل' : 'نود آفلاین',
                        color: _muted, size: 10),
                  ])),
                _label(node.latencyMs == null ? '—'
                  : '${node.latencyMs} ms', color: _sky, size: 11),
                if (_selectedNode == node.id)
                  const Icon(Icons.check_circle, color: _mint, size: 17),
              ])))),
        const SizedBox(height: 9),
      ],
    ]);
  }

  Widget _settings() {
    Widget setting(String title, String detail, IconData icon,
        {bool enabled = false}) => _card(padding: const EdgeInsets.all(15),
      child: Row(children: [
        Container(width: 40, height: 40,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            color: _sky.withValues(alpha: .13)),
          child: Icon(icon, color: _sky, size: 22)),
        const SizedBox(width: 12),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _label(title, weight: FontWeight.w700, size: 12),
            _label(detail, color: _muted, size: 10),
          ])),
        Icon(enabled ? Icons.check_circle_rounded
          : Icons.lock_outline_rounded,
          color: enabled ? _mint : _muted, size: 19),
      ]));
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _section('تنظیمات', subtitle: 'تنظیمات شبکه و امنیت آیفون'),
      setting('حالت VPN', 'نیازمند Network Extension', Icons.shield_outlined),
      const SizedBox(height: 10),
      setting('Kill Switch', 'پس از پیاده‌سازی تونل بومی', Icons.security_rounded),
      const SizedBox(height: 10),
      setting('تفکیک برنامه‌ها', 'محدود به قابلیت‌های iOS', Icons.apps_rounded),
      const SizedBox(height: 10),
      setting('DNS اختصاصی', 'پس از اتصال موتور VPN', Icons.dns_rounded),
      const SizedBox(height: 10),
      setting('رابط فارسی', 'چینش راست‌به‌چپ', Icons.translate_rounded,
        enabled: true),
      const SizedBox(height: 18),
      _card(child: _label('تنظیمات غیرفعال، صرفاً پیش‌نمایش هستند؛ هیچ‌یک '
          'در شبیه‌ساز مسیر اینترنت دستگاه را تغییر نمی‌دهند.',
          color: _muted, size: 11)),
    ]);
  }

  Widget _account() {
    final account = widget.account;
    final plan = widget.plan;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _section('حساب کاربری', subtitle: widget.brand.brandName),
      _card(child: Column(children: [
        Container(width: 68, height: 68,
          decoration: BoxDecoration(shape: BoxShape.circle,
            color: _sky.withValues(alpha: .17),
            border: Border.all(color: _sky.withValues(alpha: .5))),
          child: const Icon(Icons.person_outline_rounded,
              color: _white, size: 34)),
        const SizedBox(height: 13),
        _label(widget.username, size: 15, weight: FontWeight.w800,
            align: TextAlign.center),
        const SizedBox(height: 8),
        _pill(widget.previewMode ? 'اطلاعات نمونه' :
          (account?.status ?? 'وضعیت نامشخص'), active: true),
      ])),
      const SizedBox(height: 14),
      _card(child: Column(children: [
        _row('نوع اشتراک', plan?.subscriptionType ?? 'نامشخص'),
        const Divider(color: Color(0x335CC7D6), height: 25),
        _row('دستگاه‌های مجاز', plan?.deviceLimit.toString() ?? '—'),
        const Divider(color: Color(0x335CC7D6), height: 25),
        _row('حجم کل', account == null ? 'نامشخص'
            : (account.trafficLimitBytes == 0 ? 'نامحدود'
                : _bytes(account.trafficLimitBytes))),
        const Divider(color: Color(0x335CC7D6), height: 25),
        _row('میزان مصرف', account == null ? 'نامشخص'
            : _bytes(account.trafficUsedBytes)),
      ])),
      if (widget.previewMode) ...[
        const SizedBox(height: 15),
        _card(child: _label('این صفحه فقط شامل داده‌های ساختگی برای بررسی طراحی '
            'است و هیچ حساب واقعی یا لایسنسی را تأیید نمی‌کند.',
            size: 11, color: _muted)),
      ],
      if (widget.onLogout != null) ...[
        const SizedBox(height: 15),
        OutlinedButton.icon(onPressed: widget.onLogout,
          icon: const Icon(Icons.logout_rounded), label: const Text('خروج امن')),
      ],
    ]);
  }

  Widget _row(String name, String value) => Row(children: [
    Expanded(child: _label(name, color: _muted, size: 12)),
    Flexible(child: _label(value, weight: FontWeight.w700, size: 12)),
  ]);

  @override
  Widget build(BuildContext context) {
    final brandColor = BrandTheme.accent(widget.brand, Brightness.dark);
    return Directionality(textDirection: _rtl ? TextDirection.rtl : TextDirection.ltr,
      child: Scaffold(
        backgroundColor: const Color(0xFF091923),
        body: Stack(children: [
          Positioned.fill(child: DecoratedBox(decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topRight, end: Alignment.bottomLeft,
              colors: [Color.lerp(brandColor, const Color(0xFF102F40), .53)!,
                const Color(0xFF132D39), const Color(0xFF081720)])))),
          Positioned(top: -80, right: -70,
            child: Container(width: 280, height: 280,
              decoration: BoxDecoration(shape: BoxShape.circle,
                color: _sky.withValues(alpha: .055)))),
          SafeArea(child: Column(children: [
            Padding(padding: const EdgeInsets.fromLTRB(20, 14, 20, 16),
              child: Row(children: [
                Container(width: 42, height: 42,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(14),
                    gradient: const LinearGradient(colors: [
                      Color(0xFF286277), Color(0xFF13516A)])),
                  child: const Icon(Icons.shield_moon_rounded,
                      color: _mint, size: 25)),
                const SizedBox(width: 10),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _label('TwinConnect', size: 17, weight: FontWeight.w800),
                    _label(widget.brand.brandName, size: 10, color: _muted),
                  ])),
                if (widget.previewMode) _pill('DEMO', icon: Icons.visibility_outlined),
                const SizedBox(width: 6),
                const Icon(Icons.notifications_none_rounded, color: _sky),
              ])),
            Expanded(child: ListView(
              key: Key('iosPage$_page'),
              padding: const EdgeInsets.fromLTRB(18, 0, 18, 28),
              children: [
                if (_page == 0) _overview(),
                if (_page == 1) _locations(),
                if (_page == 2) _settings(),
                if (_page == 3) _account(),
              ])),
          ])),
        ]),
        bottomNavigationBar: SafeArea(top: false,
          child: Container(
            decoration: const BoxDecoration(
              color: Color(0xFF112B38),
              border: Border(top: BorderSide(color: Color(0x3858A8BC)))),
            child: NavigationBar(
              key: const Key('iosShowcaseNavigation'),
              height: 66,
              selectedIndex: _page,
              backgroundColor: Colors.transparent,
              indicatorColor: _sky.withValues(alpha: .23),
              labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
              onDestinationSelected: _go,
              destinations: const [
                NavigationDestination(icon: Icon(Icons.bolt_rounded),
                    label: 'اتصال'),
                NavigationDestination(icon: Icon(Icons.public_rounded),
                    label: 'مکان‌ها'),
                NavigationDestination(icon: Icon(Icons.tune_rounded),
                    label: 'تنظیمات'),
                NavigationDestination(icon: Icon(Icons.person_outline_rounded),
                    label: 'حساب'),
              ],
            ),
          )),
      ));
  }
}
