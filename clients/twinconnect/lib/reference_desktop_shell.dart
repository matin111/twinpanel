import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'tenant_models.dart';
import 'reference_visuals.dart';

/// Reference-aligned Windows shell. Never synthesizes connection telemetry.
/// Connection controls stay disabled until a real tunnel controller is supplied.
class ReferenceDesktopShell extends StatefulWidget {
  const ReferenceDesktopShell({
    super.key,
    required this.brand,
    required this.username,
    required this.locations,
    required this.onLogout,
    required this.onSettings,
    this.connected = false,
    this.onToggleConnection,
    this.publicIp,
    this.pingMs,
    this.downloadBytesPerSecond,
    this.uploadBytesPerSecond,
    this.receivedBytes,
    this.sentBytes,
    this.usedBytes,
    this.totalBytes,
    this.country,
    this.city,
    this.protocol,
    this.connectedFor,
    this.exitIpVerified = false,
  });

  final BrandPreview brand;
  final String username;
  final Widget locations;
  final VoidCallback onLogout;
  final VoidCallback onSettings;
  final bool connected;
  final VoidCallback? onToggleConnection;
  final String? publicIp;
  final int? pingMs;
  final double? downloadBytesPerSecond, uploadBytesPerSecond;
  final int? receivedBytes, sentBytes, usedBytes, totalBytes;
  final String? country, city, protocol;
  final Duration? connectedFor;
  final bool exitIpVerified;

  @override
  State<ReferenceDesktopShell> createState() => _ReferenceDesktopShellState();
}

class _ReferenceDesktopShellState extends State<ReferenceDesktopShell> {
  int tab = 0;

  static const navy = Color(0xFF080D2D);
  static const violet = Color(0xFF9F43FF);
  static const cyan = Color(0xFF00E5F2);
  static const green = Color(0xFF00E99D);
  static const muted = Color(0xFFADB4D8);

  String bytes(int? value) {
    if (value == null) return '—';
    const suffix = ['B', 'KB', 'MB', 'GB', 'TB'];
    var number = value.toDouble();
    var index = 0;
    while (number >= 1024 && index < suffix.length - 1) {
      number /= 1024;
      index++;
    }
    return '${number.toStringAsFixed(index == 0 ? 0 : 1)} ${suffix[index]}';
  }

  String speed(double? value) =>
      value == null ? '—' : '${bytes(value.round())}/s';

  String duration(Duration? value) {
    if (value == null) return '—';
    String two(int n) => n.toString().padLeft(2, '0');
    return '${two(value.inHours)}:${two(value.inMinutes.remainder(60))}:${two(value.inSeconds.remainder(60))}';
  }

