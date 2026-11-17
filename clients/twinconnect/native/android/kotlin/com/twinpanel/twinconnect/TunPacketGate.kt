package com.twinpanel.twinconnect

/**
 * Fail-closed packet admission policy for a future shared Android TUN owner.
 *
 * A packet forwarder must call [allows] for every outbound packet BEFORE
 * writing to the transport. This class alone does not intercept Android traffic.
 * No fallback to the underlying network is permitted when the tunnel drops.
 */
internal class TunPacketGate {
    enum class State { BLOCKED, CONNECTING, CONNECTED }
    enum class PacketRoute { VPN_TUNNEL, UNDERLYING_NETWORK }

    @Volatile private var state = State.BLOCKED
    @Volatile private var selectedEngine: String? = null

    @Synchronized
    fun beginConnect(engine: String) {
        require(engine.isNotBlank()) { "VPN_ENGINE_MISSING" }
        state = State.CONNECTING
        selectedEngine = engine
    }

    @Synchronized
    fun verifiedConnected(engine: String) {
        require(state == State.CONNECTING && selectedEngine == engine) {
            "VPN_TUNNEL_OWNER_MISMATCH"
        }
        state = State.CONNECTED
    }

    @Synchronized
    fun lostConnection() {
        state = State.BLOCKED
        selectedEngine = null
    }

    fun allows(route: PacketRoute): Boolean =
        state == State.CONNECTED && route == PacketRoute.VPN_TUNNEL

    fun status(): State = state
}
