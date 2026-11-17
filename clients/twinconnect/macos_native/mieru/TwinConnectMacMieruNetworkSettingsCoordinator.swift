import Foundation
import NetworkExtension

/// Applies an already-validated Mieru route policy ONLY after the signed
/// PacketTunnel has an authenticated Mieru transport and a working Libbox
/// packet-flow relay. Merely bundling either engine is never sufficient.
///
/// This coordinator is intentionally not invoked from the current Mieru
/// start path: actual egress pinning and verified transport are pending.
/// On an unsuccessful application, settings are cleared before reporting
/// failure so a half-started tunnel cannot remain configured.
final class TwinConnectMacMieruNetworkSettingsCoordinator {
    enum ApplyFailure: Error {
        case transportNotReady
        case invalidRoute
        case applyFailed
    }

    private weak var tunnel: NEPacketTunnelProvider?
    private var installed = false

    init(tunnel: NEPacketTunnelProvider) {
        self.tunnel = tunnel
    }

    func apply(
        plan: TwinConnectMacMieruEndpointRoute.Plan,
        authenticatedCoreReady: Bool,
        libboxPacketFlowReady: Bool,
        physicalEgressPinned: Bool,
        completion: @escaping (Error?) -> Void
    ) {
        guard authenticatedCoreReady && libboxPacketFlowReady &&
                physicalEgressPinned, let tunnel else {
            completion(ApplyFailure.transportNotReady)
            return
        }

        let settings: NEPacketTunnelNetworkSettings
        do {
            settings = try TwinConnectMacMieruEndpointRoute.tunnelSettings(
                for: plan)
        } catch {
            completion(ApplyFailure.invalidRoute)
            return
        }

        guard settings.tunnelRemoteAddress == plan.endpoint,
              settings.ipv4Settings?.excludedRoutes?.count == 1,
              settings.ipv4Settings?.excludedRoutes?.first?
                .destinationAddress == plan.endpoint,
              settings.ipv4Settings?.excludedRoutes?.first?
                .destinationSubnetMask == "255.255.255.255",
              settings.ipv6Settings?.includedRoutes?.count == 1,
              settings.ipv6Settings?.excludedRoutes?.isEmpty == true,
              settings.dnsSettings?.matchDomains == [""] else {
            completion(ApplyFailure.invalidRoute)
            return
        }

        tunnel.setTunnelNetworkSettings(settings) { [weak self, weak tunnel] error in
            guard let self, let tunnel else {
                completion(ApplyFailure.applyFailed)
                return
            }
            if error != nil {
                self.installed = false
                tunnel.setTunnelNetworkSettings(nil) { _ in
                    completion(ApplyFailure.applyFailed)
                }
                return
            }
            self.installed = true
            // Applying settings is NOT a verified peer handshake/egress.
            completion(nil)
        }
    }

    func clear(completion: @escaping () -> Void) {
        guard let tunnel else {
            installed = false
            completion()
            return
        }
        guard installed else {
            completion()
            return
        }
        tunnel.setTunnelNetworkSettings(nil) { [weak self] _ in
            self?.installed = false
            completion()
        }
    }
}
