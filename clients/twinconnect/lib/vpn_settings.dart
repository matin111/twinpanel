import 'package:flutter/material.dart';

import 'app_strings.dart';
import 'brand_theme.dart';
import 'tenant_models.dart';
import 'native_vpn_bridge.dart';
import 'vpn_policy.dart';
import 'vpn_policy_store.dart';
import 'vpn_strings.dart';

/// Controls are enabled only for verified native capabilities.
class VpnSettingsScreen extends StatefulWidget {
  const VpnSettingsScreen({
    required this.tenant,
    required this.account,
    this.brand,
    super.key,
  });

  final String tenant;
  final String account;
  final BrandPreview? brand;

  @override
  State<VpnSettingsScreen> createState() => _VpnSettingsScreenState();
}

class _VpnSettingsScreenState extends State<VpnSettingsScreen> {
  final _store = const VpnPolicyStore();
  final _appId = TextEditingController();

  VpnPolicy _policy = const VpnPolicy();
  NativeVpnCapabilities _capabilities =
      NativeVpnCapabilities.unavailable(NativeVpnBridge.platform);
  bool _loading = true;
  bool _saving = false;

  bool get _identified =>
      widget.tenant.trim().isNotEmpty && widget.account.trim().isNotEmpty;

  // A platform name does not prove a working per-app routing engine.
  // Windows/Android options stay disabled until OS-native rules are verified.
  bool get _includeAppsReady =>
      _capabilities.engineReady && _capabilities.includeApps;

  bool get _excludeAppsReady =>
      _capabilities.engineReady && _capabilities.excludeApps;

  @override
  void initState() {
    super.initState();
    _read();
  }

  Future<void> _read() async {
    final capabilities = await NativeVpnBridge.probe();
    final policy = _identified
        ? await _store.load(widget.tenant, widget.account)
        : const VpnPolicy();
    if (!mounted) return;
    setState(() {
      _capabilities = capabilities;
      _policy = policy;
      _loading = false;
    });
  }

  @override
  void dispose() {
    _appId.dispose();
    super.dispose();
  }

  void _update(VpnPolicy next) => setState(() => _policy = next);

  void _addApp() {
    if ((_policy.routingMode == VpnRoutingMode.onlySelectedApps &&
            !_includeAppsReady) ||
        (_policy.routingMode == VpnRoutingMode.excludeSelectedApps &&
            !_excludeAppsReady)) {
      return;
    }
    final identifier = _appId.text.trim();
    if (identifier.isEmpty) return;
    if (!_policy.appIds.contains(identifier)) {
      _update(_policy.copyWith(
        appIds: [..._policy.appIds, identifier],
      ));
    }
    _appId.clear();
  }

  void _removeApp(String identifier) {
    _update(_policy.copyWith(
      appIds: _policy.appIds.where((id) => id != identifier).toList(),
    ));
  }

