import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:twinconnect/native_vpn_bridge.dart';
import 'package:twinconnect/vpn_policy.dart';
import 'package:twinconnect/vpn_policy_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('default policy is full tunnel, with DNS/IPv6 guard desired', () {
    const policy = VpnPolicy();
    expect(policy.routingMode, VpnRoutingMode.fullTunnel);
    expect(policy.dnsMode, VpnDnsMode.protected);
    expect(policy.ipv6Mode, VpnIpv6Mode.tunnelOrBlock);
    expect(policy.killSwitchRequested, false);
    expect(policy.draftProblems(VpnPlatform.android), isEmpty);
    expect(policy.connectionProblems(
      NativeVpnCapabilities.unavailable(VpnPlatform.android),
    ), contains('ENGINE_NOT_READY'));
  });

  test('only-selected-apps requires at least one selected app', () {
    const policy = VpnPolicy(
      routingMode: VpnRoutingMode.onlySelectedApps,
    );
    expect(
      policy.draftProblems(VpnPlatform.android),
      contains('NO_SELECTED_APPS'),
    );
    expect(
      policy.draftProblems(VpnPlatform.ios),
      contains('PER_APP_REQUIRES_MANAGED_OR_UNAVAILABLE'),
    );
  });

  test('include/exclude rules cannot be mixed into one routing mode', () {
    const include = VpnPolicy(
      routingMode: VpnRoutingMode.onlySelectedApps,
      appIds: ['org.telegram.messenger'],
    );
    const exclude = VpnPolicy(
      routingMode: VpnRoutingMode.excludeSelectedApps,
      appIds: ['org.telegram.messenger'],
    );
    expect(include.draftProblems(VpnPlatform.android), isEmpty);
    expect(exclude.draftProblems(VpnPlatform.android), isEmpty);
    expect(include.copyWith(routingMode: VpnRoutingMode.excludeSelectedApps)
        .routingMode, VpnRoutingMode.excludeSelectedApps);
    expect(
      const VpnPolicy(
        routingMode: VpnRoutingMode.onlySelectedApps,
        appIds: ['x', 'x'],
      ).draftProblems(VpnPlatform.android),
      contains('DUPLICATE_APPS'),
    );
  });

  test('strict kill switch refuses DNS/IPv6 bypass policies', () {
    const unsafe = VpnPolicy(
      killSwitchRequested: true,
      dnsMode: VpnDnsMode.system,
      ipv6Mode: VpnIpv6Mode.unprotected,
    );
    expect(
      unsafe.draftProblems(VpnPlatform.windows),
      containsAll([
        'STRICT_REQUIRES_PROTECTED_DNS',
        'STRICT_REQUIRES_IPV6_GUARD',
      ]),
    );
  });

  test('native capability contract rejects unknown or incomplete payload', () {
    final unsupported = NativeVpnCapabilities.fromNativeMap(
      VpnPlatform.android,
      {'engineReady': true, 'killSwitchEnforced': true},
    );
    expect(unsupported.engineReady, false);
    expect(unsupported.killSwitchEnforced, false);
    expect(
      const VpnPolicy(killSwitchRequested: true)
          .connectionProblems(unsupported),
      contains('KILL_SWITCH_NOT_ENFORCED'),
    );
  });

  test('Apple per-app settings stay locked on consumer iPhones', () {
    final forged = NativeVpnCapabilities.fromNativeMap(
      VpnPlatform.ios,
      {
        'contractVersion': 1,
        'engineReady': true,
        'includeApps': true,
        'excludeApps': true,
        'managedDevice': false,
      },
    );
    expect(forged.includeApps, false);
    expect(forged.excludeApps, false);

    final managed = NativeVpnCapabilities.fromNativeMap(
      VpnPlatform.ios,
      {
        'contractVersion': 1,
        'engineReady': true,
        'includeApps': true,
        'managedDevice': true,
      },
    );
    expect(managed.includeApps, true);
    const policy = VpnPolicy(
      routingMode: VpnRoutingMode.onlySelectedApps,
      appIds: ['com.example.managed'],
    );
    expect(
      policy.draftProblems(VpnPlatform.ios),
      contains('PER_APP_REQUIRES_MANAGED_OR_UNAVAILABLE'),
    );
    expect(
      policy.draftProblems(VpnPlatform.ios, managedDevice: true),
      isEmpty,
    );
  });

  test('kill-switch checkbox is not equivalent to enforcement', () {
    const policy = VpnPolicy(killSwitchRequested: true);
    const caps = NativeVpnCapabilities(
      platform: VpnPlatform.windows,
      engineReady: true,
      fullTunnel: true,
      dnsGuard: true,
      ipv6Guard: true,
      autoReconnect: true,
      killSwitchEnforced: false,
    );
    expect(
      policy.connectionProblems(caps),
      contains('KILL_SWITCH_NOT_ENFORCED'),
    );
    expect(
      () => NativeVpnBridge.requireSafeToConnect(policy, caps),
      throwsStateError,
    );
  });

  test('native confirmed protections can pass policy gate', () {
    const policy = VpnPolicy(killSwitchRequested: true);
    const caps = NativeVpnCapabilities(
      platform: VpnPlatform.android,
      engineReady: true,
      fullTunnel: true,
      dnsGuard: true,
      ipv6Guard: true,
      autoReconnect: true,
      killSwitchEnforced: true,
    );
    expect(policy.connectionProblems(caps), isEmpty);
    NativeVpnBridge.requireSafeToConnect(policy, caps);
  });

  test('JSON round trip rejects unknown or unsafe policy schema', () {
    const policy = VpnPolicy(
      routingMode: VpnRoutingMode.excludeSelectedApps,
      appIds: ['com.example.app'],
      killSwitchRequested: true,
      allowLan: true,
      autoConnect: true,
    );
    final restored = VpnPolicy.decode(policy.encode());
    expect(restored.routingMode, policy.routingMode);
    expect(restored.appIds, policy.appIds);
    expect(restored.killSwitchRequested, true);
    expect(restored.allowLan, true);
    expect(
      () => VpnPolicy.decode('{"schema":2}'),
      throwsFormatException,
    );
    expect(
      () => VpnPolicy.decode('{"schema":1,"routingMode":"unknown"}'),
      throwsFormatException,
    );
  });

  test('stored preference scope cannot expose username or tokens', () async {
    const store = VpnPolicyStore();
    const policy = VpnPolicy(
      killSwitchRequested: true,
      autoSelectServer: false,
    );
    expect(
      await store.save('TP0123456789ABCDEF', 'alice', policy),
      true,
    );
    final key = VpnPolicyStore.storageKey('TP0123456789ABCDEF', 'alice');
    expect(key, isNot(contains('alice')));
    expect(key, isNot(contains('TP0123456789ABCDEF')));
    final restored = await store.load('TP0123456789ABCDEF', 'alice');
    expect(restored.killSwitchRequested, true);
    expect(restored.autoSelectServer, false);
    final other = await store.load('TP0123456789ABCDEF', 'bob');
    expect(other.killSwitchRequested, false);
    final otherTenant = await store.load('TP0000000000000001', 'alice');
    expect(otherTenant.killSwitchRequested, false);
    await store.clear('TP0123456789ABCDEF', 'alice');
    expect(
      (await store.load('TP0123456789ABCDEF', 'alice'))
          .killSwitchRequested,
      false,
    );
  });

  test('missing native plugin never reports active VPN', () async {
    final actual = await NativeVpnBridge.probe();
    expect(actual.engineReady, false);
    expect(actual.killSwitchEnforced, false);
    expect(actual.fullTunnel, false);
  });
}
