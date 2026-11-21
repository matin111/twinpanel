import Foundation
import Darwin
import Security

/// Native C-ABI adapter for a future signed, in-process Mieru PacketTunnel.
///
/// This is NOT a VPN implementation by itself. The extension must validate
/// account-scoped Keychain material, pin the Mieru egress outside its TUN,
/// start the core, then launch the Libbox loopback relay and verify runtime
/// egress before any host can claim an established connection.
///
/// A standalone CLI or arbitrary dylib path must never be executed.
final class TwinConnectMacMieruCore {
    typealias StartFn = @convention(c) (UnsafePointer<CChar>?, Int32) -> Int32
    typealias StopFn = @convention(c) () -> Int32
    typealias LocalReadyFn = @convention(c) () -> Int32

    private var handle: UnsafeMutableRawPointer?
    private var startFunction: StartFn?
    private var stopFunction: StopFn?
    private var readyFunction: LocalReadyFn?
    private var started = false

    private static func failure(_ reason: String) -> NSError {
        NSError(domain: "com.twinpanel.twinconnect.mieru", code: 2801,
                userInfo: [NSLocalizedDescriptionKey: reason])
    }

    private static func signedExtensionEntitled() -> Bool {
        #if TWINCONNECT_SIGNED_MIERU
        guard let task = SecTaskCreateFromSelf(kCFAllocatorDefault),
              let capabilities = SecTaskCopyValueForEntitlement(
                  task,
                  "com.apple.developer.networking.networkextension" as CFString,
                  nil) as? [String],
              capabilities.contains("packet-tunnel-provider") else {
            return false
        }
        return true
        #else
        // Unsigned previews never load third-party code or activate a tunnel.
        return false
        #endif
    }

    private static func bundledLibrary() -> URL? {
        guard let bundle = Bundle.main.bundleURL as URL?,
              bundle.pathExtension == "appex",
              Bundle.main.bundleIdentifier ==
                "com.twinpanel.twinconnect.PacketTunnel" else {
            return nil
        }
        let library = bundle.appendingPathComponent(
            "Contents/Frameworks/libtwinmieru.dylib", isDirectory: false)
        guard library.standardizedFileURL.deletingLastPathComponent() ==
                bundle.appendingPathComponent(
                    "Contents/Frameworks", isDirectory: true).standardizedFileURL,
              FileManager.default.fileExists(atPath: library.path) else {
            return nil
        }
        return library
    }

    /// Only accepts validated, pinned, extension-owned JSON. Do not call this
    /// from the Flutter host; C-ABI credentials remain inside the extension.
    func start(config: Data, coreOwnedByExtension: Bool,
               endpointPinnedOutsideTunnel: Bool) throws {
        guard !started, handle == nil else {
            throw Self.failure("MACOS_MIERU_ALREADY_STARTED")
        }
        guard coreOwnedByExtension, endpointPinnedOutsideTunnel,
              Self.signedExtensionEntitled(),
              (64...65536).contains(config.count),
              let library = Self.bundledLibrary() else {
            throw Self.failure("MACOS_MIERU_SIGNED_CORE_UNAVAILABLE")
        }
        // dylib and appex must be provisioned/signed by the same Apple team.
        guard let loaded = dlopen(library.path, RTLD_NOW | RTLD_LOCAL) else {
            throw Self.failure("MACOS_MIERU_LIBRARY_LOAD_FAILED")
        }
        guard let startSymbol = dlsym(loaded, "TwinMieruStart"),
              let stopSymbol = dlsym(loaded, "TwinMieruStop"),
              let readySymbol = dlsym(loaded, "TwinMieruLocalReady") else {
            dlclose(loaded)
            throw Self.failure("MACOS_MIERU_SYMBOLS_MISSING")
        }
        let run = unsafeBitCast(startSymbol, to: StartFn.self)
        let stop = unsafeBitCast(stopSymbol, to: StopFn.self)
        let ready = unsafeBitCast(readySymbol, to: LocalReadyFn.self)
        let status: Int32 = config.withUnsafeBytes { buffer in
            guard let ptr = buffer.baseAddress else { return -1 }
            return run(ptr.assumingMemoryBound(to: CChar.self),
                       Int32(config.count))
        }
        guard status == 0, ready() == 1 else {
            if status == 0 { _ = stop() }
            dlclose(loaded)
            throw Self.failure("MACOS_MIERU_LOCAL_CORE_START_FAILED")
        }
        handle = loaded
        startFunction = run
        stopFunction = stop
        readyFunction = ready
        started = true
        // Local SOCKS readiness is not a server handshake or TUN readiness.
    }

    var localCoreRunning: Bool {
        started && readyFunction?() == 1
    }

    func stop() {
        if started { _ = stopFunction?() }
        started = false
        startFunction = nil
        stopFunction = nil
        readyFunction = nil
        if let handle { dlclose(handle) }
        handle = nil
    }

    deinit { stop() }
}
