import 'package:flutter/material.dart';

import 'app_strings.dart';
import 'protocols.dart';

/// App protocol picker driven by the subscription snapshot from TwinPanel.
/// Unselected protocols stay absent, while engines still require native proof.
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
    final strings = AppStrings.of(context);
    final allowed = catalog.entries.where((entry) => entry.selected).toList();
    return Card(
      key: const Key('protocolCatalogCard'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(strings.protocolListTitle,
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            if (allowed.isEmpty)
              Text(strings.protocolNotSelected)
            else
              SizedBox(
                height: 44,
                child: ListView(
                  key: const Key('allowedProtocolFilters'),
                  scrollDirection: Axis.horizontal,
                  children: [
                    for (final entry in allowed)
                      Padding(
                        padding: const EdgeInsetsDirectional.only(end: 8),
                        child: Tooltip(
                          message: !entry.configRecordPresent
                              ? strings.protocolNotConfigured
                              : !native.supports(entry.protocol.code)
                                  ? strings.protocolEnginePending
                                  : strings.protocolEngineReady,
                          child: Chip(
                            key: Key('protocol_${entry.protocol.code}'),
                            label: Text(entry.protocol.name),
                            avatar: Icon(
                              entry.configRecordPresent
                                  ? Icons.hub_outlined
                                  : Icons.lock_outline_rounded,
                              size: 16,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
