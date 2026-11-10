import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app_strings.dart';
import 'brand_theme.dart';
import 'tenant_api.dart';
import 'tenant_models.dart';
import 'protocols.dart';
import 'protocol_catalog_view.dart';
import 'protocol_strings.dart';
import 'native_vpn_bridge.dart';
import 'android_connection_card.dart';
import 'windows_connection_card.dart';
import 'vpn_settings.dart';
import 'vpn_strings.dart';
import 'server_inventory.dart';
import 'country_flag.dart';

void main() => runApp(const TwinConnectApp());

enum AppLanguage { automatic, persian, english }

class TwinConnectApp extends StatefulWidget {
  const TwinConnectApp({super.key});

  @override
  State<TwinConnectApp> createState() => _TwinConnectAppState();
}

class _TwinConnectAppState extends State<TwinConnectApp> {
  static const _languageKey = 'twinconnect_ui_language_v1';
  AppLanguage _language = AppLanguage.automatic;
  BrandPreview? _activeBrand;

  @override
  void initState() {
    super.initState();
    _loadLanguage();
  }

  Future<void> _loadLanguage() async {
    try {
      final preferences = await SharedPreferences.getInstance();
      final saved = preferences.getString(_languageKey);
      if (!mounted) return;
      setState(() {
        _language = switch (saved) {
          'fa' => AppLanguage.persian,
          'en' => AppLanguage.english,
          _ => AppLanguage.automatic,
        };
      });
    } catch (_) {
      // A preference failure must not stop the app; device locale is the default.
    }
  }

  Future<void> _changeLanguage(AppLanguage choice) async {
    setState(() => _language = choice);
    try {
      final preferences = await SharedPreferences.getInstance();
      final code = switch (choice) {
        AppLanguage.automatic => 'system',
        AppLanguage.persian => 'fa',
        AppLanguage.english => 'en',
      };
      await preferences.setString(_languageKey, code);
    } catch (_) {
      // The requested language still applies to this running session.
    }
  }

  @override
  Widget build(BuildContext context) {
    final Locale? selectedLocale = switch (_language) {
      AppLanguage.automatic => null,
      AppLanguage.persian => const Locale('fa'),
      AppLanguage.english => const Locale('en'),
    };

    return MaterialApp(
      title: 'TwinConnect',
      debugShowCheckedModeBanner: false,
      locale: selectedLocale,
      supportedLocales: const [Locale('en'), Locale('fa')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      theme: BrandTheme.make(_activeBrand, Brightness.light),
      darkTheme: BrandTheme.make(_activeBrand, Brightness.dark),
      themeMode: BrandTheme.mode(_activeBrand),
      home: TwinConnectHome(
        language: _language,
        onLanguageChanged: _changeLanguage,
        onBrandChanged: (brand) => setState(() => _activeBrand = brand),
      ),
    );
  }
}

class TwinConnectHome extends StatefulWidget {
  const TwinConnectHome({
    required this.language,
    required this.onLanguageChanged,
    required this.onBrandChanged,
    super.key,
  });

  final AppLanguage language;
  final ValueChanged<AppLanguage> onLanguageChanged;
  final ValueChanged<BrandPreview?> onBrandChanged;

  @override
  State<TwinConnectHome> createState() => _TwinConnectHomeState();
}

class _TwinConnectHomeState extends State<TwinConnectHome> {
  final _formKey = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _password = TextEditingController();

