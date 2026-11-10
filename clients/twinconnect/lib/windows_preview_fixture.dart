import 'protocols.dart';
import 'tenant_models.dart';

/// Fictitious data for the offline Windows preview only.
///
/// Never generates an authenticated session or unlocks a VPN engine.
class WindowsPreviewFixture {
  static const namespace = 'TP0123456789ABCDEF';

  static BrandPreview brand() => BrandPreview.fromJson({
        'namespace': namespace,
        'brand_name': 'TwinConnect Demo',
        'owner_type': 'reseller',
        'account_status': 'active',
        'app_username_prefix': namespace + '_R1_',
        'support_phone': '+00 000 000 0000',
        'telegram_url': null,
        'renewal_url': 'https://demo.example.org/renew',
        'website_url': 'https://demo.example.org/',
        'support_text': 'Sample data / اطلاعات نمایشی',
        'primary_color': '#7358DF',
        'secondary_color': '#312E81',
      });

  static PanelProtocolCatalog protocolCatalog() =>
      PanelProtocolCatalog.fromJson({
        'schema': 1,
        'namespace': namespace,
        'protocols': [
          for (final p in VpnProtocols.all)
            {
              'code': p.code,
              'title': p.name,
              'engine_family': p.engine.name,
              // An illustrative mix while retaining all 16 protocols.
              'selected': true,
              'config_record_present': p.code == 'wireguard' ||
                  p.code == 'cisco' ||
                  p.code == 'v2ray',
              'client_engine_ready': false,
            }
        ],
      });
}
