// macOS native capabilities are derived from the installed extension and
// its real protocol backend marker. Installing an .appex alone is never proof
// of a working VPN. Native controls are fail-closed until backend integration.
import Foundation

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

    private static func backendReady() -> Bool {
        // Additional signed entitlement and runtime checks are mandatory
        // before this can be used to enable actual connections.
        return false
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
                    "engineReady": false,
                    "fullTunnel": false,
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
                    "supportedCodes": [String]()
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
                    "packetFlowBridgeReady": false,
                    "engineReady": false,
                    "reason": hysteriaEngineInstalled()
                        ? "MACOS_HYSTERIA2_PACKET_FLOW_BRIDGE_MISSING"
                        : "MACOS_HYSTERIA2_ENGINE_BINARY_MISSING"
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
                    call.arguments, backendLinked: backendReady(), result: result)
            case "startHysteria2":
                TwinConnectMacOSLibboxControl.start(
                    call.arguments, backendLinked: backendReady(), result: result)
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
