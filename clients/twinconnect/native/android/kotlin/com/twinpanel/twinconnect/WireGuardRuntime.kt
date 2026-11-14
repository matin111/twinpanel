package com.twinpanel.twinconnect

import android.content.Context
import android.net.VpnService
import com.wireguard.android.backend.GoBackend
import com.wireguard.android.backend.Tunnel
import com.wireguard.config.Config
import java.io.ByteArrayInputStream
import java.nio.charset.StandardCharsets

/**
 * Process-local WireGuard engine. Not an OpenConnect engine.
 *
 * The only state advertised as "up" is a WireGuard TUN interface reported
 * by the native library; peer handshake and end-to-end reachability require
 * separately observed statistics before claiming internet connectivity.
 */
internal object WireGuardRuntime {
    private var backend: GoBackend? = null

    private val tunnel = object : Tunnel {
        override fun getName(): String = "twinconnect"
        override fun onStateChange(newState: Tunnel.State) {
            // Never record sensitive WireGuard configuration in logs.
        }
    }

    @Synchronized
    fun initialize(context: Context): Boolean {
        if (backend != null) return true
        return try {
            backend = GoBackend(context.applicationContext)
            true
        } catch (_: Exception) {
            false
        } catch (_: LinkageError) {
            false
        }
    }

    @Synchronized
    fun isInterfaceUp(): Boolean {
        return try {
            backend?.getState(tunnel) == Tunnel.State.UP
        } catch (_: Exception) {
            false
        }
    }

    @Synchronized
    fun isOsLockdownEnforced(): Boolean {
        return try {
            backend?.isLockdownEnabled == true
        } catch (_: Exception) {
            false
        }
    }

    private fun hasSetting(raw: String, name: String): Boolean =
        Regex("(?im)^\\s*" + Regex.escape(name) + "\\s*=\\s*\\S+").containsMatchIn(raw)

    private fun hasFullRoute(raw: String, route: String): Boolean {
        return Regex("(?im)^\\s*AllowedIPs\\s*=\\s*(.*)$")
            .findAll(raw)
            .flatMap { it.groupValues[1].split(',').asSequence() }
            .any { it.trim().equals(route, ignoreCase = true) }
    }

    // TwinPanel deliberately emits two /1 routes, which together provide
    // the same IPv4 coverage as 0.0.0.0/0. Both forms must be accepted.
    private fun hasFullIpv4Route(raw: String): Boolean =
        hasFullRoute(raw, "0.0.0.0/0") ||
        (hasFullRoute(raw, "0.0.0.0/1") &&
         hasFullRoute(raw, "128.0.0.0/1"))

    /**
     * Route all IPv6 traffic into the Android VPN rather than allowing
     * an IPv6-only device to bypass the tunnel. Existing TwinPanel clients
     * may lack ::/0. This adds only a protective client-side route for
     * an unambiguous, single-peer FULL-IPv4-tunnel profile.
     *
     * It does not invent IPv6 connectivity at the server: if that server
     * cannot carry IPv6, IPv6 traffic will fail closed inside the VPN.
     * The incoming profile is not persisted or logged.
     */
    private fun protectIpv6Route(raw: String): String {
        if (hasFullRoute(raw, "::/0")) return raw
        require(hasFullIpv4Route(raw)) { "IPV4_DEFAULT_ROUTE_MISSING" }
        require(Regex("(?im)^\\s*\\[Peer\\]\\s*$").findAll(raw).count() == 1) {
            "IPV6_DEFAULT_ROUTE_MISSING"
        }
        val allowed = Regex("(?im)^(\\s*AllowedIPs\\s*=\\s*)([^\\r\\n]+)$")
            .findAll(raw).toList()
        require(allowed.size == 1) { "IPV6_DEFAULT_ROUTE_MISSING" }
        val match = allowed.single()
        val replacement = match.groupValues[1] +
            match.groupValues[2].trimEnd() + ", ::/0"
        return raw.replaceRange(match.range, replacement)
    }

    /**
     * Strict initial full-tunnel profile guard. GoBackend reads DNS and routes
     * from the actual profile, not Flutter UI. Never silently accept IPv4-only
     * profiles: they can leak IPv6 outside the VPN.
     */
    private fun validateStrictProfile(raw: String) {
        require(raw.length in 100..200_000) { "PROFILE_INVALID" }
        require(raw.contains("[Interface]") && raw.contains("[Peer]")) {
            "PROFILE_INVALID"
        }
        require(hasSetting(raw, "PrivateKey")) { "PRIVATE_KEY_MISSING" }
        require(hasSetting(raw, "DNS")) { "VPN_DNS_MISSING" }
        require(hasSetting(raw, "Address")) { "VPN_ADDRESS_MISSING" }
        require(hasFullIpv4Route(raw)) { "IPV4_DEFAULT_ROUTE_MISSING" }
        require(hasFullRoute(raw, "::/0")) { "IPV6_DEFAULT_ROUTE_MISSING" }
        // A future native engine will additionally verify physical IPv6 egress,
        // DNS behavior and peer handshake on an instrumented Android device.
    }

