package com.twinpanel.twinconnect

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import androidx.core.content.ContextCompat
import android.provider.Settings
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
    private var pendingAwgStart: Pair<String, MethodChannel.Result>? = null
    private var pendingGuardStart: MethodChannel.Result? = null

    private data class PendingStart(
        val config: String,
        val policy: Map<String, Any?>,
        val result: MethodChannel.Result
    )

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // The upstream package auto-registers only its OpenVPN plugin.
        // Register the independent CSTP/Cisco Android plugin explicitly.
        flutterEngine.plugins.add(com.axevpn.flutter.openconnect.OpenConnectFlutterPlugin())
        val channel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "com.twinpanel.twinconnect/vpn"
        )
        // Mieru is not a VPN until its SOCKS engine and TUN forwarder are
        // installed together. Never claim a successful connection based on
        // a compiled executable or an open local SOCKS socket.
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "com.twinpanel.twinconnect/mieru"
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "getCapabilities" -> result.success(
                    mapOf(
                        "contractVersion" to 1,
                        "engineReady" to false,
                        "tunnelVerified" to false,
                        "reason" to "MIERU_TUN_BRIDGE_NOT_INSTALLED"
                    )
                )
                "connect" -> result.error(
                    "MIERU_TUN_BRIDGE_NOT_INSTALLED",
                    "Mieru requires a native SOCKS engine and Android TUN forwarder",
                    null
                )
                "disconnect" -> result.success(
                    mapOf("connected" to false, "tunnelVerified" to false)
                )
                else -> result.notImplemented()
            }
        }
        // Fail closed until the Rust TrustTunnel engine and TUN forwarder are
        // actually bundled. A SOCKS listener alone is not a device VPN.
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "com.twinpanel.twinconnect/trusttunnel"
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "getCapabilities" -> result.success(
                    mapOf(
                        "contractVersion" to 1,
                        "engineReady" to false,
                        "vpnServiceReady" to false,
                        "tunnelVerified" to false,
                        "reason" to "TRUSTTUNNEL_NATIVE_ENGINE_NOT_INSTALLED"
                    )
                )
                "connect" -> result.error(
                    "TRUSTTUNNEL_NATIVE_ENGINE_NOT_INSTALLED",
                    "Rust TrustTunnel client and Android TUN bridge are required",
                    null
                )
                "disconnect" -> result.success(
                    mapOf("connected" to false, "tunnelVerified" to false)
                )
                else -> result.notImplemented()
            }
        }
        // AWG is an optional isolated AAR. Reflective dispatch keeps the
        // standard WireGuard-only APK buildable when AWG is not staged.
        val awgRuntime = try {
            Class.forName("com.twinpanel.twinconnect.AmneziaWgRuntime")
        } catch (_: ClassNotFoundException) {
            null
        }
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "com.twinpanel.twinconnect/amneziawg"
        ).setMethodCallHandler { call, result ->
            if (call.method == "connect" && awgRuntime != null) {
                val config = call.argument<String>("config")
                if (config.isNullOrBlank()) {
                    result.error("AWG_PROFILE_MISSING", "Missing VPN profile", null)
                } else if (pendingAwgStart != null) {
                    result.error("AWG_PERMISSION_PENDING", "VPN permission pending", null)
                } else {
                    val approval = VpnService.prepare(this)
                    if (approval != null) {
                        pendingAwgStart = Pair(config, result)
                        try {
                            @Suppress("DEPRECATION")
                            startActivityForResult(approval, AWG_APPROVAL_REQUEST)
                        } catch (_: Exception) {
                            pendingAwgStart = null
                            result.error("VPN_PERMISSION_FAILED", "Unable to request permission", null)
                        }
                    } else {
                        launchAmneziaWg(awgRuntime, config, result)
                    }
                }
            } else onWorker(result) {
                if (awgRuntime == null) {
                    if (call.method == "getCapabilities") {
                        mapOf(
                            "contractVersion" to 1,
                            "engineReady" to false,
                            "vpnServiceReady" to false,
                            "tunnelVerified" to false,
                            "reason" to "AWG_NATIVE_BACKEND_NOT_BUNDLED"
                        )
                    } else {
                        throw IllegalArgumentException("AWG_NATIVE_BACKEND_NOT_BUNDLED")
                    }
                } else {
                    try {
                        val instance = awgRuntime.getField("INSTANCE").get(null)
                        when (call.method) {
                            "getCapabilities" -> {
                                val ready = awgRuntime.getMethod(
                                    "initialize", Context::class.java
                                ).invoke(instance, applicationContext) == true
                                mapOf(
                                    "contractVersion" to 1,
                                    "engineReady" to ready,
                                    "vpnServiceReady" to ready,
                                    "tunnelVerified" to false
                                )
                            }
                            "status" -> {
                                @Suppress("UNCHECKED_CAST")
                                (awgRuntime.getMethod("status").invoke(instance)
                                    as Map<String, Any>)
                            }
                            "connect" -> throw IllegalArgumentException("AWG_CONNECT_DISPATCH_ERROR")
                            "disconnect" -> {
                                @Suppress("UNCHECKED_CAST")
                                (awgRuntime.getMethod("disconnect").invoke(instance)
                                    as Map<String, Any>)
                            }
                            else -> throw IllegalArgumentException("AWG_UNKNOWN_METHOD")
                        }
                    } catch (_: ReflectiveOperationException) {
                        throw IllegalArgumentException("AWG_NATIVE_RUNTIME_FAILED")
                    } catch (_: LinkageError) {
                        throw IllegalArgumentException("AWG_NATIVE_RUNTIME_FAILED")
                    }
                }
            }
        }
        channel.setMethodCallHandler { call, result ->
            when (call.method) {
                "getDisconnectedTrafficGuardStatus" -> {
                    val wireGuardUp = WireGuardRuntime.isInterfaceUp()
                    val legacyGuardUp = AndroidTrafficGuardService.active
                    val anyVpnUp = hasActiveVpnTransport()
                    val verifiedLockdown = if (wireGuardUp)
                        WireGuardRuntime.isOsLockdownEnforced() else null
                    result.success(mapOf(
                        "active" to legacyGuardUp,
                        "osLockdown" to verifiedLockdown,
                        "lockdownVerificationAvailable" to wireGuardUp,
                        "otherVpnActive" to (anyVpnUp && !legacyGuardUp),
                        // A running VPN is not evidence of leak prevention.
                        // Only report protection when native lockdown is verified.
                        "protectionVerified" to (verifiedLockdown == true),
                        "protectionMode" to when {
                            verifiedLockdown == true -> "OS_LOCKDOWN_VERIFIED"
                            legacyGuardUp -> "LEGACY_BLOCKING_TUN_UNSAFE_HANDOFF"
                            anyVpnUp -> "ACTIVE_VPN_LOCKDOWN_UNVERIFIED"
                            else -> "DISCONNECTED_UNPROTECTED"
                        },
                        "singleTunnelKillSwitchAvailable" to false,
                        "failClosedAcrossHandoff" to false
                    ))
                }
                "startDisconnectedTrafficGuard" -> {
                    // A separate VpnService steals Android's single VPN slot from the
                    // selected protocol. Do not offer a fake kill switch with an
                    // unprotected handoff window or interrupt a healthy tunnel.
                    result.error(
                        "KILL_SWITCH_REQUIRES_SINGLE_TUN",
                        "A fail-closed kill switch must be enforced by the active VPN engine or Android lockdown; a second VpnService is unsafe",
                        null
                    )
                }
                "stopDisconnectedTrafficGuard" -> {
                    startService(Intent(this, AndroidTrafficGuardService::class.java).apply {
                        action = AndroidTrafficGuardService.ACTION_STOP
                    })
                    result.success(mapOf("stopRequested" to true))
                }
                "openAndroidVpnSettings" -> {
                    try {
                        startActivity(Intent(Settings.ACTION_VPN_SETTINGS))
                        result.success(mapOf("opened" to true))
                    } catch (_: Exception) {
                        result.error("ANDROID_VPN_SETTINGS_UNAVAILABLE", "Unable to open Android VPN settings", null)
                    }
                }
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
                "forgetSingBoxEphemeralConfig" -> onWorker(result) {
                    // sing_box currently persists a clear-text last_config.json
                    // and the last outbound in SharedPreferences. TwinConnect
                    // must never retain credentials across tenant sessions.
                    val prefs = applicationContext.getSharedPreferences(
                        "sing_box", Context.MODE_PRIVATE
                    )
                    val cleared = prefs.edit().remove("sing_box.last_input").commit()
                    val config = java.io.File(
                        applicationContext.filesDir, "sing-box/last_config.json"
                    )
                    val removed = !config.exists() || config.delete()
                    if (!cleared || !removed) {
                        throw IllegalArgumentException("PROFILE_PURGE_FAILED")
                    }
                    mapOf("purged" to true)
                }
                // Dedicated Cisco API. Not backed by WireGuard. An Android
                // OpenConnect VpnService + reviewed native core is required
                // before enabling this protocol's native capability.
                "getOpenConnectStatus" -> onWorker(result) {
                    mapOf(
                        "protocol" to "cisco",
                        "state" to "unavailable",
                        "engineReady" to false,
                        "trafficRoutingVerified" to false
                    )
                }
                "startOpenConnect" -> {
                    // Fail BEFORE opening credentials or starting another
                    // transport. Never report Cisco as a WireGuard tunnel.
                    result.error(
                        "OPENCONNECT_CORE_NOT_INSTALLED",
                        "Dedicated OpenConnect Android core is not installed",
                        null
                    )
                }
                "stopOpenConnect" -> onWorker(result) {
                    mapOf("protocol" to "cisco", "state" to "down")
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

    private fun launchAmneziaWg(
        runtime: Class<*>,
        configuration: String,
        result: MethodChannel.Result
    ) {
        onWorker(result) {
            try {
                val instance = runtime.getField("INSTANCE").get(null)
                @Suppress("UNCHECKED_CAST")
                runtime.getMethod(
                    "connect", Context::class.java, String::class.java
                ).invoke(instance, applicationContext, configuration) as Map<String, Any>
            } catch (error: java.lang.reflect.InvocationTargetException) {
                // Reflection wraps the runtime's policy and configuration errors.
                // Preserve only allowlisted symbolic codes, never the exception
                // text from the native backend (which may contain credentials).
                val cause = error.targetException
                val safeCodes = setOf(
                    "AWG_ENGINE_UNAVAILABLE", "VPN_PERMISSION_REQUIRED",
                    "OTHER_VPN_ACTIVE", "AWG_ALREADY_CONNECTED",
                    "AWG_PROFILE_INVALID", "AWG_DNS_MISSING",
                    "AWG_DEFAULT_ROUTE_MISSING", "AWG_CONFIG_PARSE_FAILED",
                    "AWG_NATIVE_START_FAILED", "AWG_TUN_NOT_ESTABLISHED",
                    "AWG_VPN_SERVICE_TIMEOUT", "AWG_TUN_CREATION_FAILED",
                    "AWG_GO_ACTIVATION_FAILED", "AWG_ENDPOINT_DNS_FAILED",
                    "AWG_BACKEND_REJECTED", "AWG_BACKEND_START_EXCEPTION",
                    "AWG_NATIVE_LINK_FAILED", "AWG_VPN_SECURITY_REJECTED"
                )
                val code = cause.message?.takeIf { it in safeCodes }
                    ?: when (cause) {
                        is UnsatisfiedLinkError, is NoClassDefFoundError ->
                            "AWG_NATIVE_LINK_FAILED"
                        is SecurityException -> "AWG_VPN_SECURITY_REJECTED"
                        is IllegalStateException -> "AWG_BACKEND_STATE_FAILED"
                        else -> "AWG_BACKEND_START_EXCEPTION"
                    }
                throw IllegalArgumentException(code)
            } catch (_: ReflectiveOperationException) {
                throw IllegalArgumentException("AWG_NATIVE_REFLECTION_FAILED")
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
                    "WIREGUARD_CONFIG_PARSE_FAILED", "WIREGUARD_NATIVE_START_FAILED",
                    "PROFILE_PURGE_FAILED", "AWG_NATIVE_START_FAILED",
                    "AWG_NATIVE_BACKEND_NOT_BUNDLED", "AWG_PROFILE_MISSING",
                    "AWG_ENGINE_UNAVAILABLE", "AWG_PROFILE_INVALID",
                    "AWG_DNS_MISSING", "AWG_DEFAULT_ROUTE_MISSING",
                    "AWG_CONFIG_PARSE_FAILED", "AWG_TUN_NOT_ESTABLISHED",
                    "AWG_ALREADY_CONNECTED", "OTHER_VPN_ACTIVE",
                    "AWG_NATIVE_RUNTIME_FAILED", "AWG_UNKNOWN_METHOD",
                    "AWG_CONNECT_DISPATCH_ERROR", "AWG_NATIVE_LINK_FAILED",
                    "AWG_VPN_SECURITY_REJECTED", "AWG_BACKEND_STATE_FAILED",
                    "AWG_BACKEND_START_EXCEPTION", "AWG_NATIVE_REFLECTION_FAILED"
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
        if (requestCode == GUARD_APPROVAL_REQUEST) {
            val request = pendingGuardStart ?: return
            pendingGuardStart = null
            if (resultCode == Activity.RESULT_OK && !hasActiveVpnTransport()) {
                ContextCompat.startForegroundService(this, Intent(this, AndroidTrafficGuardService::class.java))
                request.success(mapOf("requested" to true, "verified" to false))
            } else {
                request.error("VPN_PERMISSION_DENIED_OR_CONFLICT", "VPN permission denied or another VPN became active", null)
            }
            return
        }
        if (requestCode == AWG_APPROVAL_REQUEST) {
            val request = pendingAwgStart ?: return
            pendingAwgStart = null
            if (resultCode == Activity.RESULT_OK) {
                val runtime = try {
                    Class.forName("com.twinpanel.twinconnect.AmneziaWgRuntime")
                } catch (_: ClassNotFoundException) {
                    null
                }
                if (runtime == null) {
                    request.second.error("AWG_NATIVE_BACKEND_NOT_BUNDLED", "AWG engine missing", null)
                } else {
                    launchAmneziaWg(runtime, request.first, request.second)
                }
            } else {
                request.second.error("VPN_PERMISSION_DENIED", "VPN permission not granted", null)
            }
            return
        }
        if (requestCode != VPN_APPROVAL_REQUEST) return
        val request = pendingStart ?: return
        pendingStart = null
        if (resultCode == Activity.RESULT_OK) {
            launchWireGuard(request.config, request.policy, request.result)
        } else {
            request.result.error("VPN_PERMISSION_DENIED", "VPN permission not granted", null)
        }
    }

    private fun hasActiveVpnTransport(): Boolean {
        val connectivity = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        return try {
            connectivity.allNetworks.any { network ->
                connectivity.getNetworkCapabilities(network)
                    ?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true
            }
        } catch (_: SecurityException) {
            // If the OS denies inspection, never replace an unknown active VPN.
            true
        }
    }

    override fun onDestroy() {
        pendingGuardStart?.error("VPN_REQUEST_CANCELLED", "VPN approval activity closed", null)
        pendingGuardStart = null
        pendingStart?.result?.error(
            "VPN_REQUEST_CANCELLED", "VPN approval activity closed", null
        )
        pendingStart = null
        pendingAwgStart?.second?.error("VPN_REQUEST_CANCELLED", "VPN approval activity closed", null)
        pendingAwgStart = null
        executor.shutdown()
        // Do not tear down a VPN on ordinary UI destruction. The user's
        // explicit Disconnect and OS VPN revocation own that lifecycle.
        super.onDestroy()
    }

    companion object {
        private const val VPN_APPROVAL_REQUEST = 44011
        private const val AWG_APPROVAL_REQUEST = 44012
        private const val GUARD_APPROVAL_REQUEST = 44013
    }
}
