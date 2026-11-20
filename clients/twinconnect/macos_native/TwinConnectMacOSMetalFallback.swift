// The no-Metal startup path now uses a real, read-only native TwinConnect UI.
// It is intentionally separate from the Flutter VPN engine and cannot claim
// an active tunnel without Apple signing and a verified PacketTunnel.
import Cocoa

final class TwinConnectMacOSMetalFallback: TwinConnectMacOSNativeDashboard {}