  bool _loading = false;
  String? _errorCode;
  BrandPreview? _brand;
  PanelDirectoryEntry? _confirmedPanel;
  String? _confirmedUsername;
  String? _confirmedSessionToken;
  PanelProtocolCatalog? _catalog;
  AppServerInventory? _servers;
  bool _refreshingServers = false;
  String? _serverRefreshError;
  NativeProtocolReadiness _nativeProtocols =
      const NativeProtocolReadiness(supportedCodes: {});
  bool _protocolCatalogUnavailable = false;
  int _lookupSerial = 0;

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _identify() async {
    if (!_formKey.currentState!.validate() || _loading) return;
    final serial = ++_lookupSerial;
    FocusScope.of(context).unfocus();
    setState(() {
      _loading = true;
      _errorCode = null;
      _brand = null;
      widget.onBrandChanged(null);
      _confirmedPanel = null;
      _confirmedUsername = null;
      _confirmedSessionToken = null;
      _catalog = null;
      _servers = null;
      _refreshingServers = false;
      _serverRefreshError = null;
      _protocolCatalogUnavailable = false;
      _nativeProtocols = const NativeProtocolReadiness(supportedCodes: {});
    });

    try {
      final username = _username.text.trim();
      final namespace = TenantIdentity.parseNamespace(username, '');
      final password = _password.text;
      final api = TenantApi.fromBuildConfig();
      final panel = await api.resolve(namespace);
      final loggedIn = await api.login(
        panel: panel,
        username: username,
        password: password,
      );
      final brand = loggedIn.brand;
      if (!mounted || serial != _lookupSerial) return;
      setState(() {
        _brand = brand;
        widget.onBrandChanged(brand);
        _confirmedPanel = panel;
        _confirmedUsername = username;
        _confirmedSessionToken = loggedIn.sessionToken;
      });
      // Refresh server inventory after authenticated login; failures are isolated.
      _refreshServers();
      // Subscription metadata is not secret and is fetched independently of
      // brand details. A temporary metadata error must not hide renewal links.
      try {
        final catalog = await api.loadSessionProtocolCatalog(
          panel: panel,
          sessionToken: loggedIn.sessionToken,
        );
        final native = await NativeVpnBridge.protocolReadiness();
        if (mounted && serial == _lookupSerial) {
          setState(() {
            _catalog = catalog;
            _nativeProtocols = native;
          });
        }
      } catch (_) {
        if (mounted && serial == _lookupSerial) {
          setState(() => _protocolCatalogUnavailable = true);
        }
      }
    } on FormatException catch (error) {
      if (mounted && serial == _lookupSerial) setState(() => _errorCode = error.message);
    } on TenantApiException catch (error) {
      if (mounted && serial == _lookupSerial) setState(() => _errorCode = error.message);
    } catch (_) {
      if (mounted && serial == _lookupSerial) setState(() => _errorCode = 'UNKNOWN_ERROR');
    } finally {
      _password.clear();
      if (mounted && serial == _lookupSerial) setState(() => _loading = false);
    }
  }

