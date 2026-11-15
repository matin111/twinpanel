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
        require(hasFullRoute(raw, "0.0.0.0/0")) { "IPV4_DEFAULT_ROUTE_MISSING" }
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
        validateStrictProfile(configText)
        require(!isInterfaceUp()) { "TUNNEL_ALREADY_RUNNING" }
        val bytes = configText.toByteArray(StandardCharsets.UTF_8)
        val config: Config
        try {
            config = Config.parse(ByteArrayInputStream(bytes))
        } finally {
            bytes.fill(0)
        }
        val actualState = backend!!.setState(tunnel, Tunnel.State.UP, config)
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

    @Synchronized
    fun status(): Map<String, Any> = mapOf(
        "protocol" to "wireguard",
        "state" to if (isInterfaceUp()) "interface_up" else "down",
        "peerHandshakeVerified" to false,
        "killSwitchEnforced" to isOsLockdownEnforced()
    )
}
