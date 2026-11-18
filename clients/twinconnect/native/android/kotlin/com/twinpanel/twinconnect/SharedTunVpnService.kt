package com.twinpanel.twinconnect

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import android.util.Log
import com.axevpn.flutter.openconnect.SharedOpenConnectEngine
import com.wireguard.android.backend.GoBackend
import com.wireguard.config.Config
import java.lang.reflect.Method
import java.net.Inet4Address

/**
 * Sole VpnService for the shared native-TUN architecture.
 *
 * Android owns the routing decision. A configured TUN with no running engine
 * is a black hole; no packet is copied to an ordinary device socket. WireGuard
 * receives a duplicated TUN FD and reads/writes IP packets itself. The primary
 * FD is retained so disconnect does not relinquish Android's VPN routing slot.
 *
 * This provides an in-process disconnect guard, NOT Android's system lockdown:
 * force-stop, process death, revocation, and reboot need OS lockdown.
 */
class SharedTunVpnService : VpnService() {
    private val lock = Any()
    @Volatile private var tun: ParcelFileDescriptor? = null
    @Volatile private var wireGuardHandle = -1
    @Volatile private var persistentBlock = false
    @Volatile private var foregroundReady = false
    @Volatile private var shuttingDown = false
    @Volatile private var ciscoEngine: SharedOpenConnectEngine? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            shutdown()
            return START_NOT_STICKY
        }
        if (VpnService.prepare(this) != null) {
            shutdown()
            return START_NOT_STICKY
        }
        try {
            val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                manager.createNotificationChannel(NotificationChannel(
                    CHANNEL, "TwinConnect VPN", NotificationManager.IMPORTANCE_LOW))
            }
            val notification = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                Notification.Builder(this, CHANNEL) else {
                @Suppress("DEPRECATION")
                Notification.Builder(this)
            }
            startForeground(NOTIFICATION_ID, notification
                .setSmallIcon(android.R.drawable.ic_lock_lock)
                .setContentTitle("TwinConnect VPN")
                .setContentText("Protected tunnel")
                .setOngoing(true).build())
            foregroundReady = true
            active = this
            when (intent?.action) {
                ACTION_START_BLOCK -> enableBlocking()
                ACTION_CONNECT_CISCO -> try {
                    connectCisco(intent)
                } catch (_: IllegalStateException) {
                    // Reject a second engine without terminating the first
                    // engine or releasing Android's existing VPN route.
                    SharedOpenConnectEngine.reject(this, "CISCO_SHARED_TUN_BUSY")
                }
                ACTION_DISCONNECT_CISCO -> disconnectCisco()
            }
        } catch (_: Exception) {
            shutdown()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    private fun blockingTun(): ParcelFileDescriptor = Builder()
        .setSession("TwinConnect disconnect guard")
        .setBlocking(true)
        .setMtu(1280)
        .addAddress("10.253.253.1", 32)
        .addRoute("0.0.0.0", 0)
        .addAddress("fd00:253:253::1", 128)
        .addRoute("::", 0)
        .addDnsServer("10.253.253.1")
        .establish() ?: throw IllegalStateException("SHARED_TUN_ESTABLISH_FAILED")

    fun enableBlocking() {
        synchronized(lock) {
            check(foregroundReady && !shuttingDown) { "SHARED_TUN_NOT_READY" }
            persistentBlock = true
            if (tun == null) tun = blockingTun()
        }
    }

    fun disableBlocking() {
        val shouldClose: Boolean
        synchronized(lock) {
            persistentBlock = false
            shouldClose = wireGuardHandle < 0 && ciscoEngine == null
        }
        if (shouldClose) shutdown()
    }

    /** Cisco and WireGuard share this *same* VpnService and Android VPN slot. */
    private fun connectCisco(intent: Intent) {
        val engine = synchronized(lock) {
            check(foregroundReady && !shuttingDown && active === this) {
                "SHARED_TUN_NOT_READY"
            }
            check(wireGuardHandle < 0 && ciscoEngine == null) { "TUNNEL_ALREADY_RUNNING" }
            SharedOpenConnectEngine(this).also { ciscoEngine = it }
        }
        Thread({ engine.connect(intent) }, "oc-shared-tun").start()
    }

    private fun disconnectCisco() {
        val engine = synchronized(lock) {
            val current = ciscoEngine
            if (current != null && persistentBlock && tun != null) {
                try {
                    // Take routing away from the native transport *before*
                    // cancellation. Even a slow TLS/DTLS shutdown must not
                    // keep forwarding packets after Disconnect was requested.
                    val replacement = blockingTun()
                    val previous = tun
                    tun = replacement
                    previous?.close()
                } catch (_: Exception) {
                    // Keep the existing captured route until the native
                    // transport exits; never release the VPN slot here.
                    Log.e("TwinSharedCisco", "CISCO_DISCONNECT_BLOCK_FAILED")
                }
            }
            current
        }
        if (engine == null) {
            if (!persistentBlock && wireGuardHandle < 0) shutdown()
        } else engine.stop()
    }

    /** Called by libopenconnect only after it authenticates and receives IPInfo. */
    fun establishCiscoTun(
        engine: SharedOpenConnectEngine,
        name: String,
        address: String,
        prefix: Int,
        mtu: Int,
        dnsServers: List<String>,
        ipv6Address: String?,
        ipv6Prefix: Int
    ): ParcelFileDescriptor = synchronized(lock) {
        check(active === this && !shuttingDown && ciscoEngine === engine &&
            wireGuardHandle < 0) { "SHARED_TUN_OWNER_CHANGED" }
        check(VpnService.prepare(this) == null) { "VPN_PERMISSION_REQUIRED" }
        check(dnsServers.isNotEmpty()) { "CISCO_DNS_MISSING" }
        val builder = Builder().setSession(name)
            .setBlocking(true)
            .setMtu(mtu.coerceIn(1280, 1300))
            .addAddress(address, prefix)
            .addRoute("0.0.0.0", 0)
        for (dns in dnsServers) builder.addDnsServer(dns)
        // Capture *both* address families. IPv4-only Cisco gateways discard
        // IPv6 inside TUN rather than letting it bypass the kill switch.
        if (ipv6Address != null) builder.addAddress(ipv6Address, ipv6Prefix)
        else builder.addAddress("fd00:253:253::1", 128)
        builder.addRoute("::", 0)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) builder.setMetered(false)
        val replacement = builder.establish()
            ?: throw IllegalStateException("SHARED_TUN_ESTABLISH_FAILED")
        val previous = tun
        tun = replacement
        previous?.close()
        // Keep the owner FD. libopenconnect may close its *duplicate* on exit,
        // leaving this service's routing slot alive as a blackhole.
        ParcelFileDescriptor.dup(replacement.fileDescriptor)
    }

    fun onCiscoEngineStopped(engine: SharedOpenConnectEngine) {
        val close = synchronized(lock) {
            if (ciscoEngine !== engine) return
            ciscoEngine = null
            !persistentBlock && !shuttingDown
        }
        if (close) shutdown()
    }

    /** Actual ownership handoff: no GoBackend.setState or second VpnService. */
    fun startWireGuard(config: Config, keepBlockedOnDisconnect: Boolean) {
        var ownsFailedStart = false
        try {
        synchronized(lock) {
            check(foregroundReady && !shuttingDown && active === this) {
                "SHARED_TUN_NOT_READY"
            }
            check(wireGuardHandle < 0) { "TUNNEL_ALREADY_RUNNING" }
            check(ciscoEngine == null) { "TUNNEL_ALREADY_RUNNING" }
            check(VpnService.prepare(this) == null) { "VPN_PERMISSION_REQUIRED" }
            // Once this startup owns the routing transition, it is responsible
            // for tearing it down if native activation fails. A failed WG
            // attempt must never turn an OFF kill switch permanently ON.
            ownsFailedStart = true
            // Never downgrade a guard already enabled using the settings button.
            persistentBlock = persistentBlock || keepBlockedOnDisconnect
            if (persistentBlock && tun == null) tun = blockingTun()
            // Resolve ONLY the VPN peer endpoint on an underlying Network.
            // Default DNS could already be blackholed by the active guard.
            // Never bind the entire process to that underlying network.
            val settings = wireGuardUserspaceConfig(config)
            val builder = Builder().setSession("TwinConnect WireGuard")
                .setBlocking(true)
                .setMtu(config.`interface`.mtu.orElse(1280))
            for (address in config.`interface`.addresses) {
                builder.addAddress(address.address, address.mask)
            }
            if (config.`interface`.addresses.none { it.address.address.size == 16 }) {
                // A full IPv6 route into an IPv4-only peer must fail closed.
                builder.addAddress("fd00:253:253::1", 128)
            }
            for (dns in config.`interface`.dnsServers) {
                builder.addDnsServer(dns.hostAddress!!)
            }
            for (domain in config.`interface`.dnsSearchDomains) builder.addSearchDomain(domain)
            // Route BOTH families, independent of a peer's AllowedIPs layout.
            builder.addRoute("0.0.0.0", 0).addRoute("::", 0)
            val replacement = builder.establish()
                ?: throw IllegalStateException("SHARED_TUN_ESTABLISH_FAILED")
            val previous = tun
            tun = replacement
            previous?.close()

            // GoBackend's JNI is package-private in practice (private Java
            // methods). Reflection is scoped to the app-bundled WireGuard AAR.
            // The bridge never instantiates GoBackend.VpnService.
            try {
                GoBackend(applicationContext) // loads the pinned libwg-go
                val copied = ParcelFileDescriptor.dup(replacement.fileDescriptor)
                val nativeFd = copied.detachFd()
                val handle = try {
                    WireGuardJni.turnOn(nativeFd, settings)
                } catch (failure: Exception) {
                    // JNI takes ownership of the fd only if successfully called.
                    // On invocation errors close the detached copy defensively.
                    try { ParcelFileDescriptor.adoptFd(nativeFd).close() } catch (_: Exception) {}
                    throw failure
                }
                if (handle < 0) throw IllegalStateException("WIREGUARD_NATIVE_START_FAILED")
                try {
                    val ipv4 = WireGuardJni.socketV4(handle)
                    val ipv6 = WireGuardJni.socketV6(handle)
                    if ((ipv4 >= 0 && !protect(ipv4)) ||
                        (ipv6 >= 0 && !protect(ipv6))) {
                        throw IllegalStateException("WIREGUARD_SOCKET_PROTECT_FAILED")
                    }
                    wireGuardHandle = handle
                } catch (failure: Exception) {
                    WireGuardJni.turnOff(handle)
                    throw failure
                }
            } catch (failure: Exception) {
                throw failure
            }
        }
        } catch (failure: Exception) {
            if (ownsFailedStart) cleanupFailedWireGuardStart(failure.javaClass.simpleName)
            throw failure
        } catch (failure: LinkageError) {
            if (ownsFailedStart) cleanupFailedWireGuardStart("NATIVE_LINKAGE")
            throw failure
        }
    }

    private fun cleanupFailedWireGuardStart(category: String) {
        // Never log the profile, endpoint, peer keys, or native exception text.
        Log.e("TwinConnectWireGuard", "WireGuard start failed: $category")
        // If the user explicitly requested a disconnected guard, the owned
        // TUN remains a black hole. Otherwise release Android's VPN slot so
        // Cisco/OpenConnect and other engines can connect normally.
        if (!persistentBlock) shutdown()
    }

    fun stopWireGuard() {
        val close: Boolean
        synchronized(lock) {
            val handle = wireGuardHandle
            wireGuardHandle = -1
            if (handle >= 0) WireGuardJni.turnOff(handle)
            close = !persistentBlock
        }
        if (close) shutdown()
    }

    fun hasWireGuardTunnel() = wireGuardHandle >= 0
    fun hasCiscoTunnel() = ciscoEngine?.isConnected == true
    fun hasBlockingTun() = tun != null && persistentBlock
    fun hasTunnel() = tun != null
    fun isLockdownVerified(): Boolean = try { isLockdownEnabled } catch (_: Exception) { false }

    /** Resolve Cisco outside VPN DNS when the guard already blackholes traffic. */
    fun resolveCiscoGateway(hostname: String): String {
        val manager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        for (network in manager.allNetworks) {
            val caps = manager.getNetworkCapabilities(network) ?: continue
            if (caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN) ||
                !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)) continue
            val resolved = try { network.getAllByName(hostname).toList() }
                catch (_: Exception) { emptyList() }
            val address = resolved.firstOrNull { it is Inet4Address }
            if (address?.hostAddress != null) return address.hostAddress!!
        }
        throw IllegalStateException("CISCO_GATEWAY_UNDERLAY_DNS_FAILED")
    }

    fun wireGuardStats(): String? = synchronized(lock) {
        // wireguard-go keeps tunnel handles in a native map. A statistics read
        // racing wgTurnOff() during disconnect/revoke can fatally crash the
        // process. Serialize getConfig and turnOff on the same service lock.
        val handle = wireGuardHandle
        if (handle < 0) null else try { WireGuardJni.getConfig(handle) }
            catch (_: Exception) { null }
    }

    private fun wireGuardUserspaceConfig(config: Config): String {
        check(config.peers.isNotEmpty()) { "WIREGUARD_ENDPOINT_MISSING" }
        val manager = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val underlays = manager.allNetworks.filter { network ->
            val capabilities = manager.getNetworkCapabilities(network)
            capabilities != null &&
                !capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN) &&
                capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
        }
        val settings = StringBuilder(config.`interface`.toWgUserspaceString())
        settings.append("replace_peers=true\n")
        for (peer in config.peers) {
            val endpoint = peer.endpoint.orElse(null)
                ?: throw IllegalStateException("WIREGUARD_ENDPOINT_MISSING")
            var target: String? = null
            for (network in underlays) {
                val resolved = try {
                    network.getAllByName(endpoint.host).toList()
                } catch (_: Exception) {
                    emptyList()
                }
                val address = resolved.firstOrNull { it is Inet4Address }
                    ?: resolved.firstOrNull()
                if (address != null) {
                    val ip = address.hostAddress ?: continue
                    val host = if (ip.contains(':')) "[$ip]" else ip
                    target = "$host:${endpoint.port}"
                    break
                }
            }
            check(target != null) { "WIREGUARD_ENDPOINT_DNS_FAILED" }
            settings.append("public_key=").append(peer.publicKey.toHex()).append('\n')
            for (allowed in peer.allowedIps) {
                settings.append("allowed_ip=").append(allowed).append('\n')
            }
            settings.append("endpoint=").append(target).append('\n')
            peer.persistentKeepalive.ifPresent {
                settings.append("persistent_keepalive_interval=").append(it).append('\n')
            }
            peer.preSharedKey.ifPresent {
                settings.append("preshared_key=").append(it.toHex()).append('\n')
            }
        }
        return settings.toString()
    }

    private fun shutdown() {
        var stoppedCisco: SharedOpenConnectEngine? = null
        synchronized(lock) {
            if (shuttingDown) return
            shuttingDown = true
            stoppedCisco = ciscoEngine
            ciscoEngine = null
            val handle = wireGuardHandle
            wireGuardHandle = -1
            if (handle >= 0) try { WireGuardJni.turnOff(handle) } catch (_: Exception) {}
            tun?.close()
            tun = null
            persistentBlock = false
            foregroundReady = false
            if (active === this) active = null
        }
        stoppedCisco?.stop()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
        stopSelf()
    }

    override fun onRevoke() {
        shutdown()
        super.onRevoke()
    }

    override fun onDestroy() {
        shutdown()
        super.onDestroy()
    }

    companion object {
        const val ACTION_START_BLOCK = "com.twinpanel.twinconnect.START_SHARED_BLOCK"
        const val ACTION_CONNECT_CISCO = "com.twinpanel.twinconnect.CONNECT_SHARED_CISCO"
        const val ACTION_DISCONNECT_CISCO = "com.twinpanel.twinconnect.DISCONNECT_SHARED_CISCO"
        const val ACTION_STOP = "com.twinpanel.twinconnect.STOP_SHARED_TUN"
        private const val CHANNEL = "twinconnect_shared_tun"
        private const val NOTIFICATION_ID = 47032
        @Volatile var active: SharedTunVpnService? = null
            private set
    }
}

/** Native ABI exported by the pinned official wireguard-go AAR. */
private object WireGuardJni {
    private val intType = Int::class.javaPrimitiveType!!
    private fun function(name: String, vararg parameters: Class<*>): Method =
        GoBackend::class.java.getDeclaredMethod(name, *parameters).apply { isAccessible = true }

    fun turnOn(fd: Int, settings: String): Int = function(
        "wgTurnOn", String::class.java, intType, String::class.java
    ).invoke(null, "twinconnect", fd, settings) as Int

    fun turnOff(handle: Int) {
        function("wgTurnOff", intType).invoke(null, handle)
    }

    fun socketV4(handle: Int): Int = function("wgGetSocketV4", intType).invoke(null, handle) as Int
    fun socketV6(handle: Int): Int = function("wgGetSocketV6", intType).invoke(null, handle) as Int
    fun getConfig(handle: Int): String? = function("wgGetConfig", intType).invoke(null, handle) as? String
}
