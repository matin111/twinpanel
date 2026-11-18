package com.twinpanel.twinconnect

import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.os.Build
import org.amnezia.awg.GoBackend as AmneziaNative
import org.amnezia.awg.config.Config
import java.io.ByteArrayInputStream
import java.nio.charset.StandardCharsets

/** The official AmneziaWG JNI core using TwinConnect's single Android TUN. */
internal object AmneziaWgRuntime {
    private var libraryLoaded = false

    @Synchronized
    fun initialize(context: Context): Boolean {
        if (libraryLoaded) return true
        return try {
            // The pinned AAR is JNI-isolated: libawg-go.so, not libwg-go.so.
            System.loadLibrary("awg-go")
            libraryLoaded = true
            true
        } catch (_: Exception) {
            false
        } catch (_: LinkageError) {
            false
        }
    }

    @Synchronized
    fun isUp(): Boolean = SharedTunVpnService.active?.hasAmneziaWgTunnel() == true

    private fun hasFullIpv4(raw: String): Boolean {
        val routes = Regex("(?im)^\\s*AllowedIPs\\s*=\\s*(.*)$")
            .findAll(raw).flatMap { it.groupValues[1].split(',').asSequence() }
            .map { it.trim() }.toSet()
        return "0.0.0.0/0" in routes ||
            ("0.0.0.0/1" in routes && "128.0.0.0/1" in routes)
    }

    private fun userspaceSettings(config: Config, service: SharedTunVpnService): String {
        // Preserve ALL official AmneziaWG Interface-level obfuscation options
        // (Jc, Jmin, Jmax, S1/S2, H1-H4). No stock WG substitution.
        val settings = StringBuilder(config.`interface`.toAwgUserspaceString())
        settings.append("replace_peers=true\n")
        for (peer in config.peers) {
            val endpoint = peer.endpoint.orElse(null)
                ?: throw IllegalArgumentException("AWG_ENDPOINT_MISSING")
            val ip = try { service.resolveAwgGateway(endpoint.host) }
                catch (_: Exception) { throw IllegalArgumentException("AWG_ENDPOINT_DNS_FAILED") }
            val host = if (ip.contains(':')) "[$ip]" else ip
            settings.append("public_key=").append(peer.publicKey.toHex()).append('\n')
            for (route in peer.allowedIps) settings.append("allowed_ip=").append(route).append('\n')
            settings.append("endpoint=").append(host).append(':').append(endpoint.port).append('\n')
            peer.persistentKeepalive.ifPresent {
                settings.append("persistent_keepalive_interval=").append(it).append('\n')
            }
            peer.preSharedKey.ifPresent {
                settings.append("preshared_key=").append(it.toHex()).append('\n')
            }
        }
        return settings.toString()
    }