    @Synchronized
    fun start(context: Context, configText: String, policy: Map<String, Any?>): Map<String, Any> {
        require(initialize(context)) { "WIREGUARD_ENGINE_UNAVAILABLE" }
        require(VpnService.prepare(context) == null) { "VPN_PERMISSION_REQUIRED" }
        require(policy["routingMode"] == "fullTunnel") { "PER_APP_ROUTING_NOT_IMPLEMENTED" }
        require(policy["dnsMode"] == "protected") { "DNS_POLICY_NOT_SUPPORTED" }
        require(policy["ipv6Mode"] == "tunnelOrBlock") { "IPV6_POLICY_NOT_SUPPORTED" }
        require(policy["allowLan"] != true) { "LAN_BYPASS_NOT_IMPLEMENTED" }
        require(policy["autoConnect"] != true) { "AUTOCONNECT_NOT_IMPLEMENTED" }
        require(policy["autoReconnect"] != true) { "AUTO_RECONNECT_NOT_VERIFIED" }
        if (policy["killSwitchRequested"] == true) {
            require(isOsLockdownEnforced()) { "OS_LOCKDOWN_NOT_ENABLED" }
        }
        val protectedProfile = protectIpv6Route(configText)
        validateStrictProfile(protectedProfile)
        require(!isInterfaceUp()) { "TUNNEL_ALREADY_RUNNING" }
        val bytes = protectedProfile.toByteArray(StandardCharsets.UTF_8)
        val config: Config
        try {
            config = try {
                Config.parse(ByteArrayInputStream(bytes))
            } catch (_: Exception) {
                // Avoid surfacing parser details that may contain credentials.
                throw IllegalArgumentException("WIREGUARD_CONFIG_PARSE_FAILED")
            }
        } finally {
            bytes.fill(0)
        }
        val actualState = try {
            backend!!.setState(tunnel, Tunnel.State.UP, config)
        } catch (_: Exception) {
            throw IllegalArgumentException("WIREGUARD_NATIVE_START_FAILED")
        }
        require(actualState == Tunnel.State.UP && isInterfaceUp()) {
            "TUNNEL_NOT_ESTABLISHED"
        }
        return mapOf(
            "state" to "interface_up",
            "protocol" to "wireguard",
            "peerHandshakeVerified" to false,
            "killSwitchEnforced" to isOsLockdownEnforced()
        )
    }

    @Synchronized
    fun stop(): Map<String, Any> {
        val existing = backend
        if (existing == null || !isInterfaceUp()) {
            return mapOf("state" to "down", "protocol" to "wireguard")
        }
        existing.setState(tunnel, Tunnel.State.DOWN, null)
        return mapOf("state" to "down", "protocol" to "wireguard")
    }

    /**
     * WireGuard JNI counters are cumulative bytes for THIS tunnel, not global
     * Android traffic or subscription accounting. Never expose peer keys.
     * A recent handshake establishes peer contact, not internet reachability.
     */
    @Synchronized
    fun status(): Map<String, Any> {
        val up = isInterfaceUp()
        var rx: Long? = null
        var tx: Long? = null
        var latestHandshake: Long? = null
        if (up) {
            try {
                val statistics = backend!!.getStatistics(tunnel)
                rx = statistics.totalRx()
                tx = statistics.totalTx()
                val timestamps = statistics.peers().mapNotNull {
                    statistics.peer(it)?.latestHandshakeEpochMillis()
                }.filter { it > 0L }
                latestHandshake = timestamps.maxOrNull()
            } catch (_: Exception) {
                // Interface may be up while counters cannot be read.
            }
        }
        val now = System.currentTimeMillis()
        val freshHandshake = latestHandshake != null &&
            latestHandshake <= now + 10_000L &&
            now - latestHandshake < 180_000L
        val result = mutableMapOf<String, Any>(
            "protocol" to "wireguard",
            "state" to if (up) "interface_up" else "down",
            "peerHandshakeVerified" to freshHandshake,
            "killSwitchEnforced" to isOsLockdownEnforced()
        )
        if (rx != null) result["rxBytes"] = rx
        if (tx != null) result["txBytes"] = tx
        if (latestHandshake != null) {
            result["latestHandshakeEpochMillis"] = latestHandshake
        }
        return result
    }
}
