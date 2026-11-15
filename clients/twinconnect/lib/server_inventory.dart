import 'dart:io' show InternetAddress;

/// Read-only server inventory, returned by the subscription's own panel.
/// Node health is NOT the same as an established VPN tunnel or ping.
class AppServer {
  const AppServer({
    required this.id,
    required this.name,
    required this.countryCode,
    required this.nodeOnline,
    required this.latencyMs,
    this.probeIp,
    this.probePorts = const <String, int>{},
  });

  final String id;
  final String name;
  final String countryCode;
  final bool nodeOnline;
  final int? latencyMs;
  final String? probeIp;
  /// Protocol-specific, confirmed public TCP listener ports for optional RTT.
  final Map<String, int> probePorts;

  factory AppServer.fromJson(Map<String, dynamic> data) {
    final id = data['id'];
    final name = data['name'];
    final country = data['country_code'];
    final online = data['node_online'];
    final latency = data['latency_ms'];
    final rawProbe = data['probe_ip'];
    final rawPorts = data['probe_ports'];
    final probePorts = <String, int>{};
    if (rawPorts is Map) {
      for (final entry in rawPorts.entries) {
        if (entry.key is String && entry.value is int &&
            RegExp(r'^[a-z0-9_]{2,32}
    final probeIp = parsedProbe != null && !parsedProbe.isLoopback &&
        !parsedProbe.isLinkLocal && !parsedProbe.isMulticast
        ? rawProbe as String : null;
    if (id is! String || !RegExp(r'^[0-9]{1,20}$').hasMatch(id) ||
        name is! String || name.trim().isEmpty || name.length > 120 ||
        country is! String || country.length > 8 || country.isEmpty ||
        online is! bool ||
        (latency != null && (latency is! int || latency < 1 || latency > 60000))) {
      throw const FormatException('INVALID_SERVER_INVENTORY');
    }
    return AppServer(
      id: id, name: name, countryCode: country,
      nodeOnline: online, latencyMs: latency, probeIp: probeIp,
      probePorts: Map.unmodifiable(probePorts),
    );
  }
}

class AppServerInventory {
  const AppServerInventory({required this.namespace, required this.servers});
  final String namespace;
  final List<AppServer> servers;

  factory AppServerInventory.fromJson(Map<String, dynamic> json) {
    if (json['schema'] != 1 || json['namespace'] is! String ||
        json['servers'] is! List) {
      throw const FormatException('INVALID_SERVER_INVENTORY');
    }
    final data = json['servers'] as List;
    if (data.length > 500) {
      throw const FormatException('INVALID_SERVER_INVENTORY');
    }
    final result = <AppServer>[];
    final seen = <String>{};
    for (final row in data) {
      if (row is! Map<String, dynamic>) {
        throw const FormatException('INVALID_SERVER_INVENTORY');
      }
      final server = AppServer.fromJson(row);
      if (!seen.add(server.id)) {
        throw const FormatException('DUPLICATE_SERVER');
      }
      result.add(server);
    }
    return AppServerInventory(
      namespace: (json['namespace'] as String).toUpperCase(),
      servers: List.unmodifiable(result),
    );
  }
}
).hasMatch(entry.key as String) &&
            (entry.value as int) >= 1 && (entry.value as int) <= 65535) {
          probePorts[entry.key as String] = entry.value as int;
        }
      }
    }
    final parsedProbe = rawProbe is String ? InternetAddress.tryParse(rawProbe) : null;
    final probeIp = parsedProbe != null && !parsedProbe.isLoopback &&
        !parsedProbe.isLinkLocal && !parsedProbe.isMulticast
        ? rawProbe as String : null;
    if (id is! String || !RegExp(r'^[0-9]{1,20}$').hasMatch(id) ||
        name is! String || name.trim().isEmpty || name.length > 120 ||
        country is! String || country.length > 8 || country.isEmpty ||
        online is! bool ||
        (latency != null && (latency is! int || latency < 1 || latency > 60000))) {
      throw const FormatException('INVALID_SERVER_INVENTORY');
    }
    return AppServer(
      id: id, name: name, countryCode: country,
      nodeOnline: online, latencyMs: latency, probeIp: probeIp,
    );
  }
}

class AppServerInventory {
  const AppServerInventory({required this.namespace, required this.servers});
  final String namespace;
  final List<AppServer> servers;

  factory AppServerInventory.fromJson(Map<String, dynamic> json) {
    if (json['schema'] != 1 || json['namespace'] is! String ||
        json['servers'] is! List) {
      throw const FormatException('INVALID_SERVER_INVENTORY');
    }
    final data = json['servers'] as List;
    if (data.length > 500) {
      throw const FormatException('INVALID_SERVER_INVENTORY');
    }
    final result = <AppServer>[];
    final seen = <String>{};
    for (final row in data) {
      if (row is! Map<String, dynamic>) {
        throw const FormatException('INVALID_SERVER_INVENTORY');
      }
      final server = AppServer.fromJson(row);
      if (!seen.add(server.id)) {
        throw const FormatException('DUPLICATE_SERVER');
      }
      result.add(server);
    }
    return AppServerInventory(
      namespace: (json['namespace'] as String).toUpperCase(),
      servers: List.unmodifiable(result),
    );
  }
}