  Future<void> _refreshServers() async {
    final panel = _confirmedPanel;
    final session = _confirmedSessionToken;
    if (panel == null || session == null || _refreshingServers) return;
    final serial = _lookupSerial;
    setState(() {
      _refreshingServers = true;
      _serverRefreshError = null;
    });
    try {
      final api = TenantApi.fromBuildConfig();
      // Server refresh is also a plan/protocol entitlement refresh.
      // Publish both together so removed permissions never remain in the UI
      // alongside newly fetched servers.
      final catalog = await api.loadSessionProtocolCatalog(
        panel: panel, sessionToken: session,
      );
      final inventory = await api.refreshSessionServers(
        panel: panel, sessionToken: session,
      );
      if (!mounted || serial != _lookupSerial) return;
      setState(() {
        _catalog = catalog;
        _servers = inventory;
        _protocolCatalogUnavailable = false;
      });
    } catch (_) {
      if (!mounted || serial != _lookupSerial) return;
      setState(() => _serverRefreshError = 'SERVER_REFRESH_FAILED');
    } finally {
      if (mounted && serial == _lookupSerial) {
        setState(() => _refreshingServers = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final strings = AppStrings.of(context);
    final brand = _brand;

    final accent = Theme.of(context).colorScheme.primary;
    final surface = Theme.of(context).colorScheme.surface;
    final dark = Theme.of(context).brightness == Brightness.dark;
    final foreground = Theme.of(context).colorScheme.onSurface;

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        titleSpacing: 24,
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              height: 35,
              width: 35,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [accent, Theme.of(context).colorScheme.secondary],
                ),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.bolt_rounded, color: Colors.white, size: 23),
            ),
            const SizedBox(width: 10),
            Text(
              strings.appTitle,
              style: const TextStyle(
                fontWeight: FontWeight.w800,
                fontSize: 19,
                letterSpacing: -0.5,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            key: const Key('vpnSettingsButton'),
            tooltip: strings.vpnSettingsTitle,
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => VpnSettingsScreen(
                  brand: brand,
                  tenant: brand?.namespace ?? '',
                  account: brand == null ? '' : _username.text.trim(),
                ),
              ),
            ),
            icon: const Icon(Icons.tune_rounded),
          ),
          Padding(
            padding: const EdgeInsetsDirectional.only(start: 5, end: 18),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<AppLanguage>(
                key: const Key('languagePicker'),
                value: widget.language,
                icon: const Icon(Icons.keyboard_arrow_down_rounded, size: 19),
                onChanged: (value) {
                  if (value != null) widget.onLanguageChanged(value);
                },
                items: [
                  DropdownMenuItem(
                    value: AppLanguage.automatic,
                    child: Text(strings.systemLanguage),
                  ),
                  DropdownMenuItem(
                    value: AppLanguage.persian,
                    child: Text(strings.persianLanguage),
                  ),
                  DropdownMenuItem(
                    value: AppLanguage.english,
                    child: Text(strings.englishLanguage),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
      body: BrandBackground(
        brand: brand,
        child: Stack(
          children: [
            Positioned(
              right: -140,
              top: -160,
              child: IgnorePointer(
                child: Container(
                  width: 560,
                  height: 560,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: RadialGradient(
                      colors: [
                        accent.withValues(alpha: dark ? 0.25 : 0.12),
                        accent.withValues(alpha: 0),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            Positioned(
              left: -160,
              bottom: -250,
              child: IgnorePointer(
                child: Container(
                  width: 550,
                  height: 550,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: RadialGradient(
                      colors: [
                        Theme.of(context).colorScheme.secondary.withValues(
                          alpha: dark ? 0.17 : 0.10,
                        ),
                        Colors.transparent,
                      ],
                    ),
                  ),
                ),
              ),
            ),
            SafeArea(
              child: LayoutBuilder(
                builder: (context, constraints) => Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 520),
                    child: ListView(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 20,
                        vertical: 20,
                      ),
                      shrinkWrap: brand == null,
                      children: [
                        SizedBox(
                          height: brand == null
                              ? (constraints.maxHeight > 640 ? 38 : 8)
                              : 8,
                        ),
                        Container(
                          decoration: BoxDecoration(
                            color: Color.lerp(
                              surface, accent, dark ? 0.045 : 0.025,
                            ),
                            borderRadius: BorderRadius.circular(28),
                            border: Border.all(
                              color: accent.withValues(alpha: dark ? 0.28 : 0.15),
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(
                                  alpha: dark ? 0.30 : 0.08,
                                ),
                                blurRadius: 45,
                                offset: const Offset(0, 22),
                              ),
                            ],
                          ),
                          padding: const EdgeInsets.symmetric(
                            horizontal: 30,
                            vertical: 30,
                          ),
                          child: Form(
                            key: _formKey,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                Align(
                                  alignment: AlignmentDirectional.centerStart,
                                  child: Container(
                                    height: 48,
                                    width: 48,
                                    decoration: BoxDecoration(
                                      color: accent.withValues(alpha: 0.13),
                                      border: Border.all(
                                        color: accent.withValues(alpha: 0.25),
                                      ),
                                      borderRadius: BorderRadius.circular(17),
                                    ),
                                    child: Icon(
                                      Icons.shield_moon_outlined,
                                      color: accent,
                                      size: 25,
                                    ),
                                  ),
                                ),
                                const SizedBox(height: 18),
                                Text(
                                  strings.appLoginTitle,
                                  style: TextStyle(
                                    color: foreground,
                                    fontSize: 26,
                                    fontWeight: FontWeight.w800,
                                    letterSpacing: -0.6,
                                  ),
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  strings.appLoginGuide,
                                  style: TextStyle(
                                    color: foreground.withValues(alpha: 0.65),
                                    fontSize: 13,
                                  ),
                                ),
                                const SizedBox(height: 25),
                                TextFormField(
                                  key: const Key('accountUsername'),
                                  controller: _username,
                                  textDirection: TextDirection.ltr,
                                  autocorrect: false,
                                  decoration: InputDecoration(
                                    labelText: strings.appUsername,
                                    prefixIcon: const Icon(Icons.person_outline_rounded),
                                    filled: true,
                                    fillColor: foreground.withValues(alpha: 0.035),
                                    contentPadding: const EdgeInsets.symmetric(
                                      horizontal: 16, vertical: 18,
                                    ),
                                    border: OutlineInputBorder(
                                      borderRadius: BorderRadius.circular(15),
                                    ),
                                  ),
                                  validator: (text) =>
                                      (text == null || text.trim().isEmpty)
                                          ? strings.usernameRequired
                                          : null,
                                ),
                                const SizedBox(height: 15),
                                TextFormField(
                                  key: const Key('appPassword'),
                                  controller: _password,
                                  obscureText: true,
                                  textDirection: TextDirection.ltr,
                                  decoration: InputDecoration(
                                    labelText: strings.appPassword,
                                    prefixIcon: const Icon(Icons.lock_outline_rounded),
                                    filled: true,
                                    fillColor: foreground.withValues(alpha: 0.035),
                                    contentPadding: const EdgeInsets.symmetric(
                                      horizontal: 16, vertical: 18,
                                    ),
                                    border: OutlineInputBorder(
                                      borderRadius: BorderRadius.circular(15),
                                    ),
                                  ),
                                  validator: (text) =>
                                      (text == null || text.isEmpty)
                                          ? strings.appPasswordRequired
                                          : null,
                                  onFieldSubmitted: (_) => _identify(),
                                ),
                                const SizedBox(height: 22),
                                SizedBox(
                                  height: 52,
                                  child: FilledButton(
                                    key: const Key('identifyButton'),
                                    style: FilledButton.styleFrom(
                                      shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(15),
                                      ),
                                      elevation: 0,
                                    ),
                                    onPressed: _loading ? null : _identify,
                                    child: _loading
                                        ? const SizedBox.square(
                                            dimension: 20,
                                            child: CircularProgressIndicator(
                                              strokeWidth: 2,
                                              color: Colors.white,
                                            ),
                                          )
                                        : Row(
                                            mainAxisAlignment: MainAxisAlignment.center,
                                            children: [
                                              Text(
                                                strings.appLoginButton,
                                                style: const TextStyle(
                                                  fontSize: 15,
                                                  fontWeight: FontWeight.w700,
                                                ),
                                              ),
                                              const SizedBox(width: 10),
                                              const Icon(Icons.arrow_forward_rounded,
                                                  size: 19),
                                            ],
                                          ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        if (_errorCode != null) ...[
                          const SizedBox(height: 12),
                          SelectableText(
                            strings.error(_errorCode!),
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.error,
                            ),
                          ),
                        ],
                        if (brand != null) ...[
                          const SizedBox(height: 20),
                          BrandDetails(brand: brand),
                          if (_protocolCatalogUnavailable) ...[
                            const SizedBox(height: 16),
                            Text(strings.protocolCatalogUnavailable),
                          ],
                          const SizedBox(height: 12),
                  Row(children: [
                    Expanded(child: Text(
                      strings.pick('سرورهای اشتراک', 'Subscription servers'),
                      style: Theme.of(context).textTheme.titleMedium,
                    )),
                    IconButton(
                      key: const Key('refreshSubscriptionServers'),
                      tooltip: strings.pick('به‌روزرسانی سرورها', 'Refresh servers'),
                      onPressed: _refreshingServers ? null : _refreshServers,
                      icon: _refreshingServers
                          ? const SizedBox.square(
                              dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                          : const Icon(Icons.refresh_rounded),
                    ),
                  ]),
                  if (_serverRefreshError != null)
                    Text(strings.pick('دریافت سرورها ناموفق بود',
                      'Could not refresh servers')),
                  if (_servers != null) ...[
                    if (_servers!.servers.isEmpty)
                      Text(strings.pick('سروری برای این اشتراک ثبت نشده',
                        'No servers assigned to this subscription')),
                    for (final server in _servers!.servers)
                      ListTile(
                        key: Key('assignedServer_${server.id}'),
                        leading: CountryFlag(server.countryCode, width: 31),
                        title: Text(server.name),
                        subtitle: Text(server.countryCode),
                        trailing: Text(server.nodeOnline
                            ? strings.pick('نود آنلاین', 'Node online')
                            : strings.pick('نود آفلاین', 'Node offline')),
                      ),
                  ],
                  if (_catalog != null) ...[
                            const SizedBox(height: 20),
                            ProtocolCatalogCard(
                              catalog: _catalog!,
                              native: _nativeProtocols,
                            ),
                            if (_confirmedPanel != null &&
                                _confirmedUsername != null &&
                                _confirmedSessionToken != null) ...[
                              const SizedBox(height: 12),
                              AndroidConnectionCard(
                                key: ValueKey(_confirmedUsername),
                                panel: _confirmedPanel!,
                                username: _confirmedUsername!,
                                sessionToken: _confirmedSessionToken!,
                                catalog: _catalog!,
                                native: _nativeProtocols,
                              ),
                              if (_servers != null) ...[
                                const SizedBox(height: 12),
                                WindowsConnectionCard(
                                  key: ValueKey('windows_${_confirmedUsername!}'),
                                  panel: _confirmedPanel!,
                                  username: _confirmedUsername!,
                                  sessionToken: _confirmedSessionToken!,
                                  catalog: _catalog!,
                                  servers: _servers!,
                                ),
                              ],
                            ],
                          ],
                        ],
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class BrandDetails extends StatelessWidget {
  const BrandDetails({required this.brand, super.key});

  final BrandPreview brand;

  Color get _brandColor => Color(
        int.parse('FF${brand.primaryColor.substring(1)}', radix: 16),
      );

  @override
  Widget build(BuildContext context) {
    final strings = AppStrings.of(context);
    final status = switch (brand.accountStatus) {
      'expired' => strings.statusExpired,
      'active' => strings.statusActive,
      _ => strings.statusOther(brand.accountStatus),
    };

    return Theme(
      data: Theme.of(context).copyWith(
        colorScheme: ColorScheme.fromSeed(
          seedColor: _brandColor,
          brightness: Theme.of(context).brightness,
        ),
      ),
      child: Card(
        key: const Key('brandCard'),
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  CircleAvatar(
                    radius: 26,
                    backgroundColor: _brandColor,
                    child: const Icon(Icons.shield, color: Colors.white),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      brand.brandName,
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Text(status),
              const Divider(height: 30),
              _CopyValue(label: strings.supportTelegram, value: brand.telegramUrl),
              _CopyValue(label: strings.renewalLink, value: brand.renewalUrl),
              _CopyValue(label: strings.supportPhone, value: brand.phone),
              _CopyValue(label: strings.website, value: brand.websiteUrl),
              if (brand.supportText != null) ...[
                const SizedBox(height: 8),
                Text(brand.supportText!),
              ],
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: null,
                icon: const Icon(Icons.power_settings_new),
                label: Text(strings.connectionDisabled),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CopyValue extends StatelessWidget {
  const _CopyValue({required this.label, required this.value});

  final String label;
  final String? value;

  @override
  Widget build(BuildContext context) {
    final text = value;
    if (text == null || text.isEmpty) return const SizedBox.shrink();
    final strings = AppStrings.of(context);

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          SizedBox(
            width: 125,
            child: Text(
              label,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
          Expanded(
            child: SelectableText(
              text,
              textDirection: TextDirection.ltr,
            ),
          ),
          IconButton(
            tooltip: strings.copyTooltip(label),
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: text));
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(strings.copied(label))),
                );
              }
            },
            icon: const Icon(Icons.copy_outlined),
          ),
        ],
      ),
    );
  }
}
