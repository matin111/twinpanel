import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'tenant_api.dart';
import 'tenant_models.dart';

void main() => runApp(const TwinConnectApp());

class TwinConnectApp extends StatelessWidget {
  const TwinConnectApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TwinConnect',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF7358DF)),
      ),
      darkTheme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF7358DF),
          brightness: Brightness.dark,
        ),
      ),
      themeMode: ThemeMode.system,
      home: const Directionality(
        textDirection: TextDirection.rtl,
        child: TwinConnectHome(),
      ),
    );
  }
}

class TwinConnectHome extends StatefulWidget {
  const TwinConnectHome({super.key});

  @override
  State<TwinConnectHome> createState() => _TwinConnectHomeState();
}

class _TwinConnectHomeState extends State<TwinConnectHome> {
  final _formKey = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _subscription = TextEditingController();
  final _tenantCode = TextEditingController();

  bool _loading = false;
  String? _error;
  BrandPreview? _brand;

  @override
  void dispose() {
    _username.dispose();
    _subscription.dispose();
    _tenantCode.dispose();
    super.dispose();
  }

  Future<void> _identify() async {
    if (!_formKey.currentState!.validate() || _loading) return;
    FocusScope.of(context).unfocus();
    setState(() {
      _loading = true;
      _error = null;
      _brand = null;
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
      if (!mounted) return;
      setState(() => _brand = brand);
    } on FormatException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } on TenantApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'امکان دریافت اطلاعات پنل وجود ندارد.');
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final brand = _brand;
    return Scaffold(
      appBar: AppBar(
        title: const Text('TwinConnect'),
        actions: const [
          Tooltip(
            message: 'نسخه اولیه: بدون موتور اتصال VPN',
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: 18),
              child: Icon(Icons.shield_outlined),
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
                  'اپلیکیشن مرکزی چندبرندی',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 8),
                Text(
                  'برند و اطلاعات پشتیبانی مستقیماً از پنل دارای لایسنس شما دریافت می‌شود.',
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
                            'شناسایی حساب',
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                          const SizedBox(height: 18),
                          TextFormField(
                            key: const Key('accountUsername'),
                            controller: _username,
                            textDirection: TextDirection.ltr,
                            decoration: const InputDecoration(
                              labelText: 'نام کاربری کامل',
                              hintText: 'TP..._R..._ali',
                              border: OutlineInputBorder(),
                            ),
                            validator: (text) =>
                                (text == null || text.trim().isEmpty)
                                    ? 'نام کاربری لازم است.'
                                    : null,
                          ),
                          const SizedBox(height: 13),
                          TextFormField(
                            key: const Key('subscriptionLink'),
                            controller: _subscription,
                            textDirection: TextDirection.ltr,
                            decoration: const InputDecoration(
                              labelText: 'لینک یا کد اشتراک',
                              hintText: 'https://panel.example/v1/connect/...',
                              border: OutlineInputBorder(),
                            ),
                            validator: (text) =>
                                (text == null || text.trim().isEmpty)
                                    ? 'لینک اشتراک لازم است.'
                                    : null,
                          ),
                          const SizedBox(height: 13),
                          TextFormField(
                            key: const Key('tenantCode'),
                            controller: _tenantCode,
                            textDirection: TextDirection.ltr,
                            decoration: const InputDecoration(
                              labelText: 'شناسه پنل (در صورت نداشتن پیشوند)',
                              hintText: 'TP0123456789ABCDEF',
                              border: OutlineInputBorder(),
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
                            label: const Text('دریافت اطلاعات برند'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 12),
                  SelectableText(
                    _error!,
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ],
                if (brand != null) ...[
                  const SizedBox(height: 20),
                  BrandDetails(brand: brand),
                ],
                const SizedBox(height: 20),
                const Text(
                  'این نسخه فقط شناسایی پنل و نمایش برند را انجام می‌دهد. '
                  'اتصال واقعی VPN پس از تکمیل موتورهای بومی فعال خواهد شد.',
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
    int.parse('FF' + brand.primaryColor.substring(1), radix: 16),
  );

  @override
  Widget build(BuildContext context) {
    final isExpired = brand.accountStatus == 'expired';
    final status = isExpired
        ? 'اشتراک منقضی'
        : (brand.accountStatus == 'active'
              ? 'اشتراک فعال'
              : 'وضعیت: ' + brand.accountStatus);
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
              _CopyValue(label: 'پشتیبانی تلگرام', value: brand.telegramUrl),
              _CopyValue(label: 'لینک تمدید', value: brand.renewalUrl),
              _CopyValue(label: 'شماره تماس', value: brand.phone),
              _CopyValue(label: 'وب‌سایت', value: brand.websiteUrl),
              if (brand.supportText != null) ...[
                const SizedBox(height: 8),
                Text(brand.supportText!),
              ],
              const SizedBox(height: 16),
              const FilledButton.icon(
                onPressed: null,
                icon: Icon(Icons.power_settings_new),
                label: Text('اتصال VPN (در دست توسعه)'),
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
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          SizedBox(
            width: 115,
            child: Text(label, style: Theme.of(context).textTheme.bodyMedium),
          ),
          Expanded(
            child: SelectableText(text, textDirection: TextDirection.ltr),
          ),
          IconButton(
            tooltip: 'کپی ' + label,
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: text));
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(label + ' کپی شد.')),
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