    @Synchronized
    fun connect(context: Context, raw: String): Map<String, Any> {
        require(initialize(context)) { "AWG_ENGINE_UNAVAILABLE" }
        require(VpnService.prepare(context) == null) { "VPN_PERMISSION_REQUIRED" }
        require(!isUp()) { "AWG_ALREADY_CONNECTED" }
        require(raw.length in 100..200_000 && raw.contains("[Interface]") &&
            raw.contains("[Peer]")) { "AWG_PROFILE_INVALID" }
        require(Regex("(?im)^\\s*DNS\\s*=\\s*\\S+").containsMatchIn(raw)) {
            "AWG_DNS_MISSING"
        }
        require(hasFullIpv4(raw)) { "AWG_DEFAULT_ROUTE_MISSING" }
        val bytes = raw.toByteArray(StandardCharsets.UTF_8)
        val config = try {
            Config.parse(ByteArrayInputStream(bytes))
        } catch (_: Exception) {
            throw IllegalArgumentException("AWG_CONFIG_PARSE_FAILED")
        } finally {
            bytes.fill(0)
        }
        // Start the same foreground VPN service that WireGuard, Cisco and
        // the disconnected blackhole guard already use.
        val service = try {
            val intent = Intent(context, SharedTunVpnService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) context.startForegroundService(intent)
            else context.startService(intent)
            var ready: SharedTunVpnService? = null
            for (attempt in 0 until 100) {
                ready = SharedTunVpnService.active
                if (ready != null) break
                Thread.sleep(50)
            }
            ready ?: throw IllegalStateException("SHARED_TUN_NOT_READY")
        } catch (_: Exception) {
            throw IllegalArgumentException("SHARED_TUN_NOT_READY")
        }
        val settings = try { userspaceSettings(config, service) }
            catch (failure: Exception) {
                service.shutdownIfIdle()
                throw failure
            }
        try {
            service.startAmneziaWg(
                addresses = config.`interface`.addresses.map { it.address to it.mask },
                dnsServers = config.`interface`.dnsServers.toList(),
                searchDomains = config.`interface`.dnsSearchDomains.toList(),
                mtu = config.`interface`.mtu.orElse(1280),
                settings = settings,
                keepBlockedOnDisconnect = service.hasBlockingTun(),
                turnOn = { fd, data -> AmneziaNative.awgTurnOn("twinconnect-awg", fd, data) },
                turnOff = { handle -> AmneziaNative.awgTurnOff(handle) },
                getSockets = { handle -> AmneziaNative.awgGetSocketV4(handle) to
                    AmneziaNative.awgGetSocketV6(handle) },
                getStats = { handle -> AmneziaNative.awgGetConfig(handle) }
            )
        } catch (failure: Exception) {
            val codes = setOf("SHARED_TUN_NOT_READY", "TUNNEL_ALREADY_RUNNING",
                "AWG_PROFILE_INVALID", "AWG_SOCKET_PROTECT_FAILED",
                "AWG_GO_ACTIVATION_FAILED", "SHARED_TUN_ESTABLISH_FAILED",
                "VPN_PERMISSION_REQUIRED")
            throw IllegalArgumentException(failure.message?.takeIf { it in codes }
                ?: "AWG_NATIVE_START_FAILED")
        } catch (_: LinkageError) {
            throw IllegalArgumentException("AWG_NATIVE_LINK_FAILED")
        }
        require(isUp()) { "AWG_TUN_NOT_ESTABLISHED" }
        return mapOf("connected" to true, "tunnelVerified" to true,
            "peerHandshakeVerified" to false, "state" to "interface_up")
    }

    @Synchronized
    fun status(): Map<String, Any> {
        if (!isUp()) return mapOf("connected" to false)
        var rx = 0L
        var tx = 0L
        var lastHandshake = 0L
        var lastSeconds = 0L
        var lastNanos = 0L
        // Serialize native reads with stop/revoke in SharedTunVpnService.
        val stats = SharedTunVpnService.active?.amneziaStats() ?: return mapOf(
            "connected" to true, "peerHandshakeVerified" to false)
        for (line in stats.lineSequence()) {
            when {
                line.startsWith("rx_bytes=") -> rx += line.substringAfter('=').toLongOrNull() ?: 0L
                line.startsWith("tx_bytes=") -> tx += line.substringAfter('=').toLongOrNull() ?: 0L
                line.startsWith("last_handshake_time_sec=") -> {
                    lastHandshake = maxOf(lastHandshake, lastSeconds * 1000L + lastNanos / 1000000L)
                    lastSeconds = line.substringAfter('=').toLongOrNull() ?: 0L
                    lastNanos = 0L
                }
                line.startsWith("last_handshake_time_nsec=") ->
                    lastNanos = line.substringAfter('=').toLongOrNull() ?: 0L
            }
        }
        lastHandshake = maxOf(lastHandshake, lastSeconds * 1000L + lastNanos / 1000000L)
        val age = System.currentTimeMillis() - lastHandshake
        return mapOf("connected" to true, "rxBytes" to rx, "txBytes" to tx,
            "peerHandshakeVerified" to (lastHandshake > 0L && age in -10_000L..180_000L))
    }

    @Synchronized
    fun disconnect(): Map<String, Any> {
        SharedTunVpnService.active?.stopAmneziaWg()
        return mapOf("connected" to false, "tunnelVerified" to false)
    }
}
