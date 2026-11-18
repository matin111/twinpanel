package com.axevpn.flutter.openconnect;

import android.net.VpnService;
import android.os.ParcelFileDescriptor;
import android.util.Log;
import java.net.InetAddress;
import java.security.MessageDigest;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.io.ByteArrayInputStream;
import java.util.Arrays;
import java.net.URI;
import java.util.List;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;
import android.net.http.X509TrustManagerExtensions;
import org.infradead.libopenconnect.LibOpenConnect;

/**
 * Experimental real libopenconnect transport. No hand-written CSTP authentication
 * or packet forwarding. Only supports a single username/password form and pins.
 * All unexpected challenges fail closed; never accept arbitrary server certs.
 */
final class NativeOpenConnectSession extends LibOpenConnect {
    interface Listener {
        void stage(String state, String error);
        ParcelFileDescriptor establish(IPInfo ip);
        void traffic(long received, long sent);
    }

    private static final String TAG = "TwinNativeOpenConnect";
    private final VpnService service;
    private final Listener listener;
    private final String username;
    private final String password;
    private final byte[] expectedPin;
    private final boolean spkiPin;
    private final String serverHost;
    private String gatewayAddress;
    private ParcelFileDescriptor tun;
    private volatile boolean stopped;

    NativeOpenConnectSession(VpnService service, Listener listener,
                              String username, String password, String pin, String serverUrl) throws Exception {
        super("TwinConnect Android OpenConnect/1.0");
        this.service = service;
        this.listener = listener;
        this.username = username;
        this.password = password;
        this.serverHost = new URI(serverUrl).getHost();
        if (serverHost == null || serverHost.isEmpty()) throw new IllegalArgumentException("CISCO_GATEWAY_INVALID");
        if (pin == null || pin.isEmpty()) {
            spkiPin = false;
            expectedPin = null;
        } else if (pin.startsWith("pin-sha256:")) {
            spkiPin = true;
            expectedPin = android.util.Base64.decode(pin.substring(11), android.util.Base64.DEFAULT);
        } else if (pin.matches("[0-9a-fA-F]{64}")) {
            spkiPin = false;
            expectedPin = new byte[32];
            for (int i = 0; i < 32; i++) {
                expectedPin[i] = (byte) Integer.parseInt(pin.substring(i * 2, i * 2 + 2), 16);
            }
        } else {
            throw new IllegalArgumentException("CISCO_CERT_PIN_INVALID");
        }
        if (expectedPin != null && expectedPin.length != 32) throw new IllegalArgumentException("CISCO_CERT_PIN_INVALID");
    }

    /** Use pre-resolved underlay IP while preserving the original TLS SNI/pin. */
    void useUnderlayAddress(String address) {
        gatewayAddress = address;
    }

    @Override public int onProcessAuthForm(AuthForm form) {
        if (stopped || username == null || password == null) return OC_FORM_RESULT_ERR;
        if (form.authgroupOpt != null) return OC_FORM_RESULT_ERR;
        boolean suppliedUsername = false, suppliedPassword = false;
        for (FormOpt opt : form.opts) {
            if (opt.type == OC_FORM_OPT_HIDDEN) continue;
            if ("username".equalsIgnoreCase(opt.name) && opt.type == OC_FORM_OPT_TEXT) {
                opt.value = username;
                suppliedUsername = true;
            } else if ("password".equalsIgnoreCase(opt.name) && opt.type == OC_FORM_OPT_PASSWORD) {
                opt.value = password;
                suppliedPassword = true;
            } else {
                // Reject MFA, SSO, group selection and unrecognized prompts.
                return OC_FORM_RESULT_ERR;
            }
        }
        return suppliedUsername || suppliedPassword ? OC_FORM_RESULT_OK : OC_FORM_RESULT_ERR;
    }