  Future<void> _save() async {
    if (_saving || !_identified || !_capabilities.engineReady) return;
    final problems = _policy.draftProblems(_capabilities.platform, managedDevice: _capabilities.managedDevice);
    if (problems.isNotEmpty) return;

    setState(() => _saving = true);
    bool saved = false;
    try {
      saved = await _store.save(widget.tenant, widget.account, _policy);
    } catch (_) {
      saved = false;
    }
    if (!mounted) return;
    setState(() => _saving = false);
    final strings = AppStrings.of(context);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(saved ? strings.vpnSaved : strings.vpnSaveError)),
    );
  }

  Widget _choice(
    VpnRoutingMode mode,
    String title, {
    bool enabled = true,
  }) {
    return ChoiceChip(
      key: Key('vpnMode_${mode.name}'),
      label: Text(title),
      selected: _policy.routingMode == mode,
      onSelected: enabled
          ? (_) => _update(_policy.copyWith(routingMode: mode))
          : null,
    );
  }

  Widget _section(BuildContext context, String title) => Padding(
    padding: const EdgeInsets.only(top: 26, bottom: 12),
    child: Text(
      title,
      style: Theme.of(context).textTheme.titleLarge,
    ),
  );

  @override
  Widget build(BuildContext context) {
    final s = AppStrings.of(context);
    final issues = _policy.draftProblems(_capabilities.platform, managedDevice: _capabilities.managedDevice);
    final selectedMode = _capabilities.engineReady &&
        _policy.routingMode != VpnRoutingMode.fullTunnel;
    final platformName = switch (_capabilities.platform) {
      VpnPlatform.android => s.vpnPlatformAndroid,
      VpnPlatform.windows => s.vpnPlatformWindows,
      VpnPlatform.ios => s.vpnPlatformIos,
      VpnPlatform.macos => s.vpnPlatformMacos,
      VpnPlatform.other => s.vpnPlatformOther,
    };

    return Scaffold(
      appBar: AppBar(title: Text(s.vpnSettingsTitle)),
      body: BrandBackground(
        brand: widget.brand,
        child: _loading
          ? const Center(child: CircularProgressIndicator())
          : SafeArea(
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 760),
                  child: ListView(
                    padding: const EdgeInsets.all(20),
                    children: [
                      ListTile(
                        key: const Key('vpnNotActiveNotice'),
                        contentPadding: EdgeInsets.zero,
                        leading: Icon(
                          _capabilities.engineReady
                              ? Icons.check_circle_outline
                              : Icons.shield_outlined,
                        ),
                        title: Text('${s.vpnPlatformStatus} · $platformName'),
                        subtitle: Text(
                          _capabilities.engineReady
                              ? s.vpnEngineAvailable
                              : s.vpnEngineUnavailable,
                        ),
                      ),
                      _section(context, s.vpnRoutingTitle),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          _choice(VpnRoutingMode.fullTunnel, s.vpnFullTunnel,
                              enabled: _capabilities.engineReady && _capabilities.fullTunnel),
                          _choice(
                            VpnRoutingMode.onlySelectedApps,
                            s.vpnOnlyApps,
                            enabled: _includeAppsReady,
                          ),
                          _choice(
                            VpnRoutingMode.excludeSelectedApps,
                            s.vpnExceptApps,
                            enabled: _excludeAppsReady,
                          ),
                        ],
                      ),


                      if (selectedMode) ...[

                        const SizedBox(height: 14),
                        Text(
                          s.vpnAppIds,
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            Expanded(
                              child: TextField(
                                key: const Key('vpnAppIdentifier'),
                                controller: _appId,
                                textDirection: TextDirection.ltr,
                                onSubmitted: (_) => _addApp(),
                                decoration: InputDecoration(
                                  labelText: s.vpnAppIdLabel,
                                  hintText: _capabilities.platform ==
                                          VpnPlatform.windows
                                      ? s.vpnWindowsHint
                                      : s.vpnAndroidHint,
                                  border: const OutlineInputBorder(),
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            IconButton.filled(
                              key: const Key('vpnAddAppButton'),
                              tooltip: s.vpnAddApp,
                              onPressed: _addApp,
                              icon: const Icon(Icons.add),
                            ),
                          ],
                        ),

                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 8,
                          runSpacing: 6,
                          children: [
                            for (final id in _policy.appIds)
                              InputChip(
                                label: Text(
                                  id,
                                  textDirection: TextDirection.ltr,
                                ),
                                onDeleted: () => _removeApp(id),
                                deleteButtonTooltipMessage: s.vpnRemoveApp,
                              ),
                          ],
                        ),
                      ],
                      _section(context, s.vpnSecurityTitle),
                      SwitchListTile.adaptive(
                        key: const Key('vpnKillSwitch'),
                        title: Text(s.vpnKillSwitch),
                        subtitle: Text(s.vpnKillSwitchSubtitle),
                        value: _capabilities.engineReady && _capabilities.killSwitchEnforced && _policy.killSwitchRequested,
                        onChanged: _capabilities.engineReady &&
                                _capabilities.killSwitchEnforced
                            ? (value) => _update(
                                _policy.copyWith(killSwitchRequested: value))
                            : null,
                      ),

                      SwitchListTile.adaptive(
                        key: const Key('vpnDnsGuard'),
                        title: Text(s.vpnDnsProtected),
                        subtitle: Text(s.vpnDnsHint),
                        value: _capabilities.engineReady && _capabilities.dnsGuard && _policy.dnsMode == VpnDnsMode.protected,
                        onChanged: _capabilities.engineReady && _capabilities.dnsGuard
                            ? (value) => _update(_policy.copyWith(
                                dnsMode: value ? VpnDnsMode.protected : VpnDnsMode.system))
                            : null,
                      ),
                      SwitchListTile.adaptive(
                        key: const Key('vpnIpv6Guard'),
                        title: Text(s.vpnIpv6Protected),
                        subtitle: Text(s.vpnIpv6Hint),
                        value: _capabilities.engineReady && _capabilities.ipv6Guard && _policy.ipv6Mode == VpnIpv6Mode.tunnelOrBlock,
                        onChanged: _capabilities.engineReady && _capabilities.ipv6Guard
                            ? (value) => _update(_policy.copyWith(
                                ipv6Mode: value ? VpnIpv6Mode.tunnelOrBlock : VpnIpv6Mode.unprotected))
                            : null,
                      ),
                      SwitchListTile.adaptive(
                        key: const Key('vpnLanAccess'),
                        title: Text(s.vpnAllowLan),
                        subtitle: Text(s.vpnAllowLanHint),
                        value: _capabilities.engineReady && _capabilities.localNetworkBypass && _policy.allowLan,
                        onChanged: _capabilities.engineReady && _capabilities.localNetworkBypass
                            ? (value) => _update(_policy.copyWith(allowLan: value))
                            : null,
                      ),
                      _section(context, s.vpnAutomationTitle),
                      SwitchListTile.adaptive(
                        key: const Key('vpnAutoReconnect'),
                        title: Text(s.vpnAutoReconnect),
                        value: _capabilities.engineReady && _capabilities.autoReconnect && _policy.autoReconnect,
                        onChanged: _capabilities.engineReady && _capabilities.autoReconnect
                            ? (value) => _update(_policy.copyWith(autoReconnect: value))
                            : null,
                      ),
                      SwitchListTile.adaptive(
                        key: const Key('vpnAutoConnect'),
                        title: Text(s.vpnAutoConnect),
                        value: _capabilities.engineReady && _capabilities.autoConnect && _policy.autoConnect,
                        onChanged: _capabilities.engineReady && _capabilities.autoConnect
                            ? (value) => _update(_policy.copyWith(autoConnect: value))
                            : null,
                      ),
                      SwitchListTile.adaptive(
                        key: const Key('vpnAutoSelect'),
                        title: Text(s.vpnAutoSelectServer),
                        value: false,
                        onChanged: null, // No verified native auto-selection engine.
                      ),


                      const SizedBox(height: 18),
                      FilledButton.icon(
                        key: const Key('vpnSaveButton'),
                        onPressed: !_identified ||
                                !_capabilities.engineReady ||
                                _saving ||
                                issues.isNotEmpty
                            ? null
                            : _save,
                        icon: const Icon(Icons.save_outlined),
                        label: Text(s.vpnSave),
                      ),
                      const SizedBox(height: 12),
                    ],
                  ),
                ),
              ),
            ),
      ),
    );
  }
}
