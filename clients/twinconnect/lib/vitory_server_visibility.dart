/// Pure Vitory plan server visibility policy. The caller must pass verified,
/// account-scoped profiles; an inventory assignment does NOT grant access.
class VitoryServerVisibility {
  const VitoryServerVisibility._();

  static bool shows({
    required String protocolFilter,
    required bool hasValidV2rayInbound,
    required bool hasValidHysteriaProfile,
  }) {
    return switch (protocolFilter) {
      'v2ray' => hasValidV2rayInbound,
      'hysteria2' => hasValidHysteriaProfile,
      'all' => hasValidV2rayInbound || hasValidHysteriaProfile,
      _ => false,
    };
  }
}
