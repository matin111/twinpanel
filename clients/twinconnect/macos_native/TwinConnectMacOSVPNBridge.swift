// macOS native capabilities are derived from the installed extension and
// its real protocol backend marker. Installing an .appex alone is never proof
// of a working VPN. Native controls are fail-closed until backend integration.
import Foundation
import Security

final class TwinConnectMacOSVPNBridge {
    private static func extensionBundle() -> Bundle? {
        guard let plugins = Bundle.main.builtInPlugInsPath else { return nil }
        let url = URL(fileURLWithPath: plugins)
            .appendingPathComponent("PacketTunnel.appex", isDirectory: true)
        guard let bundle = Bundle(url: url),
              bundle.bundleIdentifier == "com.twinpanel.twinconnect.PacketTunnel" else {
            return nil
        }
        return bundle
    }

    private static func xrayEngineInstalled() -> Bool {
        let executable = Bundle.main.bundleURL.appendingPathComponent(
            "Contents/Resources/TwinConnectEngines/xray")
        return FileManager.default.isExecutableFile(atPath: executable.path)
    }

    private static func libboxInExtension() -> Bool {
        guard let bundle = extensionBundle() else { return false }
        let path = bundle.bundleURL.appendingPathComponent(
            "Contents/Frameworks/Libbox.framework/Libbox")
        return FileManager.default.fileExists(atPath: path.path)
    }

    private static func hysteriaEngineInstalled() -> Bool {
        let root = Bundle.main.bundleURL.appendingPathComponent(
            "Contents/Resources/TwinConnectEngines/sing-box")
        guard FileManager.default.isExecutableFile(atPath: root.path) else {
            return false
        }
        // A bundled binary is useful for profile preflight only. Native
        // PacketTunnel packetFlow forwarding is a separate requirement.
        return true
    }

    private static func wireGuardBackendReady() -> Bool {
        // WireGuardKit's Go bridge is not in the shipping PacketTunnel.
        return false
    }

    private static func libboxBackendReady() -> Bool {
        // CI builds are unsigned and must never report VPN readiness.
        // Production may enable this only after a signed/manual egress test,
        // with both the app and extension provisioned for NetworkExtension.
        #if TWINCONNECT_SIGNED_LIBBOX
        guard let bundle = extensionBundle(),
              bundle.object(forInfoDictionaryKey:
                  "TwinConnectProtocolBackendLinked") as? Bool == true,
              libboxInExtension(),
              let task = SecTaskCreateFromSelf(kCFAllocatorDefault),
              let values = SecTaskCopyValueForEntitlement(task,
                  "com.apple.developer.networking.networkextension" as CFString,
                  nil) as? [String],
              values.contains("packet-tunnel-provider") else {
            return false
        }
        return true
        #else
        return false
        #endif
    }

