import Foundation
import NetworkExtension

/// Serializes Mieru tunnel route application and shutdown.
///
/// A stop arriving during an asynchronous setTunnelNetworkSettings call must
/// wait for the OS callback, undo any late success, and only then complete.
/// This coordinator is intentionally NOT invoked from the unsigned Mieru
/// startup path. Real peer auth, physical egress and Libbox packet flow must
/// all be proven before the caller may set the three readiness gates to true.
final class TwinConnectMacMieruNetworkSettingsCoordinator {
    enum ApplyFailure: Error {
        case transportNotReady
        case invalidRoute
        case applyFailed
        case stoppedWhileApplying
        case alreadyApplying
    }

    private enum Phase {
        case idle
        case applying
        case active
        case clearing
    }

    private weak var tunnel: NEPacketTunnelProvider?
    private let queue = DispatchQueue(
        label: "com.twinpanel.twinconnect.macos.mieru.network")
    private var phase: Phase = .idle
    private var cancelled = false
    private var stopWaiters: [() -> Void] = []

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
        queue.async { [weak self] in
            guard let self else {
                completion(ApplyFailure.applyFailed)
                return
            }
            guard self.phase == .idle, !self.cancelled else {
                completion(ApplyFailure.alreadyApplying)
                return
            }
            guard authenticatedCoreReady && libboxPacketFlowReady &&
                    physicalEgressPinned, let tunnel = self.tunnel else {
                completion(ApplyFailure.transportNotReady)
                return
            }

            let settings: NEPacketTunnelNetworkSettings
            do {
                settings = try TwinConnectMacMieruEndpointRoute
                    .tunnelSettings(for: plan)
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

            self.phase = .applying
            tunnel.setTunnelNetworkSettings(settings) { [weak self] error in
                guard let self else {
                    completion(ApplyFailure.applyFailed)
                    return
                }
                self.queue.async {
                    // Even after a stop, an in-flight OS apply may succeed.
                    // Always clear before notifying stop callers.
                    if error != nil || self.cancelled {
                        let failure: Error = self.cancelled
                            ? ApplyFailure.stoppedWhileApplying
                            : ApplyFailure.applyFailed
                        self.clearAfterApply(tunnel: tunnel) {
                            completion(failure)
                        }
                        return
                    }
                    self.phase = .active
                    // OS routing success is NOT an authenticated Mieru
                    // handshake or proof of working VPN egress.
                    completion(nil)
                }
            }
        }
    }

    /// Always called on queue after the callback for an in-flight apply.
    private func clearAfterApply(
        tunnel: NEPacketTunnelProvider,
        completion: @escaping () -> Void
    ) {
        phase = .clearing
        tunnel.setTunnelNetworkSettings(nil) { [weak self] _ in
            guard let self else {
                completion()
                return
            }
            self.queue.async {
                self.phase = .idle
                completion()
                self.finishStopWaiters()
            }
        }
    }

    /// Must only be invoked from the coordinator's serial queue.
    private func finishStopWaiters() {
        let waiters = stopWaiters
        stopWaiters.removeAll()
        for waiter in waiters { waiter() }
    }

    func clear(completion: @escaping () -> Void) {
        queue.async { [weak self] in
            guard let self else { completion(); return }
            self.cancelled = true
            switch self.phase {
            case .idle:
                completion()
            case .applying, .clearing:
                // The in-flight callback owns rollback and will invoke this
                // completion only after the rollback callback has finished.
                self.stopWaiters.append(completion)
            case .active:
                self.stopWaiters.append(completion)
                guard let tunnel = self.tunnel else {
                    self.phase = .idle
                    self.finishStopWaiters()
                    return
                }
                self.clearAfterApply(tunnel: tunnel, completion: {})
            }
        }
    }
}
