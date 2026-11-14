package com.twinpanel.twinconnect

import android.app.Activity
import android.content.Intent
import android.net.VpnService
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * One Android VPN owner at a time.
 *
 * This activity never logs profile contents; native VPN approval is required.
 * Protocol capabilities are reported only after WireGuard's actual JNI engine
 * loads. Cisco/OpenConnect is explicitly disabled until libopenconnect's
 * TUN bridge is built and tested (a Cisco login is not a WireGuard profile).
 */
class MainActivity : FlutterActivity() {
    private val executor: ExecutorService = Executors.newSingleThreadExecutor()
    private var pendingStart: PendingStart? = null

    private data class PendingStart(
        val config: String,
        val policy: Map<String, Any?>,
        val result: MethodChannel.Result
    )

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val channel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "com.twinpanel.twinconnect/vpn"
        )
        channel.setMethodCallHandler { call, result ->
            when (call.method) {
                "getCapabilities" -> onWorker(result) {
                    val present = WireGuardRuntime.initialize(applicationContext)
                    mapOf(
                        "contractVersion" to 1,
                        "engineReady" to present,
                        "fullTunnel" to present,
                        "includeApps" to false,
                        "excludeApps" to false,
                        "killSwitchEnforced" to (present && WireGuardRuntime.isOsLockdownEnforced()),
                        // These indicate native, profile-validated capability,
                        // NOT a claim that DNS/IPv6 protection is now active.
                        "dnsGuard" to present,
                        "ipv6Guard" to present,
                        "localNetworkBypass" to false,
                        "autoConnect" to false,
                        "autoReconnect" to false,
                        "managedDevice" to false
                    )
                }
                "getProtocolCapabilities" -> onWorker(result) {
                    val present = WireGuardRuntime.initialize(applicationContext)
                    mapOf(
                        "contractVersion" to 1,
                        "supportedProtocols" to if (present) listOf("wireguard") else emptyList<String>()
                    )
                }
                "getTunnelStatus" -> onWorker(result) {
                    WireGuardRuntime.status()
                }
                "startTunnel" -> {
                    if (call.argument<String>("protocol") != "wireguard") {
                        result.error("PROTOCOL_ENGINE_NOT_READY", "Unsupported native protocol", null)
                        return@setMethodCallHandler
                    }
                    val configuration = call.argument<String>("config")
                    @Suppress("UNCHECKED_CAST")
                    val policy = call.argument<Map<String, Any?>>("policy")
                    if (configuration.isNullOrBlank() || policy == null) {
                        result.error("PROFILE_INVALID", "Missing native tunnel parameters", null)
                        return@setMethodCallHandler
                    }
                    if (pendingStart != null) {
                        result.error("VPN_REQUEST_IN_PROGRESS", "Approval already in progress", null)
                        return@setMethodCallHandler
                    }
                    val launch = VpnService.prepare(this)
                    if (launch == null) {
                        launchWireGuard(configuration, policy, result)
                    } else {
                        pendingStart = PendingStart(configuration, policy, result)
                        try {
                            @Suppress("DEPRECATION")
                            startActivityForResult(launch, VPN_APPROVAL_REQUEST)
                        } catch (_: Exception) {
                            pendingStart = null
                            result.error("VPN_PERMISSION_FAILED", "Unable to request permission", null)
                        }
                    }
                }
                "stopTunnel" -> onWorker(result) {
                    WireGuardRuntime.stop()
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun launchWireGuard(
        configuration: String,
        policy: Map<String, Any?>,
        result: MethodChannel.Result
    ) {
        onWorker(result) {
            WireGuardRuntime.start(applicationContext, configuration, policy)
        }
    }

    private fun onWorker(
        result: MethodChannel.Result,
        work: () -> Map<String, Any>
    ) {
        executor.execute {
            try {
                val response = work()
                runOnUiThread { result.success(response) }
            } catch (error: IllegalArgumentException) {
                // Return only static policy errors, never profile/secret contents.
                val accepted = setOf(
                    "PROFILE_INVALID", "PRIVATE_KEY_MISSING", "VPN_DNS_MISSING",
                    "VPN_ADDRESS_MISSING", "IPV4_DEFAULT_ROUTE_MISSING",
                    "IPV6_DEFAULT_ROUTE_MISSING", "WIREGUARD_ENGINE_UNAVAILABLE",
                    "VPN_PERMISSION_REQUIRED", "PER_APP_ROUTING_NOT_IMPLEMENTED",
                    "DNS_POLICY_NOT_SUPPORTED", "IPV6_POLICY_NOT_SUPPORTED",
                    "LAN_BYPASS_NOT_IMPLEMENTED", "AUTOCONNECT_NOT_IMPLEMENTED",
                    "AUTO_RECONNECT_NOT_VERIFIED", "OS_LOCKDOWN_NOT_ENABLED",
                    "TUNNEL_ALREADY_RUNNING", "TUNNEL_NOT_ESTABLISHED",
                    "WIREGUARD_CONFIG_PARSE_FAILED", "WIREGUARD_NATIVE_START_FAILED"
                )
                val safeCode = error.message?.takeIf { accepted.contains(it) }
                    ?: "NATIVE_VPN_START_FAILED"
                runOnUiThread { result.error(safeCode, "Native VPN policy rejected", null) }
            } catch (_: Exception) {
                runOnUiThread { result.error("NATIVE_VPN_START_FAILED", "Native VPN failure", null) }
            } catch (_: LinkageError) {
                runOnUiThread { result.error("NATIVE_ENGINE_LINK_FAILED", "Missing WireGuard native library", null) }
            }
        }
    }

    @Deprecated("Deprecated by Android API; required for FlutterActivity's approval callback")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != VPN_APPROVAL_REQUEST) return
        val request = pendingStart ?: return
        pendingStart = null
        if (resultCode == Activity.RESULT_OK) {
            launchWireGuard(request.config, request.policy, request.result)
        } else {
            request.result.error("VPN_PERMISSION_DENIED", "VPN permission not granted", null)
        }
    }

    override fun onDestroy() {
        pendingStart?.result?.error(
            "VPN_REQUEST_CANCELLED", "VPN approval activity closed", null
        )
        pendingStart = null
        executor.shutdown()
        // Do not tear down a VPN on ordinary UI destruction. The user's
        // explicit Disconnect and OS VPN revocation own that lifecycle.
        super.onDestroy()
    }

    companion object {
        private const val VPN_APPROVAL_REQUEST = 44011
    }
}
