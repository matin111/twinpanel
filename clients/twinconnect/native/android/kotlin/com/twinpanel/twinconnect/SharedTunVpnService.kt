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
            if (intent?.action == ACTION_START_BLOCK) enableBlocking()
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
            shouldClose = wireGuardHandle < 0
        }
        if (shouldClose) shutdown()
    }

    /** Actual ownership handoff: no GoBackend.setState or second VpnService. */
    fun startWireGuard(config: Config, keepBlockedOnDisconnect: Boolean) {
        synchronized(lock) {
            check(foregroundReady && !shuttingDown && active === this) {
                "SHARED_TUN_NOT_READY"
            }
            check(wireGuardHandle < 0) { "TUNNEL_ALREADY_RUNNING" }
            check(VpnService.prepare(this) == null) { "VPN_PERMISSION_REQUIRED" }
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
                // Keep the TUN established as a black hole on failure.
                // No fallback route is installed by this service.
                if (!persistentBlock) persistentBlock = true
                throw failure
            }
        }
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
    fun hasBlockingTun() = tun != null && persistentBlock
    fun hasTunnel() = tun != null
    fun isLockdownVerified(): Boolean = try { isLockdownEnabled } catch (_: Exception) { false }

    fun wireGuardStats(): String? {
        val handle = wireGuardHandle
        return if (handle >= 0) try { WireGuardJni.getConfig(handle) }
            catch (_: Exception) { null } else null
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
        synchronized(lock) {
            if (shuttingDown) return
            shuttingDown = true
            val handle = wireGuardHandle
            wireGuardHandle = -1
            if (handle >= 0) try { WireGuardJni.turnOff(handle) } catch (_: Exception) {}
            tun?.close()
            tun = null
            persistentBlock = false
            foregroundReady = false
            if (active === this) active = null
        }
        stopForeground(STOP_FOREGROUND_REMOVE)
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
