package com.twinpanel.twinconnect

import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.os.Build
import com.wireguard.android.backend.GoBackend
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
    private var libraryLoaded = false
    private val lifecycleGate = TunPacketGate()

    @Synchronized
    fun initialize(context: Context): Boolean {
        if (libraryLoaded) return true
        return try {
            // Loads libwg-go; we intentionally never call GoBackend.setState,
            // since that starts its own VpnService and steals the VPN slot.
            GoBackend(context.applicationContext)
            libraryLoaded = true
            true
        } catch (_: Exception) {
            false
        } catch (_: LinkageError) {
            false
        }
    }

    @Synchronized
    fun isInterfaceUp(): Boolean {
        return SharedTunVpnService.active?.hasWireGuardTunnel() == true
    }

    @Synchronized
    fun isOsLockdownEnforced(): Boolean {
        return SharedTunVpnService.active?.isLockdownVerified() == true
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
        // In-app Kill Switch is implemented by retaining the SAME TUN when
        // the WireGuard transport stops, without OS settings navigation.
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
        lifecycleGate.beginConnect("wireguard")
        val service = try {
            val intent = Intent(context, SharedTunVpnService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
            var ready: SharedTunVpnService? = null
            for (attempt in 0 until 100) {
                ready = SharedTunVpnService.active
                if (ready != null) break
                Thread.sleep(50)
            }
            ready ?: throw IllegalStateException("SHARED_TUN_NOT_READY")
        } catch (_: Exception) {
            lifecycleGate.lostConnection()
            throw IllegalArgumentException("SHARED_TUN_NOT_READY")
        }
        try {
            service.startWireGuard(config, policy["killSwitchRequested"] == true)
        } catch (_: Exception) {
            lifecycleGate.lostConnection()
            throw IllegalArgumentException("WIREGUARD_NATIVE_START_FAILED")
        } catch (_: LinkageError) {
            lifecycleGate.lostConnection()
            throw IllegalArgumentException("WIREGUARD_NATIVE_START_FAILED")
        }
        if (!isInterfaceUp()) {
            lifecycleGate.lostConnection()
            throw IllegalArgumentException("TUNNEL_NOT_ESTABLISHED")
        }
        // wireguard-go owns packet forwarding on the shared service's TUN FD.
        lifecycleGate.verifiedConnected("wireguard")
        return mapOf(
            "state" to "interface_up",
            "protocol" to "wireguard",
            "peerHandshakeVerified" to false,
            "killSwitchEnforced" to (service.hasBlockingTun() || isOsLockdownEnforced()),
            "killSwitchMode" to if (service.hasBlockingTun()) "IN_APP_SHARED_TUN"
                else if (isOsLockdownEnforced()) "OS_LOCKDOWN_VERIFIED" else "OFF"
        )
    }

    @Synchronized
    fun stop(): Map<String, Any> {
        lifecycleGate.lostConnection()
        SharedTunVpnService.active?.stopWireGuard()
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
            // wgGetConfig returns sensitive device configuration; only extract
            // numeric counters. Never log or surface the returned string.
            val stats = SharedTunVpnService.active?.wireGuardStats()
            if (stats != null) {
                rx = 0L
                tx = 0L
                var handshakeSec = 0L
                var handshakeNsec = 0L
                for (line in stats.lineSequence()) {
                    when {
                        line.startsWith("rx_bytes=") ->
                            rx = rx!! + (line.substringAfter('=').toLongOrNull() ?: 0L)
                        line.startsWith("tx_bytes=") ->
                            tx = tx!! + (line.substringAfter('=').toLongOrNull() ?: 0L)
                        line.startsWith("last_handshake_time_sec=") -> {
                            if (handshakeSec > 0L) {
                                val stamp = handshakeSec * 1000L + handshakeNsec / 1000000L
                                latestHandshake = maxOf(latestHandshake ?: 0L, stamp)
                            }
                            handshakeSec = line.substringAfter('=').toLongOrNull() ?: 0L
                            handshakeNsec = 0L
                        }
                        line.startsWith("last_handshake_time_nsec=") -> {
                            handshakeNsec = line.substringAfter('=').toLongOrNull() ?: 0L
                        }
                    }
                }
                if (handshakeSec > 0L) {
                    val stamp = handshakeSec * 1000L + handshakeNsec / 1000000L
                    latestHandshake = maxOf(latestHandshake ?: 0L, stamp)
                }
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
            "killSwitchEnforced" to
                (SharedTunVpnService.active?.hasBlockingTun() == true || isOsLockdownEnforced()),
            "killSwitchMode" to if (SharedTunVpnService.active?.hasBlockingTun() == true)
                "IN_APP_SHARED_TUN" else if (isOsLockdownEnforced())
                "OS_LOCKDOWN_VERIFIED" else "OFF"
        )
        if (rx != null) result["rxBytes"] = rx
        if (tx != null) result["txBytes"] = tx
        if (latestHandshake != null) {
            result["latestHandshakeEpochMillis"] = latestHandshake
        }
        return result
    }
}
