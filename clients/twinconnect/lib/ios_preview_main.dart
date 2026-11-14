import 'package:flutter/material.dart';

import 'account_snapshot.dart';
import 'ios_home_shell.dart';
import 'plan_classification.dart';
import 'protocols.dart';
import 'server_inventory.dart';
import 'tenant_models.dart';

/// Unauthenticated, offline-only iPhone simulator tour.
///
/// This is NOT part of the real app's main.dart entry point, and cannot be
/// reached by an end user without compiling this explicit alternate target.
/// Fixtures are fictitious, contain no real customer secrets or endpoints,
/// and may never be used to authorize a VPN tunnel.
void main() => runApp(const TwinConnectIphonePreview());

class TwinConnectIphonePreview extends StatelessWidget {
  const TwinConnectIphonePreview({super.key});

  static const _tenant = 'TPABC123';
  static const _brand = BrandPreview(
    namespace: _tenant,
    brandName: 'Matin VPN',
    ownerType: 'owner',
    accountStatus: 'active',
    appUsernamePrefix: 'DEMO',
    primaryColor: '#49A7BB',
    secondaryColor: '#6BD9CA',
    buttonColor: '#3EA7B9',
    backgroundColor: '#102A37',
    surfaceColor: '#204755',
  );
  static const _nodes = AppServerInventory(namespace: _tenant, servers: [
    AppServer(id: '1', name: 'Turkey — Istanbul 01',
      countryCode: 'TR', nodeOnline: true, latencyMs: 78),
    AppServer(id: '2', name: 'Turkey — Istanbul 02',
      countryCode: 'TR', nodeOnline: true, latencyMs: 95),
    AppServer(id: '3', name: 'Germany — Frankfurt 01',
      countryCode: 'DE', nodeOnline: true, latencyMs: 116),
    AppServer(id: '4', name: 'Germany — Frankfurt 02',
      countryCode: 'DE', nodeOnline: true, latencyMs: 128),
    AppServer(id: '5', name: 'United States — New York',
      countryCode: 'US', nodeOnline: true, latencyMs: 204),
    AppServer(id: '6', name: 'United Kingdom — London',
      countryCode: 'GB', nodeOnline: true, latencyMs: 141),
    AppServer(id: '7', name: 'Finland — Helsinki',
      countryCode: 'FI', nodeOnline: true, latencyMs: 163),
  ]);
  static final _catalog = PanelProtocolCatalog(
    namespace: _tenant,
    entries: [
      for (final definition in VpnProtocols.all)
        PanelProtocolStatus(protocol: definition,
          selected: true, configRecordPresent: true,
          clientEngineReady: false),
    ],
  );
  static final _account = AppAccountSnapshot(
    namespace: _tenant,
    trafficLimitBytes: 50 * 1024 * 1024 * 1024,
    trafficUsedBytes: 14 * 1024 * 1024 * 1024,
    expiresAt: DateTime.utc(2027, 1, 1),
    activationDurationDays: 30,
    status: 'demo',
  );
  static const _plan = AppPlanClassification(
    namespace: _tenant,
    planId: 1,
    subscriptionType: 'ویژه — نمونه',
    userCountCategory: '۱ کاربر',
    deviceLimit: 2,
  );

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'TwinConnect iOS — UI Preview',
    debugShowCheckedModeBanner: false,
    theme: ThemeData.dark(useMaterial3: true).copyWith(
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xFF69D2DC),
        brightness: Brightness.dark)),
    home: TwinConnectIphoneShell(
      brand: _brand,
      username: 'demo_user',
      inventory: _nodes,
      catalog: _catalog,
      account: _account,
      plan: _plan,
      previewMode: true,
      autoTour: true,
    ),
  );
}
