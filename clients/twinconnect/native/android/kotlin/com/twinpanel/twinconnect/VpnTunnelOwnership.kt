package com.twinpanel.twinconnect

import android.net.ConnectivityManager
import android.net.NetworkCapabilities

/**
 * Single authority for VPN ownership decisions. A second VpnService is never
 * started as a "kill switch" while a protocol tunnel owns Android's VPN slot.
 *
 * This coordinator is deliberately NOT a packet firewall. Protection must be
 * enforced by the active TUN owner (or Android lockdown), not by a UI toggle.
 */
internal object VpnTunnelOwnership {
    enum class Owner { NONE, LEGACY_GUARD, PROTOCOL, UNKNOWN }

    data class Snapshot(
        val owner: Owner,
        val legacyGuard: Boolean,
        val vpnTransport: Boolean,
        val lockdownVerified: Boolean
    ) {
        val trafficProtected: Boolean
            get() = lockdownVerified
        val canStartSeparateGuard: Boolean
            get() = false // No unsafe second-VpnService takeover/handoff.
        val requiresNativePacketGuard: Boolean
            get() = !lockdownVerified
    }

    fun snapshot(
        manager: ConnectivityManager,
        legacyGuardActive: Boolean,
        wireGuardUp: Boolean,
        wireGuardLockdown: Boolean?
    ): Snapshot {
        val vpnUp = try {
            manager.allNetworks.any { network ->
                manager.getNetworkCapabilities(network)
                    ?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true
            }
        } catch (_: SecurityException) {
            // Unknown must never be interpreted as safe to replace the VPN.
            return Snapshot(Owner.UNKNOWN, legacyGuardActive, true, false)
        }
        val owner = when {
            legacyGuardActive -> Owner.LEGACY_GUARD
            vpnUp || wireGuardUp -> Owner.PROTOCOL
            else -> Owner.NONE
        }
        return Snapshot(
            owner,
            legacyGuardActive,
            vpnUp || wireGuardUp,
            wireGuardUp && wireGuardLockdown == true
        )
    }
}
