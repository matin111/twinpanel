import 'dart:io';

import 'package:flutter/material.dart';

import 'macos_standalone_panel_profile.dart';
import 'macos_standalone_proxy_runtime.dart';
import 'protocols.dart';
import 'server_inventory.dart';
import 'tenant_api.dart';
import 'tenant_models.dart';

/// Unsigned macOS development mode: a one-shot proxied request, NOT a VPN.
/// Never uses the stale UI catalog to authorize access to client secrets.
class MacStandaloneConnectionCard extends StatefulWidget {
  const MacStandaloneConnectionCard({
    super.key,
    required this.panel,
    required this.sessionToken,
    required this.catalog,
    required this.servers,
  });

  final PanelDirectoryEntry panel;
  final String sessionToken;
  final PanelProtocolCatalog catalog;
  final AppServerInventory servers;

  @override
  State<MacStandaloneConnectionCard> createState() =>
      _MacStandaloneConnectionCardState();
}

class _MacStandaloneConnectionCardState
    extends State<MacStandaloneConnectionCard> {
  String? _protocol;
  String? _serverId;
  bool _running = false;
  String? _message;
  String? _testedIp;

  @override
  Widget build(BuildContext context) {
    final availableProtocols = widget.catalog.entries.where((entry) =>
      entry.selected &&
      entry.configRecordPresent &&
      MacStandalonePanelProfile.supportedCodes.contains(entry.protocol.code)
    ).toList(growable: false);
    final chosenProtocol = availableProtocols.any(
      (entry) => entry.protocol.code == _protocol,
    ) ? _protocol : null;
    final chosenServer = widget.servers.servers.any(
      (server) => server.id == _serverId,
    ) ? _serverId : null;
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('macOS local proxy test', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            const Text(
              'Tests an HTTPS request through a selected subscription server. '
              'This does not enable system VPN, Kill Switch, or protected DNS.',
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              initialValue: chosenProtocol,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Protocol'),
              items: [
                for (final entry in availableProtocols)
                  DropdownMenuItem<String>(
                    value: entry.protocol.code,
                    child: Text(entry.protocol.code),
                  ),
              ],
              onChanged: _running ? null : (value) {
                setState(() { _protocol = value; _message = null; });
              },
            ),
            const SizedBox(height: 10),
            DropdownButtonFormField<String>(
              initialValue: chosenServer,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Subscription server'),
              items: [
                for (final server in widget.servers.servers)
                  DropdownMenuItem<String>(
                    value: server.id,
                    child: Text('${server.name} (${server.countryCode})',
                        overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: _running ? null : (value) {
                setState(() { _serverId = value; _message = null; });
              },
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              icon: const Icon(Icons.network_check),
              label: Text(_running ? 'Testing proxy…' : 'Test selected server'),
              onPressed: _running || chosenProtocol == null ||
                      chosenServer == null
                  ? null
                  : () => _runTest(chosenProtocol, chosenServer),
            ),
            if (_testedIp != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: SelectableText('Proxied HTTPS exit IP: $_testedIp'),
              ),
            if (_message != null)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text(_message!, style: theme.textTheme.bodySmall),
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _runTest(String code, String serverId) async {
    if (!Platform.isMacOS || _running) return;
    setState(() {
      _running = true;
      _testedIp = null;
      _message = 'Checking current subscription permissions…';
    });
    try {
      // Development binaries installed by install_standalone_engines.sh.
      // A sandboxed/released app may not be allowed to spawn processes;
      // errors must be displayed instead of claiming a connection.
      final home = Platform.environment['HOME'];
      if (home == null || home.isEmpty) {
        throw const FormatException('MAC_STANDALONE_HOME_UNAVAILABLE');
      }
      final engineRoot = Directory(
          '$home/twinpanel/clients/twinconnect/macos_native/build');
      final arch = Platform.version.contains('arm64') ? 'arm64' :
          'amd64'; // Runtime detects architecture again on launch.
      final executableName = code == 'v2ray' ? 'xray' : 'sing-box';
      final group = executableName == 'xray' ? 'xray' : 'singbox';
      final executable = File(
          '${engineRoot.path}/$group/$arch/$executableName');
      // Check actual Intel binary here; the runtime does the definitive check.
      final found = executable.existsSync() ||
          File('${engineRoot.path}/$group/arm64/$executableName').existsSync();
      if (!found) {
        throw const FormatException('MAC_STANDALONE_ENGINE_NOT_INSTALLED');
      }
      final candidate = await MacStandalonePanelProfile(
        api: TenantApi.fromBuildConfig(),
      ).prepare(
        panel: widget.panel,
        sessionToken: widget.sessionToken,
        serverId: serverId,
        protocolCode: code,
        engineInstalled: found,
        localPort: 17089,
      );
      if (!mounted) return;
      setState(() => _message = 'Checking real proxy traffic…');
      final result = await MacStandaloneProxyRuntime(
        engineRoot: engineRoot,
      ).probe(candidate);
      if (!mounted) return;
      setState(() {
        _testedIp = result.egressIp;
        _message = 'Proxy traffic verified; system VPN is not active.';
      });
    } catch (error) {
      if (!mounted) return;
      // Do not print sensitive exceptions from a backend or credentials.
      final code = error is FormatException
          ? error.message : 'MAC_STANDALONE_TEST_FAILED';
      setState(() => _message = 'Test failed: $code');
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }
}