  Future<void> openLink(String? url) async {
    final uri = Uri.tryParse(url ?? '');
    if (uri == null || !['https', 'http', 'tg'].contains(uri.scheme)) return;
    await Clipboard.setData(ClipboardData(text: uri.toString()));
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Link copied to clipboard')),
      );
    }
  }

  Widget glass(Widget child, {EdgeInsets padding = const EdgeInsets.all(20),
      double radius = 28, Color? tint}) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(radius),
        gradient: LinearGradient(
          begin: Alignment.topLeft, end: Alignment.bottomRight,
          colors: [tint ?? const Color(0xC11B2059), const Color(0xE617124E)],
        ),
        border: Border.all(color: violet.withOpacity(.65), width: 1),
        boxShadow: [BoxShadow(color: violet.withOpacity(.12),
            blurRadius: 23, spreadRadius: -4)],
      ),
      padding: padding,
      child: child,
    );
  }

  Widget title(String text, {double size = 21, Color? color}) => Text(text,
      style: TextStyle(fontSize: size, fontWeight: FontWeight.w700,
          color: color ?? Colors.white));

  Widget nav(IconData icon, String label, int value) {
    final active = tab == value;
    return Padding(
      padding: const EdgeInsets.only(bottom: 11),
      child: InkWell(
        key: Key('referenceNav$value'),
        onTap: () => setState(() => tab = value),
        borderRadius: BorderRadius.circular(16),
        child: Container(
          height: 63,
          padding: const EdgeInsets.symmetric(horizontal: 22),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: active ? const Color(0xFFDB8CFF) : const Color(0x665D5FC2)),
            gradient: LinearGradient(colors: active
                ? [const Color(0xFF7928D7), const Color(0xFFB348FF)]
                : [const Color(0xB9323275), const Color(0xAA27235A)]),
          ),
          child: Row(children: [Icon(icon, size: 26, color: Colors.white),
            const SizedBox(width: 20), Expanded(child: title(label, size: 17))]),
        ),
      ),
    );
  }

  Widget metric(IconData icon, String name, String value, Color accent) =>
    glass(Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [Icon(icon, color: accent, size: 25),
        const SizedBox(width: 14), Text(name, style: const TextStyle(color: Colors.white))]),
      const Spacer(), title(value, size: 26, color: value == '—' ? muted : accent),
      const SizedBox(height: 7),
    ]), radius: 21, padding: const EdgeInsets.all(18));

  Widget sidebar() => Container(
    width: 300,
    padding: const EdgeInsets.fromLTRB(18, 55, 18, 24),
    decoration: const BoxDecoration(
      gradient: LinearGradient(begin: Alignment.topCenter,
          end: Alignment.bottomCenter, colors: [Color(0xFF080C29), Color(0xFF21145A)]),
      border: Border(left: BorderSide(color: Color(0x664A3B9D))),
    ),
    child: LayoutBuilder(builder: (context, bounds) => SingleChildScrollView(
      child: SizedBox(height: math.max(850, bounds.maxHeight),
        child: Column(children: [
      SizedBox(height: 68, width: 85,
        child: widget.brand.logoUrl == null
          ? const Icon(Icons.change_history_rounded, size: 68, color: violet)
          : Image.network(widget.brand.logoUrl!, fit: BoxFit.contain,
              errorBuilder: (context, error, stackTrace) => const Icon(Icons.change_history_rounded,
                size: 68, color: violet))),
      const SizedBox(height: 8),
      title(widget.brand.brandName, size: 25),
      const SizedBox(height: 42),
      nav(Icons.bolt, 'Quick connect', 0),
      nav(Icons.location_on_outlined, 'Locations', 1),
      nav(Icons.tune, 'Settings', 2),
      nav(Icons.person_outline, 'Account', 3),
      const SizedBox(height: 16),
      glass(Row(mainAxisAlignment: MainAxisAlignment.spaceAround, children: [
        linkIcon(Icons.headset_mic_outlined, 'Support', widget.brand.telegramUrl),
        linkIcon(Icons.autorenew, 'Renew', widget.brand.renewalUrl),
        linkIcon(Icons.language, 'Website', widget.brand.websiteUrl),
      ]), padding: const EdgeInsets.symmetric(vertical: 15, horizontal: 4), radius: 20),
      const Spacer(),
      glass(Row(children: [const Icon(Icons.circle, color: green, size: 12),
        const SizedBox(width: 10), Expanded(child: Column(
          crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(widget.username, maxLines: 1, overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
            const Text('Signed in', style: TextStyle(color: muted, fontSize: 12)),
          ]))]), padding: const EdgeInsets.all(16), radius: 17),
      const SizedBox(height: 18),
      const Tooltip(message: 'Dark theme (light theme not yet available)',
        child: Icon(Icons.dark_mode, color: violet, size: 30)),
      const SizedBox(height: 14),
      IconButton(key: const Key('referenceSettingsButton'), onPressed: widget.onSettings,
          icon: const Icon(Icons.settings_outlined, color: Colors.white, size: 29)),
    ])))),
  );

  Widget linkIcon(IconData icon, String text, String? url) => InkWell(
    onTap: url == null ? null : () => openLink(url),
    child: Column(children: [Icon(icon, color: const Color(0xFFC06CFF), size: 29),
      const SizedBox(height: 8),
      Text(text, style: TextStyle(color: url == null ? muted : Colors.white,
          fontWeight: FontWeight.w600, fontSize: 12))]),
  );

  Widget connection() => glass(Column(children: [
    Container(
      padding: const EdgeInsets.symmetric(horizontal: 23, vertical: 11),
      decoration: BoxDecoration(border: Border.all(color: widget.connected ? green : muted),
        borderRadius: BorderRadius.circular(30), color: const Color(0x66112646)),
      child: Text(widget.connected ? '✓  You are online' : '○  Not connected',
        style: TextStyle(color: widget.connected ? green : muted,
            fontSize: 16, fontWeight: FontWeight.bold)),
    ),
    const Spacer(),
    Tooltip(
      message: widget.onToggleConnection == null
          ? 'VPN tunnel controller not available in this build'
          : widget.connected ? 'Disconnect' : 'Connect',
      child: NeonRing(active: widget.connected, child: InkWell(
        key: const Key('referenceConnectAction'),
        onTap: widget.onToggleConnection,
        customBorder: const CircleBorder(),
        child: Container(
          width: 238, height: 238,
          decoration: BoxDecoration(shape: BoxShape.circle,
            gradient: const RadialGradient(colors: [
              Color(0xFF142456), Color(0xFF18236D), Color(0xFF651EC3)]),
            border: Border.all(color: widget.connected ? cyan : violet, width: 5),
            boxShadow: [BoxShadow(color: (widget.connected ? cyan : violet)
                .withOpacity(.55), blurRadius: 38, spreadRadius: 6)]),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(Icons.power_settings_new, size: 67,
                color: widget.onToggleConnection == null ? muted : Colors.white),
            const SizedBox(height: 19),
            title(widget.connected ? 'Secure connection' : 'Connection', size: 17),
            title(widget.connected ? 'active' : 'inactive', size: 17),
          ]),
        ),
      )),
    ),
    const Spacer(),
    Row(mainAxisAlignment: MainAxisAlignment.center, children: [
      const Icon(Icons.access_time, color: cyan), const SizedBox(width: 12),
      const Text('Connected for  '), title(duration(widget.connectedFor), color: cyan, size: 18),
    ]),
    const SizedBox(height: 15),
    Row(mainAxisAlignment: MainAxisAlignment.center, children: [
      Icon(widget.exitIpVerified ? Icons.verified_user : Icons.shield_outlined,
          color: widget.exitIpVerified ? cyan : muted),
      const SizedBox(width: 9),
      Text(widget.exitIpVerified ? 'Tunnel exit IP verified' : 'Exit IP not verified',
          style: const TextStyle(color: muted)),
    ]),
    const SizedBox(height: 16),
    const Text('Refresh tunnel status', style: TextStyle(color: violet)),
    const Spacer(),
    const AmbientWave(height: 52),
    Container(height: 53, width: 355, alignment: Alignment.center,
      decoration: BoxDecoration(borderRadius: BorderRadius.circular(24),
        color: const Color(0x663B2D8C), border: Border.all(color: violet)),
      child: Row(mainAxisAlignment: MainAxisAlignment.center,
        children: List.generate(20, (i) => Container(
          width: 4, height: 8 + (math.sin(i * 1.4).abs() * 24),
          margin: const EdgeInsets.symmetric(horizontal: 4),
          decoration: BoxDecoration(color: i.isEven ? cyan : violet,
            borderRadius: BorderRadius.circular(4))))),
    ),
    const SizedBox(height: 21),
    glass(Row(mainAxisAlignment: MainAxisAlignment.spaceAround, children: [
      mini('Location', widget.country ?? '—'),
      mini('Public IP', widget.publicIp ?? '—'),
      mini('Protocol', widget.protocol ?? '—'),
    ]), radius: 18, padding: const EdgeInsets.all(14)),
  ]), padding: const EdgeInsets.fromLTRB(17, 29, 17, 20));

  Widget mini(String label, String value) => Flexible(child: Column(children: [
    Text(label, style: const TextStyle(color: muted, fontSize: 12)),
    const SizedBox(height: 9),
    Text(value, overflow: TextOverflow.ellipsis, maxLines: 1,
      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
  ]));

  Widget network() => glass(Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
    Row(children: [const Icon(Icons.bar_chart, color: violet, size: 32),
      const SizedBox(width: 13), Expanded(child: title('Network status', size: 23)),
      Text(widget.connected ? '◉  Tunnel active' : '○  Tunnel inactive',
          style: TextStyle(color: widget.connected ? cyan : muted))]),
    const SizedBox(height: 23),
    Expanded(child: GridView.count(
      crossAxisCount: 2, crossAxisSpacing: 17, mainAxisSpacing: 17,
      childAspectRatio: 2.2, physics: const NeverScrollableScrollPhysics(),
      children: [
        metric(Icons.timer_outlined, 'Server ping',
          widget.pingMs == null ? '—' : '${widget.pingMs} ms', green),
        metric(Icons.language, 'Public IP', widget.publicIp ?? '—', Colors.white),
        metric(Icons.arrow_downward, 'Received', bytes(widget.receivedBytes), cyan),
        metric(Icons.arrow_upward, 'Sent', bytes(widget.sentBytes), const Color(0xFFEA48FF)),
      ],
    )),
    const SizedBox(height: 18),
    glass(Row(children: [const Icon(Icons.location_on, color: violet),
      const SizedBox(width: 10),
      Expanded(child: Text([widget.country, widget.city].whereType<String>().join(' – ').isEmpty
          ? 'No server selected'
          : [widget.country, widget.city].whereType<String>().join(' – '),
          style: const TextStyle(fontWeight: FontWeight.w600))),
      TextButton(onPressed: () => setState(() => tab = 1),
          child: const Text('Locations'))]),
      padding: const EdgeInsets.all(14), radius: 18),
    const SizedBox(height: 20),
    glass(Row(children: [
      Expanded(child: gauge(Icons.arrow_downward, 'Download',
          speed(widget.downloadBytesPerSecond), cyan)),
      const SizedBox(width: 12),
      Expanded(child: gauge(Icons.arrow_upward, 'Upload',
          speed(widget.uploadBytesPerSecond), violet)),
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Data usage', style: TextStyle(color: muted)),
        const SizedBox(height: 12),
        title('${bytes(widget.usedBytes)} / ${bytes(widget.totalBytes)}', size: 16),
        const SizedBox(height: 17),
        LinearProgressIndicator(
          value: widget.usedBytes != null && widget.totalBytes != null &&
                  widget.totalBytes! > 0
              ? (widget.usedBytes! / widget.totalBytes!).clamp(0.0, 1.0)
              : 0,
          backgroundColor: const Color(0xFF35346F), color: violet,
          minHeight: 9),
      ])),
    ]), padding: const EdgeInsets.all(22), radius: 20),
  ]), padding: const EdgeInsets.all(22));

  Widget gauge(IconData icon, String name, String value, Color color) =>
    RingGauge(color: color, icon: icon, label: name, value: value);

  Widget quickConnect() => Column(children: [
    Row(children: [const Icon(Icons.bolt, color: violet, size: 57),
      const SizedBox(width: 14),
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        title('Quick Connect', size: 31),
        const Text('Fast  •  Secure  •  Stable', style: TextStyle(color: muted)),
      ]),
      const Spacer(),
      glass(Text(widget.brand.accountStatus, style: const TextStyle(color: green)),
          padding: const EdgeInsets.symmetric(horizontal: 17, vertical: 11), radius: 24),
    ]),
    const SizedBox(height: 23),
    Expanded(child: Row(children: [
      Expanded(flex: 9, child: connection()),
      const SizedBox(width: 16),
      Expanded(flex: 10, child: network()),
    ])),
    const SizedBox(height: 23),
    glass(Row(children: [const Icon(Icons.bolt, color: violet, size: 42),
      const SizedBox(width: 15),
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        title('Select fastest server', size: 20),
        const Text('Based on measured server latency', style: TextStyle(color: muted)),
      ])),
      const Tooltip(message: 'Waiting for the native fastest-server selector',
        child: Switch(value: false, onChanged: null)),
    ]), padding: const EdgeInsets.all(19)),
  ]);

  @override
  Widget build(BuildContext context) {
    // Desktop visual reference uses 1536x1024. Scroll when available height is smaller.
    return Theme(data: ThemeData.dark(useMaterial3: true), child: Scaffold(
      key: const Key('referenceDesktopShell'),
      backgroundColor: navy,
      body: DecoratedBox(
        decoration: const BoxDecoration(gradient: LinearGradient(
          begin: Alignment.topLeft, end: Alignment.bottomRight,
          colors: [Color(0xFF080D2D), Color(0xFF211252), Color(0xFF080D2D)])),
        child: Row(children: [
          Expanded(child: Padding(
            padding: const EdgeInsets.fromLTRB(29, 39, 19, 32),
            child: LayoutBuilder(builder: (context, limits) {
              final page = switch (tab) {
                1 => SingleChildScrollView(child: widget.locations),
                2 => Center(child: FilledButton.icon(onPressed: widget.onSettings,
                    icon: const Icon(Icons.settings), label: const Text('Open Settings'))),
                3 => Center(child: glass(Column(mainAxisSize: MainAxisSize.min, children: [
                  title(widget.username), const SizedBox(height: 16),
                  Text(widget.brand.brandName),
                  const SizedBox(height: 18),
                  FilledButton(onPressed: widget.onLogout, child: const Text('Sign out')),
                ]))),
                _ => quickConnect(),
              };
              if (limits.maxWidth >= 900 && limits.maxHeight >= 850) {
                return page;
              }
              // Preserve the desktop composition without Flex overflow on
              // narrow/short windows: allow both axes to scroll explicitly.
              return SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: SizedBox(
                  width: math.max(900, limits.maxWidth),
                  child: SingleChildScrollView(
                    child: SizedBox(
                      height: math.max(850, limits.maxHeight),
                      child: page,
                    ),
                  ),
                ),
              );
            }),
          )),
          sidebar(),
        ]),
      ),
    ));
  }
}
