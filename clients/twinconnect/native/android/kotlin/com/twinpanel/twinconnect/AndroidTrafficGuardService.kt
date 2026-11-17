package com.twinpanel.twinconnect

import android.content.Intent
import android.net.VpnService
import android.os.ParcelFileDescriptor

/**
 * Disconnected-state fail-closed TUN: no packet forwarding, DNS or bypass.
 * This is NOT a seamless handover mechanism or an OS lockdown replacement.
 * Only start after VpnService.prepare() returns null (user consent granted).
 */
class AndroidTrafficGuardService : VpnService() {
    private var tun: ParcelFileDescriptor? = null

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
            if (tun == null) stopSelf()
        } catch (_: Exception) {
            stopGuard()
        }
        return START_NOT_STICKY
    }

    override fun onRevoke() {
        stopGuard()
    }

    override fun onDestroy() {
        tun?.close()
        tun = null
        established = false
        active = false
        super.onDestroy()
    }

    private fun stopGuard() {
        tun?.close()
        tun = null
        established = false
        active = false
        stopSelf()
    }

    companion object {
        @Volatile var active: Boolean = false
            private set
        const val ACTION_STOP = "com.twinpanel.twinconnect.STOP_TRAFFIC_GUARD"
    }
}
