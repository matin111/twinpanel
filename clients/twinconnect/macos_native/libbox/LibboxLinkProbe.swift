import Foundation
#if canImport(Libbox)
import Libbox
#else
#error("Libbox XCFramework is missing from the PacketTunnel target")
#endif

/// This file deliberately validates native module linking only.
/// PacketFlow, DNS, platform interface and signed entitlements are not ready.
enum TwinConnectLibboxLinkProbe {
    static let nativeFrameworkResolved = true
    static let packetFlowReady = false
    static let connectionVerified = false
}
