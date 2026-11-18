// The pinned libopenconnect JNI protocol adapter for SharedTunVpnService.
// Based on the GPL-3.0 axevpn_flutter integration used by TwinConnect.
package com.axevpn.flutter.openconnect;

import android.content.Intent;
import android.os.ParcelFileDescriptor;
import android.util.Log;

import com.twinpanel.twinconnect.SharedTunVpnService;
import org.infradead.libopenconnect.LibOpenConnect;

import java.net.InetAddress;
import java.util.ArrayList;
import java.util.List;

/** No VpnService subclass: the shared service owns and retains the primary TUN. */
public final class SharedOpenConnectEngine {
    private static final String TAG = "TwinSharedCisco";
    private final SharedTunVpnService owner;
    private volatile NativeOpenConnectSession session;
    private volatile boolean stopped;
    private volatile boolean connected;

    public SharedOpenConnectEngine(SharedTunVpnService owner) {
        this.owner = owner;
    }

    public boolean isConnected() { return connected; }

    public static void reject(SharedTunVpnService owner, String reason) {
        AxeOpenConnectVpnService.lastFailureCode = reason;
        broadcast(owner, "error");
    }

    private static void broadcast(SharedTunVpnService owner, String stage) {
        Intent event = new Intent(AxeOpenConnectVpnService.BROADCAST_STAGE);
        event.setPackage(owner.getPackageName());
        event.putExtra(AxeOpenConnectVpnService.EXTRA_STAGE, stage);
        owner.sendBroadcast(event);
    }

    public void connect(Intent intent) {
        AxeOpenConnectVpnService.lastFailureCode = "";
        AxeOpenConnectVpnService.assignedVpnIpv4 = "";
        AxeOpenConnectVpnService.bytesReceived.set(0);
        AxeOpenConnectVpnService.bytesSent.set(0);
        broadcast(owner, "preparing");
        try {
            final String url = intent.getStringExtra(AxeOpenConnectVpnService.EXTRA_SERVER_URL);
            final String user = intent.getStringExtra(AxeOpenConnectVpnService.EXTRA_USERNAME);
            final String pass = intent.getStringExtra(AxeOpenConnectVpnService.EXTRA_PASSWORD);
            final String pin = intent.getStringExtra(AxeOpenConnectVpnService.EXTRA_SERVERCERT);
            final String title = intent.getStringExtra(AxeOpenConnectVpnService.EXTRA_TUNNEL_NAME);
            if (url == null || url.isEmpty() || user == null || user.isEmpty() || pass == null) {
                reject(owner, "CISCO_AUTH_INIT_CONTEXT_MISSING");
                return;
            }
            String underlayAddress = null;
            if (owner.hasBlockingTun()) {
                try {
                    // Bypass only the DNS resolver; never bind the process to
                    // an unprotected network or skip the pinned TLS checks.
                    underlayAddress = owner.resolveCiscoGateway(
                            new java.net.URI(url).getHost());
                } catch (Exception resolveFailure) {
                    reject(owner, "CISCO_GATEWAY_UNDERLAY_DNS_FAILED");
                    return;
                }
            }
            System.loadLibrary("stoken");
            System.loadLibrary("openconnect");
            NativeOpenConnectSession next = new NativeOpenConnectSession(
                    owner, new NativeOpenConnectSession.Listener() {
                @Override public void stage(String stage, String error) {
                    if (error != null && !error.isEmpty()) {
                        AxeOpenConnectVpnService.lastFailureCode = error;
                    }
                    if ("connected".equals(stage)) {
                        connected = true;
                        AxeOpenConnectVpnService.isRunning = true;
                    }
                    broadcast(owner, stage);
                }

                @Override public ParcelFileDescriptor establish(LibOpenConnect.IPInfo ip) {
                    try {
                        if (stopped || ip == null || ip.addr == null || ip.netmask == null ||
                                ip.DNS == null || ip.DNS.isEmpty()) return null;
                        int prefix = prefixFromNetmask(ip.netmask);
                        String address6 = null;
                        int prefix6 = 128;
                        if (ip.netmask6 != null && ip.netmask6.contains("/")) {
                            String[] parts = ip.netmask6.split("/", 2);
                            address6 = parts[0];
                            prefix6 = Integer.parseInt(parts[1]);
                        }
                        List<String> dns = new ArrayList<>(ip.DNS);
                        ParcelFileDescriptor tun = owner.establishCiscoTun(
                                SharedOpenConnectEngine.this,
                                title == null ? "TwinConnect Cisco" : title,
                                ip.addr, prefix, ip.MTU > 0 ? ip.MTU : 1300,
                                dns, address6, prefix6);
                        AxeOpenConnectVpnService.assignedVpnIpv4 = ip.addr;
                        return tun;
                    } catch (Exception error) {
                        // Native core reports CISCO_NATIVE_TUN_FAILED and
                        // the shared service preserves any requested block.
                        Log.e(TAG, "CISCO_SHARED_TUN_ESTABLISH_FAILED");
                        return null;
                    }
                }

                @Override public void traffic(long rx, long tx) {
                    AxeOpenConnectVpnService.bytesReceived.set(Math.max(0, rx));
                    AxeOpenConnectVpnService.bytesSent.set(Math.max(0, tx));
                }
            }, user, pass, pin, url);
            if (underlayAddress != null) next.useUnderlayAddress(underlayAddress);
            session = next;
            if (stopped) {
                next.stopSession();
                next.destroy();
            }
            else next.start(url);
        } catch (LinkageError linkError) {
            reject(owner, "CISCO_NATIVE_ENGINE_UNAVAILABLE");
        } catch (Exception error) {
            reject(owner, "CISCO_NATIVE_START_FAILED");
        } finally {
            connected = false;
            AxeOpenConnectVpnService.isRunning = false;
            AxeOpenConnectVpnService.assignedVpnIpv4 = "";
            session = null;
            broadcast(owner, AxeOpenConnectVpnService.lastFailureCode.isEmpty()
                    ? "disconnected" : "error");
            owner.onCiscoEngineStopped(this);
        }
    }

    public void stop() {
        stopped = true;
        NativeOpenConnectSession running = session;
        if (running != null) running.stopSession();
    }

    private static int prefixFromNetmask(String mask) throws Exception {
        byte[] bytes = InetAddress.getByName(mask).getAddress();
        if (bytes.length != 4) throw new IllegalArgumentException("CISCO_INVALID_MASK");
        int prefix = 0;
        boolean sawZero = false;
        for (byte b : bytes) {
            for (int bit = 7; bit >= 0; bit--) {
                boolean one = ((b >> bit) & 1) != 0;
                if (one && sawZero) throw new IllegalArgumentException("CISCO_INVALID_MASK");
                if (one) prefix++; else sawZero = true;
            }
        }
        if (prefix == 0) throw new IllegalArgumentException("CISCO_INVALID_MASK");
        return prefix;
    }
}
