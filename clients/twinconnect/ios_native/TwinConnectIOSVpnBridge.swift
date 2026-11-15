import Foundation
import Flutter
import NetworkExtension

// Read-only iOS native capability bridge. The shared Flutter dashboard
// must NOT treat this channel as evidence that any tunnel engine is installed.
//
// To ship a real VPN: provision packet-tunnel-provider entitlement, embed a
// signed NEPacketTunnelProvider extension with a linked engine, and only then
// replace the empty supportedProtocols list after runtime verification.
final class TwinConnectIOSVpnBridge {
    private static let channelName = "com.twinpanel.twinconnect/vpn"

    static func register(binaryMessenger: FlutterBinaryMessenger) {
        let channel = FlutterMethodChannel(
            name: channelName, binaryMessenger: binaryMessenger)
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
                    "managedDevice": false
                ] as [String: Any])
            case "getProtocolCapabilities":
                // Must remain empty until a real, signed PacketTunnel target
                // and its protocol transport are installed on this device.
                result([
                    "contractVersion": 1,
                    "supportedProtocols": [String]()
                ] as [String: Any])
            case "getEngineInstallation":
                TwinConnectIOSVPNControl.checkInstallation(result)
            case "startTunnel":
                TwinConnectIOSVPNControl.start(call.arguments, result: result)
            case "stopTunnel":
                TwinConnectIOSVPNControl.stop(result)
            case "getTunnelStatus":
                NETunnelProviderManager.loadAllFromPreferences {
                    managers, error in
                    guard error == nil, let managers = managers else {
                        result([
                            "contractVersion": 1,
                            "state": "unknown",
                            "verified": false
                        ] as [String: Any])
                        return
                    }
                    let ours = managers.first {
                        ($0.protocolConfiguration as? NETunnelProviderProtocol)?
                            .providerBundleIdentifier ==
                            "com.twinpanel.twinconnect.PacketTunnel"
                    }
                    // Never infer successful VPN traffic from a saved profile.
                    let state = ours?.connection.status
                    let label: String
                    switch state {
                    case .connected: label = "os_connected_unverified"
                    case .connecting: label = "connecting"
                    case .disconnecting: label = "disconnecting"
                    case .reasserting: label = "reasserting"
                    case .disconnected: label = "disconnected"
                    case .invalid: label = "invalid"
                    case .none: label = "not_configured"
                    @unknown default: label = "unknown"
                    }
                    result([
                        "contractVersion": 1,
                        "state": label,
                        "verified": false
                    ] as [String: Any])
                }
            default:
                result(FlutterMethodNotImplemented)
            }
        }
    }
}
