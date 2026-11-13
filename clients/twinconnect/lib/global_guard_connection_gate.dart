import 'vpn_policy.dart';

/// Shared check for every Windows protocol entry point.
///
/// This does not install or enable the Windows Kill Switch. It prevents a
/// connection attempt from claiming requested protection without an explicit
/// dual-stack, recovery-verified native service acknowledgement.
class GlobalGuardConnectionGate {
  const GlobalGuardConnectionGate._();

  static bool verified(Map<String, dynamic> status) =>
      status['contractVersion'] == 1 &&
      status['serviceInstalled'] == true &&
      status['armed'] == true &&
      status['enforcedV4'] == true &&
      status['enforcedV6'] == true &&
      status['recoveryVerified'] == true;

  static void ensureCanConnect(
    VpnPolicy policy,
    Map<String, dynamic> status,
  ) {
    if (!policy.killSwitchRequested) return;
    if (!verified(status)) {
      throw const FormatException('GLOBAL_KILL_SWITCH_NOT_VERIFIED');
    }
  }
}
