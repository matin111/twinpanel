package com.twinpanel.twinconnect

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import java.io.FileInputStream
import java.io.FileOutputStream
import java.net.DatagramSocket
import java.net.Socket

/**
 * Single Android VPN owner for engines adapted to [PacketEngine].
 *
 * IMPORTANT: Legacy WireGuard GoBackend, OpenVPN and OpenConnect plugins do
 * not implement this contract yet. They must NOT be started alongside this
 * service; doing so would steal Android's VPN slot.
 *
 * The shared TUN stays established when a transport fails. Its ingress loop
 * drops packets while the engine is not verified, preventing an application
 * fallback socket from receiving cleartext packets through this service.
 * Android OS lockdown is still needed for process death/revoke protection.
 */
class SharedTunVpnService : VpnService() {
    interface PacketEngine {
        val id: String
        /** Called only with an active VPN owner; engine owns NO VpnService. */
        fun start(underlying: SocketProtector, sink: PacketSink)
        /** Encrypted transport must be ready before returning true. */
        fun isReady(): Boolean
        /** Consume a full IP packet, never send it over an unprotected socket. */
        fun sendPacket(packet: ByteArray, length: Int)
        fun stop()
    }

    interface SocketProtector {
        fun protect(socket: Socket): Boolean
        fun protect(socket: DatagramSocket): Boolean
    }

    interface PacketSink {
        /** Receive decrypted IP packets from the engine, write to TUN only. */
        fun deliver(packet: ByteArray, length: Int)
    }

    private val gate = TunPacketGate()
    private val lock = Any()
    private var generation = 0L
    @Volatile private var tun: ParcelFileDescriptor? = null
    @Volatile private var engine: PacketEngine? = null
    @Volatile private var reader: Thread? = null
    @Volatile private var stopping = false

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            shutdown()
            return START_NOT_STICKY
        }
        if (VpnService.prepare(this) != null) {
            shutdown()
            return START_NOT_STICKY
        }
        if (tun != null) return START_STICKY
        stopping = false
        try {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (Build.VERSION.SDK_INT >= 26) {
                nm.createNotificationChannel(NotificationChannel(
                    CHANNEL, "TwinConnect VPN", NotificationManager.IMPORTANCE_LOW))
            }
            val notification = if (Build.VERSION.SDK_INT >= 26)
                Notification.Builder(this, CHANNEL) else {
                @Suppress("DEPRECATION")
                Notification.Builder(this)
            }
            startForeground(NOTIFICATION_ID, notification
                .setSmallIcon(android.R.drawable.ic_lock_lock)
                .setContentTitle("TwinConnect VPN")
                .setContentText("Protected tunnel")
                .setOngoing(true).build())
            tun = Builder().setSession("TwinConnect shared tunnel")
                .setMtu(1280)
                .addAddress("10.253.253.1", 32)
                .addRoute("0.0.0.0", 0)
                .addAddress("fd00:253:253::1", 128)
                .addRoute("::", 0)
                .addDnsServer("10.253.253.1")
                .addDnsServer("fd00:253:253::1")
                .setBlocking(true)
                .establish() ?: throw IllegalStateException("SHARED_TUN_ESTABLISH_FAILED")
            active = this
            startReader(tun!!)
        } catch (_: Exception) {
            shutdown()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    /**
     * Engine registration is deliberately explicit: no engine can install
     * another VpnService or bypass the packet gate through this API.
     */
    fun attach(next: PacketEngine) {
        synchronized(lock) {
            check(tun != null && active === this) { "SHARED_TUN_NOT_ESTABLISHED" }
            gate.lostConnection()
            generation++
            engine?.stop()
            engine = null
            gate.beginConnect(next.id)
            val token = generation
            try {
                next.start(object : SocketProtector {
                    override fun protect(socket: Socket) = this@SharedTunVpnService.protect(socket)
                    override fun protect(socket: DatagramSocket) = this@SharedTunVpnService.protect(socket)
                }, object : PacketSink {
                    override fun deliver(packet: ByteArray, length: Int) {
                        synchronized(lock) {
                            if (engine !== next || generation != token ||
                                !gate.allows(TunPacketGate.PacketRoute.VPN_TUNNEL)) return
                            if (length <= 0 || length > packet.size) return
                            tun?.let { FileOutputStream(it.fileDescriptor).write(packet, 0, length) }
                        }
                    }
                })
                check(next.isReady()) { "ENGINE_NOT_READY" }
                engine = next
                gate.verifiedConnected(next.id)
            } catch (failure: Exception) {
                gate.lostConnection()
                next.stop()
                throw failure
            }
        }
    }

    fun transportLost() {
        synchronized(lock) {
            gate.lostConnection()
            generation++
            engine?.stop()
            engine = null
        }
    }

    private fun startReader(fd: ParcelFileDescriptor) {
        val thread = Thread({
            try {
                val input = FileInputStream(fd.fileDescriptor)
                val packet = ByteArray(32768)
                while (!Thread.currentThread().isInterrupted && tun === fd) {
                    val length = input.read(packet)
                    if (length < 0) break
                    synchronized(lock) {
                        val current = engine
                        if (current != null && gate.allows(TunPacketGate.PacketRoute.VPN_TUNNEL)
                            && current.isReady()) {
                            val ownedPacket = packet.copyOf(length)
                            current.sendPacket(ownedPacket, ownedPacket.size)
                        } else {
                            // Drop while disconnected. Do not forward outside TUN.
                            if (current != null && !current.isReady()) transportLost()
                        }
                    }
                }
            } catch (_: Exception) {
                transportLost()
            }
        }, "twinconnect-shared-tun")
        thread.isDaemon = true
        reader = thread
        thread.start()
    }

    private fun shutdown() {
        if (stopping) return
        stopping = true
        transportLost()
        tun?.close()
        tun = null
        reader?.interrupt()
        reader = null
        if (active === this) active = null
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
        const val ACTION_STOP = "com.twinpanel.twinconnect.STOP_SHARED_TUN"
        private const val CHANNEL = "twinconnect_shared_tun"
        private const val NOTIFICATION_ID = 47032
        @Volatile var active: SharedTunVpnService? = null
            private set
    }
}