    static func register(binaryMessenger messenger: FlutterBinaryMessenger) {
        let channel = FlutterMethodChannel(
            name: "com.twinpanel.twinconnect/vpn",
            binaryMessenger: messenger
        )
        channel.setMethodCallHandler { call, result in
            switch call.method {
            case "getCapabilities":
                result([
                    "contractVersion": 1,
                    "engineReady": libboxBackendReady(),
                    "fullTunnel": libboxBackendReady(),
                    "includeApps": false,
                    "excludeApps": false,
                    "killSwitchEnforced": false,
                    "dnsGuard": false,
                    "ipv6Guard": false,
                    "localNetworkBypass": false,
                    "autoConnect": false,
                    "autoReconnect": false,
                    "managedDevice": false,
                ] as [String: Any])
            case "getProtocolCapabilities":
                result([
                    "contractVersion": 1,
                    "supportedCodes": libboxBackendReady()
                        ? ["hysteria2", "tuic", "anytls", "naive", "shadowtls"] : [String]()
                ] as [String: Any])
            case "macOSXrayEngineStatus":
                result([
                    "contractVersion": 1,
                    "protocol": "v2ray",
                    "binaryInstalled": xrayEngineInstalled(),
                    "packetFlowBridgeReady": false,
                    "engineReady": false,
                    "reason": xrayEngineInstalled()
                        ? "MACOS_XRAY_PACKET_FLOW_BRIDGE_MISSING"
                        : "MACOS_XRAY_ENGINE_BINARY_MISSING"
                ] as [String: Any])
            case "macOSHysteria2EngineStatus":
                result([
                    "contractVersion": 1,
                    "protocol": "hysteria2",
                    "binaryInstalled": hysteriaEngineInstalled(),
                    "inProcessLibboxBundled": libboxInExtension(),
                    "packetFlowBridgeReady": libboxBackendReady(),
                    "engineReady": libboxBackendReady(),
                    "reason": libboxBackendReady()
                        ? "MACOS_HYSTERIA2_SIGNED_START_UNVERIFIED"
                        : (libboxInExtension()
                            ? "MACOS_HYSTERIA2_SIGNING_OR_ENTITLEMENT_MISSING"
                            : "MACOS_HYSTERIA2_PACKET_FLOW_BRIDGE_MISSING")
                ] as [String: Any])
            case "macOSShadowTlsEngineStatus":
                result([
                    "contractVersion": 1,
                    "protocol": "shadowtls",
                    "inProcessLibboxBundled": libboxInExtension(),
                    "packetFlowBridgeReady": libboxBackendReady(),
                    "engineReady": libboxBackendReady(),
                    "reason": libboxBackendReady()
                        ? "MACOS_SHADOWTLS_SIGNED_START_UNVERIFIED"
                        : (libboxInExtension()
                            ? "MACOS_SHADOWTLS_SIGNING_OR_ENTITLEMENT_MISSING"
                            : "MACOS_SHADOWTLS_PACKET_FLOW_BRIDGE_MISSING")
                ] as [String: Any])
            case "macOSNaiveEngineStatus":
                result([
                    "contractVersion": 1,
                    "protocol": "naive",
                    "inProcessLibboxBundled": libboxInExtension(),
                    "packetFlowBridgeReady": libboxBackendReady(),
                    "engineReady": libboxBackendReady(),
                    "reason": libboxBackendReady()
                        ? "MACOS_NAIVE_SIGNED_START_UNVERIFIED"
                        : (libboxInExtension()
                            ? "MACOS_NAIVE_SIGNING_OR_ENTITLEMENT_MISSING"
                            : "MACOS_NAIVE_PACKET_FLOW_BRIDGE_MISSING")
                ] as [String: Any])
            case "macOSAnyTlsEngineStatus":
                result([
                    "contractVersion": 1,
                    "protocol": "anytls",
                    "inProcessLibboxBundled": libboxInExtension(),
                    "packetFlowBridgeReady": libboxBackendReady(),
                    "engineReady": libboxBackendReady(),
                    "reason": libboxBackendReady()
                        ? "MACOS_ANYTLS_SIGNED_START_UNVERIFIED"
                        : (libboxInExtension()
                            ? "MACOS_ANYTLS_SIGNING_OR_ENTITLEMENT_MISSING"
                            : "MACOS_ANYTLS_PACKET_FLOW_BRIDGE_MISSING")
                ] as [String: Any])
            case "macOSTuicEngineStatus":
                result([
                    "contractVersion": 1,
                    "protocol": "tuic",
                    "inProcessLibboxBundled": libboxInExtension(),
                    "packetFlowBridgeReady": libboxBackendReady(),
                    "engineReady": libboxBackendReady(),
                    "reason": libboxBackendReady()
                        ? "MACOS_TUIC_SIGNED_START_UNVERIFIED"
                        : (libboxInExtension()
                            ? "MACOS_TUIC_SIGNING_OR_ENTITLEMENT_MISSING"
                            : "MACOS_TUIC_PACKET_FLOW_BRIDGE_MISSING")
                ] as [String: Any])
            case "macOSRuntimeStatus":
                let installed = extensionBundle() != nil
                result([
                    "contractVersion": 1,
                    "state": installed ? "backend_not_linked" : "not_installed",
                    "extensionInstalled": installed,
                    "engineReady": false,
                    "connected": false,
                    "reason": installed
                        ? "MACOS_PROTOCOL_BACKEND_NOT_LINKED"
                        : "MACOS_PACKET_TUNNEL_NOT_INSTALLED",
                ] as [String: Any])
            case "startTunnel":
                TwinConnectMacOSVPNControl.start(
                    call.arguments, backendLinked: wireGuardBackendReady(), result: result)
            case "startHysteria2":
                TwinConnectMacOSLibboxControl.start(
                    call.arguments, backendLinked: libboxBackendReady(), result: result)
            case "getHysteria2TunnelStatus":
                TwinConnectMacOSLibboxControl.status(result)
            case "startTuic":
                TwinConnectMacOSLibboxControl.start(
                    call.arguments, backendLinked: libboxBackendReady(),
                    protocolCode: "tuic", result: result)
            case "getTuicTunnelStatus":
                TwinConnectMacOSLibboxControl.status(result, protocolCode: "tuic")
            case "startAnyTls":
                TwinConnectMacOSLibboxControl.start(
                    call.arguments, backendLinked: libboxBackendReady(),
                    protocolCode: "anytls", result: result)
            case "getAnyTlsTunnelStatus":
                TwinConnectMacOSLibboxControl.status(result, protocolCode: "anytls")
            case "startShadowTls":
                TwinConnectMacOSLibboxControl.start(
                    call.arguments, backendLinked: libboxBackendReady(),
                    protocolCode: "shadowtls", result: result)
            case "getShadowTlsTunnelStatus":
                TwinConnectMacOSLibboxControl.status(result, protocolCode: "shadowtls")
            case "startNaive":
                TwinConnectMacOSLibboxControl.start(
                    call.arguments, backendLinked: libboxBackendReady(),
                    protocolCode: "naive", result: result)
            case "getNaiveTunnelStatus":
                TwinConnectMacOSLibboxControl.status(result, protocolCode: "naive")
            case "stopTunnel":
                TwinConnectMacOSVPNControl.stop(result)
            case "getTunnelStatus":
                TwinConnectMacOSVPNControl.status(result)
            default:
                result(FlutterMethodNotImplemented)
            }
        }
    }
}
