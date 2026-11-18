import 'dart:async' show Future;
import 'dart:io' show InternetAddress, InternetAddressType;

import 'protocols.dart';
import 'server_inventory.dart';

/// Use only the public IP supplied by the owning authenticated panel, and
/// only for the already authorized WireGuard peer. WireGuard authenticates the
/// peer public key, so changing the transport destination does not change
/// cryptographic identity. TLS-based protocols must not use this helper.
class EmergencyWireGuardEndpoint {
  const EmergencyWireGuardEndpoint._();

  static final _endpoint = RegExp(
    r'^([ \t]*Endpoint[ \t]*=[ \t]*)([a-zA-Z0-9][a-zA-Z0-9.-]*)(:[0-9]{1,5})([ \t]*\r?)$',
    multiLine: true,
  );

  static Future<ClientProtocolProfiles> useDirectIpOnDnsFailure({
    required ClientProtocolProfiles profiles,
    required AppServer server,
    Future<List<InternetAddress>> Function(String host)? lookup,
  }) async {
    if (profiles.protocol.code != 'wireguard' || server.probeIp == null) {
      return profiles;
    }
    final directIp = InternetAddress.tryParse(server.probeIp!);
    if (directIp == null || directIp.isLoopback ||
        directIp.isLinkLocal || directIp.isMulticast) return profiles;

    if (profiles.items.length != 1 ||
        profiles.items.single['node_id'].toString() != server.id ||
        profiles.items.single['config'] is! String) return profiles;
    final original = profiles.items.single['config'] as String;
    final matches = _endpoint.allMatches(original).toList(growable: false);
    if (matches.length != 1) return profiles;
    final match = matches.single;
    final hostname = match.group(2)!;
    if (InternetAddress.tryParse(hostname) != null || !hostname.contains('.')) {
      return profiles;
    }
    final port = int.tryParse(match.group(3)!.substring(1));
    if (port == null || port == 0 || port > 65535) return profiles;

    try {
      final answers = await (lookup ?? InternetAddress.lookup)(hostname)
          .timeout(const Duration(seconds: 2));
      if (answers.isNotEmpty) return profiles;
    } catch (_) {
      // DNS is unavailable, but the last panel-confirmed public IP may work.
    }
    final target = directIp.type == InternetAddressType.IPv6
        ? '[' + directIp.address + ']' : directIp.address;
    final replacement = match.group(1)! + target +
        match.group(3)! + match.group(4)!;
    final changed = original.replaceRange(match.start, match.end, replacement);
    return ClientProtocolProfiles(
      namespace: profiles.namespace,
      protocol: profiles.protocol,
      items: [
        {...profiles.items.single, 'config': changed},
      ],
    );
  }
}