    @Override public int onValidatePeerCert(String reason) {
        try {
            byte[] der = getPeerCertDER();
            if (der == null || der.length == 0) return -1;
            if (expectedPin == null) {
                // Android platform CA + hostname verification, never trust-all.
                byte[][] chainDer = getPeerCertChain();
                if (chainDer == null || chainDer.length == 0) return -1;
                X509Certificate[] chain = new X509Certificate[chainDer.length];
                for (int i = 0; i < chainDer.length; i++) {
                    chain[i] = (X509Certificate) CertificateFactory.getInstance("X.509")
                            .generateCertificate(new ByteArrayInputStream(chainDer[i]));
                }
                TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm());
                tmf.init((java.security.KeyStore) null);
                for (javax.net.ssl.TrustManager manager : tmf.getTrustManagers()) {
                    if (manager instanceof X509TrustManager) {
                        new X509TrustManagerExtensions((X509TrustManager) manager)
                                .checkServerTrusted(chain, chain[0].getPublicKey().getAlgorithm(), serverHost);
                        return 0;
                    }
                }
                return -1;
            }
            byte[] fingerprint;
            if (spkiPin) {
                X509Certificate cert = (X509Certificate) CertificateFactory.getInstance("X.509")
                        .generateCertificate(new ByteArrayInputStream(der));
                fingerprint = MessageDigest.getInstance("SHA-256").digest(cert.getPublicKey().getEncoded());
            } else {
                fingerprint = MessageDigest.getInstance("SHA-256").digest(der);
            }
            return MessageDigest.isEqual(fingerprint, expectedPin) ? 0 : -1;
        } catch (Exception ex) {
            Log.w(TAG, "Certificate verification failed");
            return -1;
        }
    }

    @Override public void onProtectSocket(int fd) {
        if (!service.protect(fd)) {
            listener.stage("error", "CISCO_SOCKET_PROTECTION_FAILED");
            cancel();
        }
    }

    @Override public void onProgress(int level, String msg) {
        // Never log raw library messages: they can contain hosts, credentials
        // or server-provided text. Only coarse categories are emitted.
        if (msg == null) return;
        final String event = msg.toLowerCase(java.util.Locale.ROOT);
        if (event.contains("established dtls connection") ||
                event.contains("dtls connected")) {
            Log.i(TAG, "CISCO_TRANSPORT_DTLS_ESTABLISHED");
        } else if (event.contains("dtls") &&
                (event.contains("failed") || event.contains("error") ||
                 event.contains("timeout") || event.contains("unavailable"))) {
            Log.w(TAG, "CISCO_TRANSPORT_DTLS_FAILED_OR_UNAVAILABLE");
        } else if (level == PRG_ERR) {
            final String category =
                    event.contains("dtls") || event.contains("udp") ? "DTLS_UDP" :
                    event.contains("cstp") || event.contains("tcp") ? "CSTP_TCP" :
                    event.contains("certificate") || event.contains("tls") ? "TLS" :
                    event.contains("tun") || event.contains("packet") ? "TUN_PACKET" :
                    event.contains("timeout") || event.contains("timed out") ? "TIMEOUT" :
                    event.contains("dns") || event.contains("resolve") ? "DNS" :
                    event.contains("reconnect") ? "RECONNECT" : "OTHER";
            Log.w(TAG, "CISCO_NATIVE_TRANSPORT_ERROR category=" + category);
        }
    }

    private long lastTrafficLogAtMs;

    @Override public void onStatsUpdate(VPNStats stats) {
        if (stats == null) return;
        listener.traffic(stats.rxBytes, stats.txBytes);
        // Counters are non-sensitive and help distinguish blackholed return
        // traffic from broken DNS/HTTPS. Throttle diagnostic logs.
        long now = android.os.SystemClock.elapsedRealtime();
        if (now - lastTrafficLogAtMs >= 15000) {
            lastTrafficLogAtMs = now;
            Log.i(TAG, "CISCO_TUN_COUNTERS tx=" + Math.max(0, stats.txBytes)
                    + " rx=" + Math.max(0, stats.rxBytes));
        }
    }

    void start(String serverUrl) {
        String failure = "CISCO_NATIVE_START_FAILED";
        try {
            setProtocol("anyconnect");
            setXMLPost(true);
            setReportedOS("android");
            // Do not disable peer certificate validation or leak credentials to logs.
            if (parseURL(serverUrl) != 0) throw new IllegalStateException("URL");
            if (gatewayAddress != null) {
                setSNI(serverHost);
                setHostname(gatewayAddress);
            }
            listener.stage("authenticating", "");
            failure = "CISCO_NATIVE_AUTH_FAILED";
            if (obtainCookie() != 0 || stopped) throw new IllegalStateException("AUTH");
            listener.stage("connecting", "");
            failure = "CISCO_NATIVE_CSTP_FAILED";
            if (makeCSTPConnection() != 0 || stopped) throw new IllegalStateException("CSTP");
            IPInfo ip = getIPInfo();
            failure = "CISCO_NATIVE_TUN_FAILED";
            if (ip == null) throw new IllegalStateException("NO_IP");
            tun = listener.establish(ip);
            if (tun == null || setupTunFD(tun.getFd()) != 0 || stopped) {
                throw new IllegalStateException("TUN");
            }
            listener.stage("connected", "");
            // DTLS/UDP is the preferred high-throughput data path. A working
            // CSTP/TCP session alone is not proof that UDP was established.
            // Do not fail or restart a healthy TCP tunnel if the UDP probe
            // fails: record a non-sensitive diagnostic for device comparison.
            final int dtlsSetup = setupDTLS(60);
            if (dtlsSetup != 0) {
                Log.w(TAG, "CISCO_TRANSPORT_DTLS_SETUP_UNAVAILABLE code=" + dtlsSetup);
            } else {
                Log.i(TAG, "CISCO_TRANSPORT_DTLS_SETUP_REQUESTED");
            }
            // libopenconnect.mainloop() blocks while handling the tunnel.
            // Stats must be requested from another thread, otherwise they
            // remain at zero during a healthy long-running connection.
            Thread statsPoller = new Thread(() -> {
                while (!stopped) {
                    try {
                        Thread.sleep(1000);
                        if (!stopped) requestStats();
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        break;
                    } catch (RuntimeException failureToPoll) {
                        break;
                    }
                }
            }, "oc-native-stats");
            statsPoller.setDaemon(true);
            statsPoller.start();
            failure = "CISCO_NATIVE_LOOP_FAILED";
            while (!stopped && mainloop(300, RECONNECT_INTERVAL_MIN) >= 0) {
                // Keep all packet processing on the OpenConnect tunnel thread.
            }
            if (!stopped) listener.stage("error", failure);
        } catch (Exception ex) {
            if (!stopped) listener.stage("error", failure);
        } finally {
            stopped = true;
            if (tun != null) try { tun.close(); } catch (Exception ignored) {}
            destroy();
        }
    }

    void stopSession() {
        stopped = true;
        cancel();
    }
}

