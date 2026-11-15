// Native macOS capability boundary for the shared TwinConnect Flutter UI.
// The real NEPacketTunnelProvider target and engine linkage are not installed
// in this unsigned development preview. Never claim connectivity/protection.
final class TwinConnectMacOSVPNBridge {
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
                // An Apple-signed, entitled Packet Tunnel extension with
                // real protocol engines must be embedded before this changes.
                result([
                    "contractVersion": 1,
                    "supportedCodes": [String]()
                ] as [String: Any])
            case "macOSRuntimeStatus":
                result([
                    "contractVersion": 1,
                    "state": "not_installed",
                    "engineReady": false,
                    "connected": false,
                    "reason": "MACOS_PACKET_TUNNEL_NOT_INSTALLED",
                ] as [String: Any])
            default:
                result(FlutterMethodNotImplemented)
            }
        }
    }
}
