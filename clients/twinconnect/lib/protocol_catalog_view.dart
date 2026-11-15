import 'package:flutter/material.dart';

import 'app_strings.dart';
import 'protocol_strings.dart';
import 'protocols.dart';

/// Read-only status from the owning panel. Never represents a VPN connection.
class ProtocolCatalogCard extends StatelessWidget {
  const ProtocolCatalogCard({
    required this.catalog,
    this.native = const NativeProtocolReadiness(supportedCodes: {}),
    super.key,
  });

  final PanelProtocolCatalog catalog;
  final NativeProtocolReadiness native;

  @override
  Widget build(BuildContext context) {
    final s = AppStrings.of(context);
    return Card(
      key: const Key('protocolCatalogCard'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              s.protocolListTitle,
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            Text(s.protocolListSubtitle),
            const SizedBox(height: 12),
            for (final entry in catalog.entries)
              _ProtocolItem(entry: entry, native: native),
            const SizedBox(height: 10),
            Text(
              s.protocolPrivacy,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _ProtocolItem extends StatelessWidget {
  const _ProtocolItem({required this.entry, required this.native});

  final PanelProtocolStatus entry;
  final NativeProtocolReadiness native;

  @override
  Widget build(BuildContext context) {
    final s = AppStrings.of(context);
    final status = !entry.selected
        ? s.protocolNotSelected
        : !entry.configRecordPresent
            ? s.protocolNotConfigured
            : !native.supports(entry.protocol.code)
                ? s.protocolEnginePending
                : s.protocolEngineReady;
    return ListTile(
      key: Key('protocol_${entry.protocol.code}'),
      contentPadding: EdgeInsets.zero,
      leading: Icon(
        entry.selected ? Icons.tune : Icons.remove_circle_outline,
        size: 20,
      ),
      title: Text(entry.protocol.name),
      subtitle: Text(status),
      trailing: const Icon(Icons.lock_outline, size: 17),
    );
  }
}
