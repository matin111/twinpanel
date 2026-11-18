package com.twinpanel.twinconnect

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.net.VpnService
import android.os.ParcelFileDescriptor
import java.io.FileInputStream

/**
 * Disconnected-state fail-closed TUN: no packet forwarding, DNS or bypass.
 * This is NOT a seamless handover mechanism or an OS lockdown replacement.
 * Only start after VpnService.prepare() returns null (user consent granted).
 */
class AndroidTrafficGuardService : VpnService() {
    private var tun: ParcelFileDescriptor? = null
    private val packetGate = TunPacketGate()
    @Volatile private var drainThread: Thread? = null

    @Volatile private var established = false

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopGuard()
            return START_NOT_STICKY
        }
        if (VpnService.prepare(this) != null) {
            stopSelf()
            return START_NOT_STICKY
        }
        try {
            val notifications = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                notifications.createNotificationChannel(NotificationChannel(
                    CHANNEL_ID, "VPN traffic protection", NotificationManager.IMPORTANCE_LOW
                ))
            }
            val notificationBuilder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                Notification.Builder(this, CHANNEL_ID)
            } else {
                @Suppress("DEPRECATION")
                Notification.Builder(this)
            }
            val notification = notificationBuilder
                .setSmallIcon(android.R.drawable.ic_lock_lock)
                .setContentTitle("TwinConnect Kill Switch")
                .setContentText("Disconnected traffic is blocked")
                .setOngoing(true)
                .build()
            startForeground(NOTIFICATION_ID, notification)
            established = false
            tun?.close()
            tun = Builder()
                .setSession("TwinConnect traffic guard")
                .setMtu(1280)
                .addAddress("10.253.254.1", 32)
                .addRoute("0.0.0.0", 0)
                .addAddress("fd00:253:254::1", 128)
                .addRoute("::", 0)
                .addDnsServer("10.253.254.1")
                .addDnsServer("fd00:253:254::1")
                .setBlocking(true)
                .establish()
            established = tun != null
            active = established
            if (tun == null) stopSelf() else startDropLoop(tun!!)
        } catch (_: Exception) {
            stopGuard()
        }
        return START_STICKY
    }

    // Consume actual TUN ingress and discard every packet. No network egress.
    // This legacy guard remains disabled for unsafe protocol handoffs.
    private fun startDropLoop(descriptor: ParcelFileDescriptor) {
        packetGate.lostConnection()
        val worker = Thread({
            try {
                val input = FileInputStream(descriptor.fileDescriptor)
                val packet = ByteArray(32768)
                while (!Thread.currentThread().isInterrupted && active) {
                    if (input.read(packet) < 0) break
                    check(!packetGate.allows(TunPacketGate.PacketRoute.UNDERLYING_NETWORK))
                }
            } catch (_: Exception) {
                // Closing TUN on shutdown interrupts the blocking read.
            } finally {
                packetGate.lostConnection()
            }
        }, "twinconnect-guard-drop")
        worker.isDaemon = true
        drainThread = worker
        worker.start()
    }

    override fun onRevoke() {
        stopGuard()
    }

    override fun onDestroy() {
        packetGate.lostConnection()
        tun?.close()
        tun = null
        drainThread?.interrupt()
        drainThread = null
        established = false
        active = false
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
        super.onDestroy()
    }

    private fun stopGuard() {
        packetGate.lostConnection()
        tun?.close()
        tun = null
        drainThread?.interrupt()
        drainThread = null
        established = false
        active = false
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    companion object {
        private const val CHANNEL_ID = "twinconnect_traffic_guard"
        private const val NOTIFICATION_ID = 47031
        @Volatile var active: Boolean = false
            private set
        const val ACTION_STOP = "com.twinpanel.twinconnect.STOP_TRAFFIC_GUARD"
    }
}
