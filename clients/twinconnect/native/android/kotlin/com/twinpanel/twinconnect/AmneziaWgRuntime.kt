package com.twinpanel.twinconnect

import android.content.Context
import android.net.VpnService
import org.amnezia.awg.backend.GoBackend
import org.amnezia.awg.backend.Tunnel
import org.amnezia.awg.config.Config
import java.io.ByteArrayInputStream
import java.nio.charset.StandardCharsets

/** Independent AmneziaWG backend; never falls back to stock WireGuard. */
internal object AmneziaWgRuntime {
    private var backend: GoBackend? = null
    private val tunnel = object : Tunnel {
        override fun getName(): String = "twinconnect-awg"
        override fun onStateChange(newState: Tunnel.State) = Unit
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
    fun isUp(): Boolean = try {
        backend?.getState(tunnel) == Tunnel.State.UP
    } catch (_: Exception) {
        false
    }

    @Synchronized
    fun connect(context: Context, raw: String): Map<String, Any> {
        require(initialize(context)) { "AWG_ENGINE_UNAVAILABLE" }
        require(VpnService.prepare(context) == null) { "VPN_PERMISSION_REQUIRED" }
        require(!WireGuardRuntime.isInterfaceUp()) { "OTHER_VPN_ACTIVE" }
        require(!isUp()) { "AWG_ALREADY_CONNECTED" }
        require(raw.length in 100..200_000 &&
            raw.contains("[Interface]") && raw.contains("[Peer]")) {
            "AWG_PROFILE_INVALID"
        }
        require(Regex("(?im)^\\s*DNS\\s*=\\s*\\S+").containsMatchIn(raw)) {
            "AWG_DNS_MISSING"
        }
        require(Regex("(?im)^\\s*AllowedIPs\\s*=.*(?:0\\.0\\.0\\.0/0|0\\.0\\.0\\.0/1)").containsMatchIn(raw)) {
            "AWG_DEFAULT_ROUTE_MISSING"
        }
        val bytes = raw.toByteArray(StandardCharsets.UTF_8)
        val config = try {
            Config.parse(ByteArrayInputStream(bytes))
        } catch (_: Exception) {
            throw IllegalArgumentException("AWG_CONFIG_PARSE_FAILED")
        } finally {
            bytes.fill(0)
        }
        val state = try {
            backend!!.setState(tunnel, Tunnel.State.UP, config)
        } catch (_: Exception) {
            throw IllegalArgumentException("AWG_NATIVE_START_FAILED")
        }
        require(state == Tunnel.State.UP && isUp()) { "AWG_TUN_NOT_ESTABLISHED" }
        return mapOf(
            "connected" to true,
            "tunnelVerified" to true,
            "peerHandshakeVerified" to false,
            "state" to "interface_up"
        )
    }

    @Synchronized
    fun disconnect(): Map<String, Any> {
        if (isUp()) backend!!.setState(tunnel, Tunnel.State.DOWN, null)
        return mapOf("connected" to false, "tunnelVerified" to false)
    }
}
