import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Mieru PacketTunnel owns a scoped profile and fails if egress pin absent', () {
    final engine = File(
      'macos_native/mieru/TwinConnectMacMieruTunnelEngine.swift',
    ).readAsStringSync();
    final provider = File(
      'macos_native/PacketTunnelProvider.swift',
    ).readAsStringSync();
    final installer = File(
      'macos_native/install_packet_tunnel_target.rb',
    ).readAsStringSync();
    final bridge = File(
      'macos_native/TwinConnectMacOSVPNBridge.swift',
    ).readAsStringSync();

    expect(installer,
        contains('mieru/TwinConnectMacMieruTunnelEngine.swift'));
    expect(provider, contains('case "mieru":'));
    expect(provider, contains('TwinConnectMacMieruTunnelEngine(tunnel: self)'));
    expect(provider, contains('if let engine = mieru'));
    expect(engine, contains('kSecValuePersistentRef'));
    expect(engine, contains('kSecReturnData'));
    expect(engine, contains('Set(object.keys) == Set(["core", "relay"])'));
    expect(engine, contains('core["rpcPort"] as? Int == 0'));
    expect(engine, contains('core["socks5ListenLAN"] as? Bool == false'));
    expect(engine, contains('outbounds[0]["server"] as? String == "127.0.0.1"'));
    expect(engine, contains('outbounds[0]["server_port"] as? Int == socksPort'));
    final planner = File(
      'macos_native/mieru/TwinConnectMacMieruEndpointRoute.swift',
    ).readAsStringSync();
    expect(installer, contains('mieru/TwinConnectMacMieruEndpointRoute.swift'));
    expect(engine, contains('TwinConnectMacMieruEndpointRoute.plan('));
    expect(engine, contains('MACOS_MIERU_ENDPOINT_ROUTE_INVALID'));
    expect(planner, contains('static func tunnelSettings(for plan: Plan)'));
    expect(planner, contains('ipv4.excludedRoutes = [plan.excludedRoute]'));
    expect(planner, contains('ipv6.includedRoutes = [NEIPv6Route.default()]'));
    expect(planner, contains('dns.matchDomains = [""]'));
    expect(engine, contains('.tunnelSettings(for: routePlan)'));
    expect(engine, contains('MACOS_MIERU_NETWORK_POLICY_INVALID'));
    expect(planner, contains('NEIPv4Route('));
    expect(planner, contains('subnetMask: "255.255.255.255"'));
    expect(planner, contains('server["domainName"] as? String == ""'));
    expect(planner, contains('endpointNotPublic'));
    expect(File('macos_native/mieru/tests/main.swift').existsSync(), isTrue);
    expect(engine, contains('MACOS_MIERU_EGRESS_ROUTE_PIN_NOT_IMPLEMENTED'));
    expect(engine, contains('self?.core?.stop()'));
    expect(bridge, contains('"packetFlowBridgeReady": false'));
    expect(bridge, contains('"engineReady": false'));
  });
}
