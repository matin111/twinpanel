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
import 'ambient_background.dart';
import 'interactive_glass_card.dart';
import 'live_dashboard.dart';
import 'app_session_store.dart';
import 'account_snapshot.dart';
import 'plan_classification.dart';

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
  final AppSessionStore _sessionStore = const AppSessionStore();
  AppPlanClassification? _plan;
  AppAccountSnapshot? _account;
  String? _accountError;

  int _dashboardTab = 0;
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
  void initState() {
    super.initState();
    _restoreSession();
  }

  Future<void> _restoreSession() async {
    final serial = _lookupSerial;
    try {
      final remembered = await _sessionStore.lastUsername();
      if (!mounted || serial != _lookupSerial) return;
      if (remembered != null) _username.text = remembered;
      final saved = await _sessionStore.read();
      if (saved == null) return;
      final api = TenantApi.fromBuildConfig();
      final namespace = TenantIdentity.parseNamespace(saved.username, '');
      if (namespace != saved.brand.namespace) return;
      final panel = await api.resolve(namespace);
      // OS storage does not make a session valid: always revalidate
      // with the owning panel before restoring an authenticated screen.
      final catalog = await api.loadSessionProtocolCatalog(
        panel: panel, sessionToken: saved.sessionToken,
      );
      final native = await NativeVpnBridge.protocolReadiness();
      if (!mounted || serial != _lookupSerial) return;
      setState(() {
        _brand = saved.brand;
        widget.onBrandChanged(saved.brand);
        _confirmedPanel = panel;
        _confirmedUsername = saved.username;
        _confirmedSessionToken = saved.sessionToken;
        _catalog = catalog;
        _nativeProtocols = native;
      });
      _refreshServers();
      _loadAccountPlan(panel, saved.sessionToken, serial);
      _loadAccountSnapshot(panel, saved.sessionToken, serial);
    } on TenantApiException catch (error) {
      if (error.message == 'APP_LOGIN_INVALID' ||
          error.message == 'APP_NOT_AUTHORIZED') {
        try { await _sessionStore.clearSession(); } catch (_) {}
      }
    } catch (_) {
      // An offline panel keeps the remembered username, not access.
    } finally {
      // No blocking splash: login stays responsive while secure storage is checked.
    }
  }

  Future<void> _loadAccountSnapshot(
    PanelDirectoryEntry panel, String session, int serial,
  ) async {
    try {
      final snapshot = await TenantApi.fromBuildConfig().loadSessionAccount(
        panel: panel, sessionToken: session,
      );
      if (mounted && serial == _lookupSerial) {
        setState(() { _account = snapshot; _accountError = null; });
      }
    } catch (error) {
      if (mounted && serial == _lookupSerial) {
        setState(() => _accountError = error is TenantApiException
            ? error.message : 'ACCOUNT_RESPONSE_INVALID');
      }
    }
  }

  Future<void> _loadAccountPlan(
    PanelDirectoryEntry panel, String session, int serial,
  ) async {
    try {
      final plan = await TenantApi.fromBuildConfig().loadSessionPlan(
        panel: panel, sessionToken: session,
      );
      if (mounted && serial == _lookupSerial) {
        setState(() => _plan = plan);
      }
    } catch (_) {
      // Missing plan metadata is not a reason to sign out.
    }
  }

  Future<void> _signOutSafely() async {
    // Invalidate stale account / inventory requests immediately, then
    // erase the OS-protected session before displaying the login screen.
    ++_lookupSerial;
    try {
      await _sessionStore.clearSession();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Unable to clear saved session. Try again.'),
        ));
      }
      return;
    }
    if (!mounted) return;
    setState(() {
      _brand = null;
      _confirmedPanel = null;
      _confirmedUsername = null;
      _confirmedSessionToken = null;
      _catalog = null;
      _servers = null;
      _plan = null;
      _account = null;
      _accountError = null;
      _dashboardTab = 0;
      _errorCode = null;
      widget.onBrandChanged(null);
      _password.clear();
    });
  }

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
      _plan = null;
      _account = null;
      _accountError = null;
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
      // Persist only in OS secure storage; invalid sessions must reauthenticate.
      try {
        await _sessionStore.save(username: username,
          sessionToken: loggedIn.sessionToken, brand: brand);
      } catch (_) {}
      _loadAccountPlan(panel, loggedIn.sessionToken, serial);
      _loadAccountSnapshot(panel, loggedIn.sessionToken, serial);
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


  // ignore: unused_element
  Widget _buildAuthenticatedDashboard(
    BuildContext context,
    AppStrings strings,
    BrandPreview brand,
  ) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    final accent = theme.colorScheme.primary;
    final isWide = MediaQuery.sizeOf(context).width >= 820;
    final sections = [
      strings.pick('اتصال', 'Connect'),
      strings.pick('مکان‌ها', 'Locations'),
      strings.pick('تنظیمات', 'Settings'),
      strings.pick('حساب', 'Account'),
    ];
    final icons = [
      Icons.power_settings_new_rounded,
      Icons.public_rounded,
      Icons.tune_rounded,
      Icons.person_outline_rounded,
    ];

    Widget glass(Widget child) => TwinConnectGlassCard(
      dark: dark,
      radius: 24,
      padding: const EdgeInsets.all(22),
      child: child,
    );

    Widget header(String title, IconData icon, {Widget? trailing}) => Row(
      children: [
        Icon(icon, color: accent),
        const SizedBox(width: 12),
        Expanded(child: Text(title, style: theme.textTheme.titleLarge?.copyWith(
          fontWeight: FontWeight.w800,
        ))),
        if (trailing != null) trailing,
      ],
    );

    Widget serverInventory() {
      if (_servers == null) {
        return glass(Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            header(strings.pick('سرورهای اشتراک', 'Subscription servers'),
              Icons.public_rounded,
              trailing: IconButton(
                tooltip: strings.pick('به‌روزرسانی', 'Refresh'),
                onPressed: _refreshingServers ? null : _refreshServers,
                icon: const Icon(Icons.refresh_rounded),
              )),
            const SizedBox(height: 14),
            Text(_serverRefreshError == null
              ? strings.pick('در حال دریافت اطلاعات سرورها…', 'Loading servers…')
              : strings.pick('دریافت سرورها ناموفق بود', 'Could not refresh servers')),
          ],
        ));
      }
      return glass(Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          header(strings.pick('مکان‌های در دسترس', 'Available locations'),
            Icons.public_rounded,
            trailing: IconButton(
              tooltip: strings.pick('به‌روزرسانی سرورها', 'Refresh servers'),
              onPressed: _refreshingServers ? null : _refreshServers,
              icon: _refreshingServers
                ? const SizedBox.square(dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh_rounded),
            )),
          const SizedBox(height: 14),
          if (_servers!.servers.isEmpty)
            Text(strings.pick('سروری برای این اشتراک ثبت نشده',
              'No servers assigned to this subscription')),
          for (final server in _servers!.servers)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                key: Key('assignedServer_${server.id}'),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16)),
                tileColor: accent.withValues(alpha: 0.065),
                leading: CountryFlag(server.countryCode, width: 31),
                title: Text(server.name),
                subtitle: Text(server.countryCode),
                trailing: Text(server.nodeOnline
                  ? strings.pick('نود آنلاین', 'Node online')
                  : strings.pick('نود آفلاین', 'Node offline')),
              ),
            ),
        ],
      ));
    }

    Widget page;
    switch (_dashboardTab) {
      case 0:
        page = Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            glass(Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                header(strings.pick('اتصال امن', 'Secure connection'),
                  Icons.shield_outlined),
                const SizedBox(height: 10),
                Text(strings.pick(
                  'برای اتصال، یکی از پروتکل‌های فعال اشتراک را انتخاب کنید.',
                  'Choose an enabled subscription protocol to connect.')),
              ],
            )),
            const SizedBox(height: 16),
            if (_protocolCatalogUnavailable)
              glass(Text(strings.protocolCatalogUnavailable)),
            if (_catalog == null && !_protocolCatalogUnavailable)
              glass(const Center(child: CircularProgressIndicator())),
            if (_catalog != null) ...[
              ProtocolCatalogCard(catalog: _catalog!, native: _nativeProtocols),
              if (_confirmedPanel != null &&
                  _confirmedUsername != null &&
                  _confirmedSessionToken != null) ...[
                const SizedBox(height: 12),
                if (Theme.of(context).platform == TargetPlatform.android)
                  AndroidConnectionCard(
                    key: ValueKey(_confirmedUsername),
                    panel: _confirmedPanel!,
                    username: _confirmedUsername!,
                    sessionToken: _confirmedSessionToken!,
                    catalog: _catalog!,
                    native: _nativeProtocols,
                  ),
                if (Theme.of(context).platform != TargetPlatform.android &&
                    _servers != null)
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
        );
        break;
      case 1:
        page = serverInventory();
        break;
      case 2:
        page = Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            glass(Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                header(strings.pick('تنظیمات اتصال', 'Connection settings'),
                  Icons.tune_rounded),
                const SizedBox(height: 18),
                FilledButton.icon(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => VpnSettingsScreen(
                        brand: brand,
                        tenant: brand.namespace,
                        account: _confirmedUsername ?? '',
                      ),
                    ),
                  ),
                  icon: const Icon(Icons.settings_rounded),
                  label: Text(strings.vpnSettingsTitle),
                ),
              ],
            )),
            const SizedBox(height: 16),
            glass(Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                header(strings.pick('زبان برنامه', 'App language'),
                  Icons.language_rounded),
                const SizedBox(height: 12),
                DropdownButton<AppLanguage>(
                  isExpanded: true,
                  value: widget.language,
                  onChanged: (language) {
                    if (language != null) widget.onLanguageChanged(language);
                  },
                  items: [
                    DropdownMenuItem(value: AppLanguage.automatic,
                      child: Text(strings.systemLanguage)),
                    DropdownMenuItem(value: AppLanguage.persian,
                      child: Text(strings.persianLanguage)),
                    DropdownMenuItem(value: AppLanguage.english,
                      child: Text(strings.englishLanguage)),
                  ],
                ),
              ],
            )),
          ],
        );
        break;
      default:
        page = Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            glass(Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                header(strings.pick('حساب کاربری', 'Account'),
                  Icons.person_outline_rounded),
                const SizedBox(height: 16),
                Text(_confirmedUsername ?? '',
                  style: theme.textTheme.titleMedium),
                const SizedBox(height: 8),
                Text(strings.pick('وضعیت اشتراک', 'Subscription status')),
                Text(brand.accountStatus == 'active'
                  ? strings.statusActive
                  : brand.accountStatus == 'expired'
                    ? strings.statusExpired
                    : strings.statusOther(brand.accountStatus)),
              ],
            )),
            const SizedBox(height: 16),
            glass(Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                header(strings.pick('پشتیبانی و تمدید', 'Support and renewal'),
                  Icons.help_outline_rounded),
                const SizedBox(height: 12),
                _CopyValue(label: strings.supportTelegram, value: brand.telegramUrl),
                _CopyValue(label: strings.renewalLink, value: brand.renewalUrl),
                _CopyValue(label: strings.supportPhone, value: brand.phone),
                _CopyValue(label: strings.website, value: brand.websiteUrl),
                if (brand.supportText != null) Text(brand.supportText!),
              ],
            )),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: () {
                ++_lookupSerial;
                setState(() {
                  _brand = null;
                  _confirmedPanel = null;
                  _confirmedUsername = null;
                  _confirmedSessionToken = null;
                  _catalog = null;
                  _servers = null;
                  _dashboardTab = 0;
                  _errorCode = null;
                  widget.onBrandChanged(null);
                });
              },
              icon: const Icon(Icons.logout_rounded),
              label: Text(strings.pick('خروج از حساب', 'Sign out')),
            ),
          ],
        );
        break;
    }

    final content = ListView(
      key: ValueKey('dashboard_page_$_dashboardTab'),
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
      children: [
        Text(sections[_dashboardTab],
          style: theme.textTheme.headlineMedium?.copyWith(
            fontWeight: FontWeight.w800)),
        const SizedBox(height: 20),
        page,
      ],
    );

    return Scaffold(
      key: const Key('authenticatedDashboard'),
      extendBodyBehindAppBar: true,
      body: TwinConnectAmbientBackground(
        dark: dark,
        child: SafeArea(
          child: isWide
            ? Row(children: [
                Container(
                  width: 224,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12, vertical: 20),
                  child: glass(Column(
                    children: [
                      for (var i = 0; i < sections.length; i++)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: ListTile(
                            key: Key('dashboardNav_$i'),
                            selected: _dashboardTab == i,
                            selectedTileColor: accent.withValues(alpha: 0.14),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(14)),
                            leading: Icon(icons[i]),
                            title: Text(sections[i]),
                            onTap: () => setState(() => _dashboardTab = i),
                          ),
                        ),
                    ],
                  )),
                ),
                Expanded(child: content),
              ])
            : Column(children: [
                Expanded(child: content),
                NavigationBar(
                  selectedIndex: _dashboardTab,
                  onDestinationSelected: (index) =>
                    setState(() => _dashboardTab = index),
                  destinations: [
                    for (var i = 0; i < sections.length; i++)
                      NavigationDestination(
                        icon: Icon(icons[i]),
                        label: sections[i],
                      ),
                  ],
                ),
              ]),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final strings = AppStrings.of(context);
    final brand = _brand;
    if (brand != null && _confirmedPanel != null &&
        _confirmedUsername != null && _confirmedSessionToken != null) {
      return TwinConnectLiveDashboard(
        key: ValueKey(_confirmedUsername),
        panel: _confirmedPanel!,
        username: _confirmedUsername!,
        sessionToken: _confirmedSessionToken!,
        catalog: _catalog,
        servers: _servers,
        native: _nativeProtocols,
        plan: _plan,
        account: _account,
        accountError: _accountError,
        onRefreshAccount: () {
          if (_confirmedPanel != null && _confirmedSessionToken != null) {
            _loadAccountSnapshot(_confirmedPanel!, _confirmedSessionToken!, _lookupSerial);
            _loadAccountPlan(_confirmedPanel!, _confirmedSessionToken!, _lookupSerial);
          }
        },
        accountStatus: _brand?.accountStatus ?? 'unknown',
        onRefresh: _refreshServers,
        onLogout: _signOutSafely,
      );
    }

    final accent = Theme.of(context).colorScheme.primary;
    final dark = Theme.of(context).brightness == Brightness.dark;
    final foreground = Theme.of(context).colorScheme.onSurface;

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        titleSpacing: 24,
        // Before authentication, never display the app brand, reseller
        // brand, panel brand or a customer-identifying title.
        title: brand == null
            ? const SizedBox.shrink()
            : Row(
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
      body: TwinConnectAmbientBackground(
        dark: dark,
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
                        TweenAnimationBuilder<double>(
                          key: const Key('loginEntranceAnimation'),
                          tween: Tween(begin: 0, end: 1),
                          duration: const Duration(milliseconds: 720),
                          curve: Curves.easeOutCubic,
                          builder: (context, progress, child) => Opacity(
                            opacity: progress,
                            child: Transform.translate(
                              offset: Offset(0, 22 * (1 - progress)),
                              child: child,
                            ),
                          ),
                          child: TwinConnectGlassCard(
                            key: const Key('loginGlassCard'),
                            dark: dark,
                            radius: 28,
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
