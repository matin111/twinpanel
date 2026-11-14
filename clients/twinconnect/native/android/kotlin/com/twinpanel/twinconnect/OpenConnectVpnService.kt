package com.twinpanel.twinconnect

import android.net.VpnService

/**
 * Dedicated Android VPN owner reserved for the Cisco/OpenConnect transport.
 *
 * This service intentionally does NOT establish an empty TUN adapter or
 * falsely claim a running tunnel. A reviewed libopenconnect JNI integration
 * must supply the encrypted transport, authenticated network configuration,
 * DNS/IPv6 policy and byte counters before MainActivity can expose support.
 * WireGuard's GoBackend uses an independent VpnService.
 */
class OpenConnectVpnService : VpnService() {
    override fun onRevoke() {
        // Once the real engine is integrated, revoke must also cancel its
        // native worker and close its TUN descriptor before returning.
        stopSelf()
        super.onRevoke()
    }
}
