import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app_strings.dart';
import 'tenant_api.dart';
import 'tenant_models.dart';
import 'protocols.dart';
import 'protocol_catalog_view.dart';
import 'protocol_strings.dart';
import 'native_vpn_bridge.dart';
import 'android_connection_card.dart';
import 'windows_preview_fixture.dart';
import 'reference_desktop_shell.dart';
import 'vpn_settings.dart';
import 'vpn_strings.dart';

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
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF7358DF),
        ),
      ),
      darkTheme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF7358DF),
          brightness: Brightness.dark,
        ),
      ),
      themeMode: ThemeMode.system,
      home: TwinConnectHome(
        language: _language,
        onLanguageChanged: _changeLanguage,
      ),
    );
  }
}

class TwinConnectHome extends StatefulWidget {
  const TwinConnectHome({
    required this.language,
    required this.onLanguageChanged,
    super.key,
  });

  final AppLanguage language;
  final ValueChanged<AppLanguage> onLanguageChanged;

  @override
  State<TwinConnectHome> createState() => _TwinConnectHomeState();
}

class _TwinConnectHomeState extends State<TwinConnectHome> {
  final _formKey = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _subscription = TextEditingController();
  final _tenantCode = TextEditingController();

  bool _loading = false;
  String? _errorCode;
  BrandPreview? _brand;
  PanelDirectoryEntry? _confirmedPanel;
  String? _confirmedUsername;
  String? _confirmedToken;
  PanelProtocolCatalog? _catalog;
  NativeProtocolReadiness _nativeProtocols =
      const NativeProtocolReadiness(supportedCodes: {});
  bool _protocolCatalogUnavailable = false;
  bool _offlineDemo = false;
  bool _showLogin = false;
  int _lookupSerial = 0;

