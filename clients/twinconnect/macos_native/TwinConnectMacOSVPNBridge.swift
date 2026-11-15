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
            default:
                result(FlutterMethodNotImplemented)
            }
        }
    }
}
