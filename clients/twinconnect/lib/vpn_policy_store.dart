import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'vpn_policy.dart';

/// Local *non-secret* desired policy, isolated per tenant/account.
///
/// Never persist subscription tokens, passwords, configuration URLs, private
/// keys or traffic logs in preferences. A saved policy is not a live tunnel.
class VpnPolicyStore {
  const VpnPolicyStore();

  static String storageKey(String tenant, String account) {
    final scope = '${tenant.trim().toUpperCase()}:${account.trim()}';
    final digest = sha256.convert(utf8.encode('twinconnect:policy:v1:$scope'));
    return 'twinconnect_vpn_policy_v1_$digest';
  }

  Future<VpnPolicy> load(String tenant, String account) async {
    try {
      final preferences = await SharedPreferences.getInstance();
      final raw = preferences.getString(storageKey(tenant, account));
      if (raw == null) return const VpnPolicy();
      return VpnPolicy.decode(raw);
    } catch (_) {
      // Tampered, legacy, or corrupt preferences never activate protection.
      return const VpnPolicy();
    }
  }

  Future<bool> save(
    String tenant,
    String account,
    VpnPolicy policy,
  ) async {
    final preferences = await SharedPreferences.getInstance();
    return preferences.setString(
      storageKey(tenant, account),
      policy.encode(),
    );
  }

  Future<bool> clear(String tenant, String account) async {
    final preferences = await SharedPreferences.getInstance();
    return preferences.remove(storageKey(tenant, account));
  }
}