  @override
  void dispose() {
    _username.dispose();
    _subscription.dispose();
    _tenantCode.dispose();
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
      _offlineDemo = false;
      _confirmedPanel = null;
      _confirmedUsername = null;
      _confirmedToken = null;
      _catalog = null;
      _protocolCatalogUnavailable = false;
      _nativeProtocols = const NativeProtocolReadiness(supportedCodes: {});
    });

    try {
      final username = _username.text.trim();
      final namespace = TenantIdentity.parseNamespace(
        username,
        _tenantCode.text,
      );
      final token = SubscriptionInput.tokenFromInput(_subscription.text);
      final api = TenantApi.fromBuildConfig();
      final panel = await api.resolve(namespace);
      final brand = await api.loadBrand(
        panel: panel,
        username: username,
        shareToken: token,
      );
      if (!mounted || serial != _lookupSerial) return;
      setState(() {
        _brand = brand;
        _showLogin = false;
        _confirmedPanel = panel;
        _confirmedUsername = username;
        _confirmedToken = token;
      });
      // Subscription metadata is not secret and is fetched independently of
      // brand details. A temporary metadata error must not hide renewal links.
      try {
        final catalog = await api.loadProtocolCatalog(
          panel: panel,
          username: username,
          shareToken: token,
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
      if (mounted && serial == _lookupSerial) setState(() => _loading = false);
    }
  }

  void _showOfflineDemo() {
    ++_lookupSerial; // Do not allow a late network response to replace demo state.
    FocusScope.of(context).unfocus();
    setState(() {
      _offlineDemo = true;
      _errorCode = null;
      _loading = false;
      _confirmedPanel = null;
      _confirmedUsername = null;
      _confirmedToken = null;
      _showLogin = false;
      _brand = WindowsPreviewFixture.brand();
      _catalog = WindowsPreviewFixture.protocolCatalog();
      _nativeProtocols =
          const NativeProtocolReadiness(supportedCodes: {});
      _protocolCatalogUnavailable = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final strings = AppStrings.of(context);
    final brand = _brand;

    final desktop = Platform.isWindows || Platform.isLinux || Platform.isMacOS;

    // The reference dashboard is the actual initial Windows surface.
    // Preview state is explicitly signed out; account identification is
    // accessible from Account -> Sign in and never fakes tunnel connectivity.
    if (desktop && brand == null && !_showLogin) {
      return ReferenceDesktopShell(
        brand: WindowsPreviewFixture.brand(),
        username: 'Guest preview',
        onLogin: () => setState(() => _showLogin = true),
        onLogout: () => setState(() => _showLogin = true),
        onSettings: () => setState(() => _showLogin = true),
        locations: const Center(child: Text(
          'Sign in to retrieve your available servers and protocols.',
          style: TextStyle(color: Colors.white),
        )),
      );
    }

    if (desktop && brand != null) {
      return ReferenceDesktopShell(
        brand: brand,
        username: _offlineDemo ? 'Offline preview' : (_confirmedUsername ?? _username.text.trim()),
        onLogout: () => setState(() {
          _brand = null;
          _catalog = null;
          _confirmedPanel = null;
          _confirmedUsername = null;
          _confirmedToken = null;
          _offlineDemo = false;
          _showLogin = false;
        }),
        onSettings: () => Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => VpnSettingsScreen(
              tenant: brand.namespace,
              account: _offlineDemo ? 'offline-demo-only' : _username.text.trim(),
            ),
          ),
        ),
        locations: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            BrandDetails(brand: brand),
            if (_offlineDemo) const Padding(
              padding: EdgeInsets.all(12),
              child: Text('Offline preview: VPN functions and telemetry are disabled.'),
            ),
            if (_protocolCatalogUnavailable)
              Text(strings.protocolCatalogUnavailable),
            if (_catalog != null) ...[
              ProtocolCatalogCard(
                catalog: _catalog!,
                native: _nativeProtocols,
              ),
              if (_confirmedPanel != null &&
                  _confirmedUsername != null &&
                  _confirmedToken != null)
                AndroidConnectionCard(
                  key: ValueKey(_confirmedUsername),
                  panel: _confirmedPanel!,
                  username: _confirmedUsername!,
                  shareToken: _confirmedToken!,
                  catalog: _catalog!,
                  native: _nativeProtocols,
                ),
            ],
          ],
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(strings.appTitle),
        actions: [
          IconButton(
            key: const Key('vpnSettingsButton'),
            tooltip: strings.vpnSettingsTitle,
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => VpnSettingsScreen(
                  tenant: brand?.namespace ?? '',
                  account: _offlineDemo
                      ? 'offline-demo-only'
                      : (brand == null ? '' : _username.text.trim()),
                ),
              ),
            ),
            icon: const Icon(Icons.tune_outlined),
          ),
          Tooltip(
            message: strings.engineNotReady,
            child: const Padding(
              padding: EdgeInsets.symmetric(horizontal: 8),
              child: Icon(Icons.shield_outlined),
            ),
          ),
          Padding(
            padding: const EdgeInsetsDirectional.only(end: 12),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<AppLanguage>(
                key: const Key('languagePicker'),
                value: widget.language,
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
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 740),
            child: ListView(
              padding: const EdgeInsets.all(18),
              children: [
                const SizedBox(height: 14),
                const Icon(Icons.shield_moon_outlined, size: 60),
                const SizedBox(height: 12),
                Text(
                  strings.appHeadline,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 8),
                Text(
                  strings.appIntroduction,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 22),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Form(
                      key: _formKey,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(
                            strings.identifyAccount,
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                          const SizedBox(height: 18),
                          TextFormField(
                            key: const Key('accountUsername'),
                            controller: _username,
                            textDirection: TextDirection.ltr,
                            decoration: InputDecoration(
                              labelText: strings.accountUsername,
                              hintText: strings.accountUsernameHint,
                              border: const OutlineInputBorder(),
                            ),
                            validator: (text) =>
                                (text == null || text.trim().isEmpty)
                                    ? strings.usernameRequired
                                    : null,
                          ),
                          const SizedBox(height: 13),
                          TextFormField(
                            key: const Key('subscriptionLink'),
                            controller: _subscription,
                            textDirection: TextDirection.ltr,
                            decoration: InputDecoration(
                              labelText: strings.subscription,
                              hintText: strings.subscriptionHint,
                              border: const OutlineInputBorder(),
                            ),
                            validator: (text) =>
                                (text == null || text.trim().isEmpty)
                                    ? strings.subscriptionRequired
                                    : null,
                          ),
                          const SizedBox(height: 13),
                          TextFormField(
                            key: const Key('tenantCode'),
                            controller: _tenantCode,
                            textDirection: TextDirection.ltr,
                            decoration: InputDecoration(
                              labelText: strings.tenantCode,
                              hintText: strings.tenantCodeHint,
                              border: const OutlineInputBorder(),
                            ),
                          ),
                          const SizedBox(height: 18),
                          FilledButton.icon(
                            key: const Key('identifyButton'),
                            onPressed: _loading ? null : _identify,
                            icon: _loading
                                ? const SizedBox.square(
                                    dimension: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Icon(Icons.verified_user_outlined),
                            label: Text(strings.identifyButton),
                          ),
                          const SizedBox(height: 12),
                          OutlinedButton.icon(
                            key: const Key('windowsDemoButton'),
                            onPressed: _showOfflineDemo,
                            icon: const Icon(Icons.desktop_windows_outlined),
                            label: Text(strings.previewButton),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            strings.previewSubtitle,
                            textAlign: TextAlign.center,
                            style: Theme.of(context).textTheme.bodySmall,
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
                  if (_offlineDemo) ...[
                    Card(
                      key: const Key('offlineDemoBanner'),
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Row(
                          children: [
                            const Icon(Icons.info_outline),
                            const SizedBox(width: 12),
                            Expanded(child: Text(strings.previewBanner)),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                  ],
                  BrandDetails(brand: brand),
                  if (_protocolCatalogUnavailable) ...[
                    const SizedBox(height: 16),
                    Text(strings.protocolCatalogUnavailable),
                  ],
                  if (_catalog != null) ...[
                    const SizedBox(height: 20),
                    ProtocolCatalogCard(
                      catalog: _catalog!,
                      native: _nativeProtocols,
                    ),
                    if (_confirmedPanel != null &&
                        _confirmedUsername != null &&
                        _confirmedToken != null) ...[
                      const SizedBox(height: 12),
                      AndroidConnectionCard(
                        key: ValueKey(_confirmedUsername),
                        panel: _confirmedPanel!,
                        username: _confirmedUsername!,
                        shareToken: _confirmedToken!,
                        catalog: _catalog!,
                        native: _nativeProtocols,
                      ),
                    ],
                  ],
                ],
                const SizedBox(height: 20),
                Text(
                  strings.windowsEnginePending,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text(
                  strings.developmentNotice,
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
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
