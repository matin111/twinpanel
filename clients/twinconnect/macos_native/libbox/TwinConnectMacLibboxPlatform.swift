import Foundation
import Network
import NetworkExtension
import Darwin

#if canImport(Libbox)
import Libbox

/// Adapter for the official sing-box Libbox macOS in-process TUN engine.
/// A packet-flow file descriptor, default-interface observations, and Apple
/// routing/DNS policy must all be available before the service may start.
/// Unsupported optional platform features fail explicitly (never bypass VPN).
final class TwinConnectMacLibboxPlatform: NSObject,
    LibboxPlatformInterfaceProtocol, LibboxCommandServerHandlerProtocol {
    private weak var tunnel: PacketTunnelProvider?
    private var settings: NEPacketTunnelNetworkSettings?
    private var monitor: NWPathMonitor?
    private var observedPath: Network.NWPath?
    private let stateLock = NSLock()
    private var stopped = false

    init(tunnel: PacketTunnelProvider) {
        self.tunnel = tunnel
        super.init()
    }

    private static func failure(_ code: String) -> NSError {
        NSError(domain: "com.twinpanel.twinconnect.libbox", code: 2301,
            userInfo: [NSLocalizedDescriptionKey: code])
    }

    /// Libbox calls this on a worker thread. Never use an undocumented
    /// packetFlow KVC key: a missing Objective-C key may raise an exception
    /// and crash the entire PacketTunnel extension instead of failing safely.
    /// Use Libbox's native tunnel-descriptor accessor only.
    func openTun(_ options: LibboxTunOptionsProtocol?,
                 ret0_: UnsafeMutablePointer<Int32>?) throws {
        guard let options, let ret0_, let tunnel,
              options.getAutoRoute(), options.getMTU() >= 576,
              options.getMTU() <= 9000 else {
            throw Self.failure("MACOS_LIBBOX_TUN_OPTIONS_INVALID")
        }
        stateLock.lock()
        let cancelled = stopped
        stateLock.unlock()
        if cancelled { throw Self.failure("MACOS_LIBBOX_TUN_STOPPED") }

        let candidate = TwinConnectMacTunnelPolicy.hysteria2Settings()
        candidate.mtu = NSNumber(value: options.getMTU())
        let semaphore = DispatchSemaphore(value: 0)
        // The OS can finish route installation AFTER our 15-second wait.
        // A timed-out start must roll back that late installation instead of
        // leaving a full-tunnel route active without a packet-flow engine.
        let applyLock = NSLock()
        var applyError: Error?
        var applyFinished = false
        var applyTimedOut = false
        tunnel.setTunnelNetworkSettings(candidate) { error in
            applyLock.lock()
            applyError = error
            applyFinished = true
            let mustRollback = applyTimedOut
            applyLock.unlock()
            if mustRollback {
                tunnel.setTunnelNetworkSettings(nil) { _ in }
            }
            semaphore.signal()
        }
        guard semaphore.wait(timeout: .now() + .seconds(15)) == .success else {
            applyLock.lock()
            applyTimedOut = true
            let completedBeforeTimeout = applyFinished
            applyLock.unlock()
            // Exactly one side owns rollback: the timeout path if the
            // callback already finished, otherwise the delayed callback.
            if completedBeforeTimeout {
                tunnel.setTunnelNetworkSettings(nil) { _ in }
            }
            throw Self.failure("MACOS_LIBBOX_TUN_NETWORK_SETTINGS_TIMEOUT")
        }
        if let applyError {
            tunnel.setTunnelNetworkSettings(nil) { _ in }
            throw applyError
        }
        // Commit the locally owned policy atomically with stop state.
        // reset() may be running on the provider's shutdown callback.
        stateLock.lock()
        let stoppedDuringApply = stopped
        if !stoppedDuringApply {
            settings = candidate
        }
        stateLock.unlock()
        guard !stoppedDuringApply else {
            tunnel.setTunnelNetworkSettings(nil) { _ in }
            throw Self.failure("MACOS_LIBBOX_TUN_STOPPED")
        }

        // Never introspect NEPacketTunnelFlow via private KVC. The
        // Libbox-provided descriptor is the only supported native handle
        // in this adapter; unavailable means fail closed, not mock success.
        let descriptor = LibboxGetTunnelFileDescriptor()
        guard descriptor >= 0 else {
            // A TUN interface without a usable descriptor must not leave
            // full-tunnel routes or DNS installed on the OS.
            stateLock.lock()
            settings = nil
            stateLock.unlock()
            tunnel.setTunnelNetworkSettings(nil) { _ in }
            throw Self.failure("MACOS_LIBBOX_TUN_DESCRIPTOR_UNAVAILABLE")
        }
        ret0_.pointee = descriptor
    }

    func usePlatformAutoDetectControl() -> Bool { false }
    func autoDetectControl(_ fd: Int32) throws {}

    func findConnectionOwner(_ ipProtocol: Int32, sourceAddress: String?,
                             sourcePort: Int32, destinationAddress: String?,
                             destinationPort: Int32) throws -> LibboxConnectionOwner {
        throw Self.failure("MACOS_LIBBOX_PROCESS_OWNER_UNAVAILABLE")
    }

    func startDefaultInterfaceMonitor(
        _ listener: LibboxInterfaceUpdateListenerProtocol?) throws {
        guard let listener else {
            throw Self.failure("MACOS_LIBBOX_MONITOR_LISTENER_MISSING")
        }
        let monitor = NWPathMonitor()
        self.monitor = monitor
        let ready = DispatchSemaphore(value: 0)
        var initial = true
        monitor.pathUpdateHandler = { [weak self] path in
            guard let self else { return }
            self.stateLock.lock()
            self.observedPath = path
            self.stateLock.unlock()
            listener.updateNetworkPath(path.status == .satisfied
                ? "satisfied" : "unavailable")
            let defaultInterface = path.availableInterfaces.first {
                $0.type == .wifi || $0.type == .wiredEthernet ||
                $0.type == .cellular
            }
            listener.updateDefaultInterface(defaultInterface?.name ?? "",
                interfaceIndex: Int32(defaultInterface?.index ?? -1),
                isExpensive: path.isExpensive,
                isConstrained: path.isConstrained)
            if initial { initial = false; ready.signal() }
        }
        monitor.start(queue: DispatchQueue(label: "twinconnect.libbox.path"))
        guard ready.wait(timeout: .now() + .seconds(10)) == .success else {
            monitor.cancel()
            self.monitor = nil
            throw Self.failure("MACOS_LIBBOX_INTERFACE_MONITOR_TIMEOUT")
        }
    }

    func closeDefaultInterfaceMonitor(
        _ listener: LibboxInterfaceUpdateListenerProtocol?) throws {
        monitor?.cancel()
        monitor = nil
        stateLock.lock()
        observedPath = nil
        stateLock.unlock()
    }

    func getInterfaces() throws -> LibboxNetworkInterfaceIteratorProtocol {
        stateLock.lock()
        let path = observedPath
        stateLock.unlock()
        guard let path, path.status == .satisfied else {
            throw Self.failure("MACOS_LIBBOX_INTERFACES_UNAVAILABLE")
        }
        let interfaces: [LibboxNetworkInterface] = path.availableInterfaces.map {
            let result = LibboxNetworkInterface()
            result.name = $0.name
            result.index = Int32($0.index)
            switch $0.type {
            case .wifi: result.type = LibboxInterfaceTypeWIFI
            case .cellular: result.type = LibboxInterfaceTypeCellular
            case .wiredEthernet: result.type = LibboxInterfaceTypeEthernet
            default: result.type = LibboxInterfaceTypeOther
            }
            return result
        }
        return LibboxNetworkInterfaces(interfaces)
    }

    private final class LibboxNetworkInterfaces: NSObject,
        LibboxNetworkInterfaceIteratorProtocol {
        private var items: [LibboxNetworkInterface]
        private var index = 0
        init(_ items: [LibboxNetworkInterface]) { self.items = items }
        func hasNext() -> Bool { index < items.count }
        func next() -> LibboxNetworkInterface? {
            guard index < items.count else { return nil }
            defer { index += 1 }
            return items[index]
        }
    }

    func underNetworkExtension() -> Bool { true }
    func includeAllNetworks() -> Bool { false }

    func clearDNSCache() {
        // Reapplying NEPacketTunnelNetworkSettings is NOT a DNS cache flush.
        // It can re-install default routes after stop() has begun and cause
        // DNS or traffic to remain trapped in a torn-down tunnel.
        // macOS does not expose a safe per-extension system DNS cache flush
        // through this Libbox callback. Leave OS routing unchanged.
    }
    func readWIFIState() -> LibboxWIFIState? { nil }
    func readWIFISSID() -> String? { nil }
    func connectSSHAgent(_ ret0_: UnsafeMutablePointer<Int32>?) throws {
        throw Self.failure("MACOS_LIBBOX_SSH_AGENT_UNSUPPORTED")
    }

    func writeLog(_ message: String?) {
        // Credentials and entire Libbox config must never be logged here.
    }
    func writeDebugMessage(_ message: String?) {}
    func serviceStop() throws {
        throw Self.failure("MACOS_LIBBOX_SERVICE_STOP_NOT_HOST_REQUESTED")
    }
    func serviceReload() throws {
        throw Self.failure("MACOS_LIBBOX_SERVICE_RELOAD_NOT_VERIFIED")
    }

    func getSystemProxyStatus() throws -> LibboxSystemProxyStatus {
        LibboxSystemProxyStatus()
    }
    func setSystemProxyEnabled(_ enabled: Bool) throws {
        throw Self.failure("MACOS_LIBBOX_SYSTEM_PROXY_UNSUPPORTED")
    }
    func triggerNativeCrash() throws {
        throw Self.failure("MACOS_LIBBOX_TRIGGER_CRASH_DISABLED")
    }
    func send(_ notification: LibboxNotification?) throws {}
    func cancelNotification(_ identifier: String?, typeID: Int32) throws {}
    func startNeighborMonitor(
        _ listener: LibboxNeighborUpdateListenerProtocol?) throws {}
    func registerMyInterface(_ name: String?) {}
    func closeNeighborMonitor(
        _ listener: LibboxNeighborUpdateListenerProtocol?) throws {}

    func localDNSTransport() -> (any LibboxLocalDNSTransportProtocol)? { nil }
    func systemCertificates() -> (any LibboxStringIteratorProtocol)? { nil }
    func usePlatformShell() -> Bool { false }
    func checkPlatformShell() throws {
        throw Self.failure("MACOS_LIBBOX_SHELL_UNSUPPORTED")
    }
    func openShellSession(_ user: LibboxPlatformUser?, command: String?,
        environ: (any LibboxStringIteratorProtocol)?, term: String?,
        rows: Int32, cols: Int32) throws -> any LibboxShellSessionProtocol {
        throw Self.failure("MACOS_LIBBOX_SHELL_UNSUPPORTED")
    }
    func readSystemSSHHostKey(_ error: NSErrorPointer) -> String {
        error?.pointee = Self.failure("MACOS_LIBBOX_SSH_UNSUPPORTED")
        return ""
    }
    func lookupSFTPServer(_ error: NSErrorPointer) -> String {
        error?.pointee = Self.failure("MACOS_LIBBOX_SFTP_UNSUPPORTED")
        return ""
    }
    func tailscaleHostname() -> String { "" }
    func usePlatformBridge() -> Bool { false }
    func createBridge(
        _ options: LibboxBridgeOptions?) throws -> any LibboxBridgeSessionProtocol {
        throw Self.failure("MACOS_LIBBOX_BRIDGE_UNSUPPORTED")
    }
    func lookupUser(_ username: String?) throws -> LibboxPlatformUser {
        throw Self.failure("MACOS_LIBBOX_USER_LOOKUP_UNSUPPORTED")
    }

    /// The stop completion is not delivered until macOS acknowledges
    /// removal of tunnel routes and DNS. Never report a completed shutdown
    /// while setTunnelNetworkSettings(nil) is still in flight.
    func reset(completion: @escaping () -> Void) {
        stateLock.lock()
        stopped = true
        observedPath = nil
        let hadSettings = settings != nil
        settings = nil
        stateLock.unlock()
        monitor?.cancel()
        monitor = nil
        guard hadSettings, let tunnel else {
            completion()
            return
        }
        tunnel.setTunnelNetworkSettings(nil) { _ in
            completion()
        }
    }
}
#endif
