// AppKit-only fallback for a macOS host without a Metal device/command queue.
// This view does NOT launch Flutter, request secrets, or claim VPN connectivity.
import Cocoa

final class TwinConnectMacOSMetalFallback: NSViewController {
    private let diagnostic = [
        "TwinConnect macOS graphics compatibility mode",
        "FlutterView not initialized: no MTLDevice or MTLCommandQueue available.",
        "This is a native AppKit screen, not the Flutter VPN dashboard.",
        "VPN connection: NOT AVAILABLE in this mode.",
        "Run: python3 macos_native/preflight_macos.py"
    ].joined(separator: "\n")

    override func loadView() {
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 880, height: 550))
        root.wantsLayer = true
        root.layer?.backgroundColor = NSColor(
            calibratedRed: 0.055, green: 0.085, blue: 0.14, alpha: 1.0
        ).cgColor

        let brand = makeLabel("TwinConnect", size: 34, weight: .bold,
                              color: .white)
        let heading = makeLabel("Graphics compatibility mode", size: 22,
                                weight: .semibold, color: .white)
        let message = makeLabel(
            "This Mac session has no available Metal GPU or command queue. " +
            "Flutter cannot draw its interface here, so TwinConnect is showing " +
            "a native macOS screen instead of a blank window.",
            size: 15, weight: .regular,
            color: NSColor(calibratedWhite: 0.86, alpha: 1.0)
        )
        let restriction = makeLabel(
            "VPN connection is unavailable in this mode. " +
            "Your profiles and server settings have not been changed.",
            size: 14, weight: .medium,
            color: NSColor(calibratedRed: 1.0, green: 0.77,
                           blue: 0.45, alpha: 1.0)
        )
        let instructions = makeLabel(
            "Enable Metal/GPU acceleration on the host or use a Metal-capable " +
            "Mac to run the full Flutter interface. Xcode builds and offline " +
            "tests can still run without a graphics device.",
            size: 13, weight: .regular,
            color: NSColor(calibratedWhite: 0.68, alpha: 1.0)
        )

        let copy = NSButton(title: "Copy diagnostics", target: self,
                            action: #selector(copyDiagnostics(_:)))
        copy.bezelStyle = .rounded
        copy.controlSize = .large
        copy.setButtonType(.momentaryPushIn)

        let stack = NSStackView(views: [
            brand, heading, message, restriction, instructions, copy
        ])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 20
        stack.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: root.leadingAnchor,
                                           constant: 55),
            stack.trailingAnchor.constraint(lessThanOrEqualTo:
                                            root.trailingAnchor, constant: -55),
            stack.centerYAnchor.constraint(equalTo: root.centerYAnchor),
            stack.widthAnchor.constraint(lessThanOrEqualToConstant: 740),
            stack.widthAnchor.constraint(lessThanOrEqualTo:
                                         root.widthAnchor, constant: -110)
        ])
        self.view = root
    }

    private func makeLabel(_ value: String, size: CGFloat,
                           weight: NSFont.Weight, color: NSColor)
                           -> NSTextField {
        let field = NSTextField(wrappingLabelWithString: value)
        field.font = NSFont.systemFont(ofSize: size, weight: weight)
        field.textColor = color
        field.isSelectable = true
        return field
    }

    @objc private func copyDiagnostics(_ sender: NSButton) {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(diagnostic, forType: .string)
        sender.title = "Diagnostics copied"
    }
}
