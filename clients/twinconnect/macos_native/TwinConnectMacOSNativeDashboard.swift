// Native AppKit rendering of the shared TwinConnect appearance, without Metal.
// The visual design mirrors the Flutter desktop/mobile experience while
// strictly keeping VPN unavailable until a signed and verified PacketTunnel.
import Cocoa
import CryptoKit

// Low-cost AppKit renderer for remote/macOS machines without a working Metal
// backend. Set TWINCONNECT_MAC_LIGHTWEIGHT_UI=0 before launching to opt out.
private enum TwinNativeRenderBudget {
    static let lightweight =
        ProcessInfo.processInfo.environment["TWINCONNECT_MAC_LIGHTWEIGHT_UI"] != "0"
}

private final class TwinNativeFlippedDocument: NSView {
    override var isFlipped: Bool { true }
}

private final class TwinNativeBackdrop: NSView {
    // Retina vector artwork inspired by the Windows spatial atmosphere.
    // Drawn on CPU: supported on the Metal-less Catalina test machine.
    // All highlights derive from the authenticated panel theme.
    var base = NSColor(calibratedRed: 0.032, green: 0.11, blue: 0.145, alpha: 1)
    var glow = NSColor(calibratedRed: 0.10, green: 0.47, blue: 0.55, alpha: 1)
    private let ambientAura = CAGradientLayer()

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.masksToBounds = true
        ambientAura.type = .radial
        ambientAura.startPoint = CGPoint(x: 0.73, y: 0.79)
        ambientAura.endPoint = CGPoint(x: 1.40, y: 1.37)
        ambientAura.locations = [0, 0.45, 1]
        ambientAura.opacity = 0.20
        layer?.insertSublayer(ambientAura, at: 0)
    }

    required init?(coder: NSCoder) { return nil }

    func beginAmbientMotion() {
        // Ambient motion is decoration ONLY. It is not a fake VPN handshake,
        // download activity, or an offline "connected" animation.
        ambientAura.colors = [
            glow.withAlphaComponent(0.30).cgColor,
            glow.withAlphaComponent(0.12).cgColor,
            glow.withAlphaComponent(0).cgColor
        ]
        guard !TwinNativeRenderBudget.lightweight,
              !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion,
              ambientAura.animation(forKey: "ambientBreath") == nil
        else { return }
        let breathe = CABasicAnimation(keyPath: "opacity")
        breathe.fromValue = 0.12
        breathe.toValue = 0.36
        breathe.duration = 9
        breathe.autoreverses = true
        breathe.repeatCount = .infinity
        breathe.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        ambientAura.add(breathe, forKey: "ambientBreath")
    }

    override func layout() {
        super.layout()
        ambientAura.frame = bounds
    }

    private func radialLight(_ context: CGContext, center: CGPoint,
                             radius: CGFloat, tint: NSColor, opacity: CGFloat) {
        let clear = tint.withAlphaComponent(0).cgColor
        guard let gradient = CGGradient(
            colorsSpace: CGColorSpaceCreateDeviceRGB(),
            colors: [tint.withAlphaComponent(opacity).cgColor,
                     tint.withAlphaComponent(opacity * 0.42).cgColor,
                     clear] as CFArray,
            locations: [0, 0.35, 1]
        ) else { return }
        context.drawRadialGradient(
            gradient, startCenter: center, startRadius: 0,
            endCenter: center, endRadius: radius,
            options: [.drawsAfterEndLocation])
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        let area = bounds
        let w = area.width
        let h = area.height
        let accent = glow
        let frost = accent.blended(withFraction: 0.57, of: .white) ?? accent
        let shade = base.blended(withFraction: 0.40, of: .black) ?? base

        // Deep architectural backdrop rather than flat aqua wallpaper.
        NSGradient(colors: [
            shade, base,
            base.blended(withFraction: 0.16, of: accent) ?? base,
            shade
        ])?.draw(in: area, angle: 138)

        if !TwinNativeRenderBudget.lightweight,
           let context = NSGraphicsContext.current?.cgContext {
            context.saveGState()
            // Off-canvas light shafts give believable dimensional depth.
            radialLight(context,
                center: CGPoint(x: w * 0.74, y: h * 1.02),
                radius: max(w, h) * 0.67,
                tint: accent, opacity: 0.50)
            radialLight(context,
                center: CGPoint(x: w * 1.03, y: h * 0.28),
                radius: max(w, h) * 0.48,
                tint: frost, opacity: 0.19)
            radialLight(context,
                center: CGPoint(x: w * 0.25, y: h * -0.18),
                radius: max(w, h) * 0.52,
                tint: accent, opacity: 0.20)
            context.restoreGState()
        }

        // An asymmetric luminous orbital feature sits mostly behind the
        // content, with enough of its sweep visible in the page margins.
        if TwinNativeRenderBudget.lightweight { return }
        let origin = CGPoint(x: w * 0.87, y: h * 0.52)
        for index in 0..<7 {
            let expansion = CGFloat(index) * 31
            let ellipse = NSBezierPath(ovalIn: NSRect(
                x: origin.x - (w * 0.28 + expansion),
                y: origin.y - (h * 0.47 + expansion * 0.76),
                width: (w * 0.28 + expansion) * 2,
                height: (h * 0.47 + expansion * 0.76) * 2))
            ellipse.lineWidth = index == 0 ? 1.5 : 0.65
            frost.withAlphaComponent(index == 0 ? 0.20 : 0.075)
                .setStroke()
            ellipse.stroke()
        }

        // A second broad ribbon curves across the canvas; it avoids the
        // sharp repeated waves that made the first design look dated.
        for index in 0..<4 {
            let offset = CGFloat(index) * 29
            let ribbon = NSBezierPath()
            ribbon.move(to: CGPoint(x: -w * 0.15, y: h * 0.12 + offset))
            ribbon.curve(to: CGPoint(x: w * 1.13, y: h * 0.78 + offset),
                         controlPoint1: CGPoint(x: w * 0.31, y: h * 0.59 + offset),
                         controlPoint2: CGPoint(x: w * 0.56, y: -h * 0.19 + offset))
            ribbon.lineWidth = index == 0 ? 1.25 : 0.75
            accent.withAlphaComponent(index == 0 ? 0.17 : 0.065)
                .setStroke()
            ribbon.stroke()
        }

        // Small, restrained specular accents—not a starfield texture.
        for index in 0..<13 {
            let x = CGFloat((index * 83 + 47) % 241) / 241
            let y = CGFloat((index * 61 + 19) % 229) / 229
            let radius: CGFloat = index.isMultiple(of: 4) ? 1.25 : 0.65
            let sparkle = NSBezierPath(ovalIn: NSRect(
                x: w * x - radius, y: h * y - radius,
                width: radius * 2, height: radius * 2))
            frost.withAlphaComponent(index.isMultiple(of: 4) ? 0.33 : 0.12)
                .setFill()
            sparkle.fill()
        }
    }
}

private final class TwinNativePremiumButton: NSButton {
    private let accentGradient = CAGradientLayer()
    private let glassEdge = CAGradientLayer()
    private var glassLayersAttached = false

    func setAccentGradient(_ top: NSColor, _ bottom: NSColor) {
        wantsLayer = true
        // A transparent gradient cannot look like glass if the parent layer
        // carries the old opaque button paint underneath it.
        layer?.backgroundColor = NSColor.clear.cgColor
        accentGradient.colors = [top.cgColor, bottom.cgColor]
        accentGradient.startPoint = CGPoint(x: 0, y: 1)
        accentGradient.endPoint = CGPoint(x: 1, y: 0)
        accentGradient.locations = [0, 1]
        glassEdge.colors = [
            NSColor.white.withAlphaComponent(0.35).cgColor,
            NSColor.white.withAlphaComponent(0.025).cgColor
        ]
        glassEdge.startPoint = CGPoint(x: 0, y: 0.5)
        glassEdge.endPoint = CGPoint(x: 1, y: 0.5)
        if !glassLayersAttached {
            layer?.insertSublayer(accentGradient, at: 0)
            layer?.insertSublayer(glassEdge, above: accentGradient)
            glassLayersAttached = true
        }
        needsLayout = true
    }

    override func layout() {
        super.layout()
        let radius = layer?.cornerRadius ?? 14
        accentGradient.frame = bounds
        accentGradient.cornerRadius = radius
        glassEdge.frame = NSRect(x: 1, y: max(0, bounds.height - 1.5),
                                width: max(0, bounds.width - 2), height: 1)
    }
}

// Uses Core Animation's vector gradient, not a raster image or Metal shader.
// Keeps the Windows-style translucent depth on macOS cloud hosts without Metal.
private final class TwinNativeGlassCard: NSView {
    enum Style: Equatable { case panel, inset, metric, sidebar }
    private let glassGradient = CAGradientLayer()
    private let upperEdge = CAGradientLayer()
    private let blur = NSVisualEffectView(frame: .zero)
    private let tintOverlay = NSView(frame: .zero)
    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        // Actual AppKit vibrancy/blur, not a nearly opaque painted rectangle.
        // withinWindow works on Catalina without an app Metal renderer.
        // Catalina's vibrancy material is neutral GREY by design. Keep a
        // small amount of real blur but do NOT let its opaque charcoal tint
        // replace the tenant's blue/brand-colored glass surfaces.
        blur.material = .sidebar
        blur.blendingMode = .withinWindow
        blur.state = .active
        blur.alphaValue = TwinNativeRenderBudget.lightweight ? 0 : 0.14
        if TwinNativeRenderBudget.lightweight { blur.state = .inactive }
        blur.wantsLayer = true
        addSubview(blur)
        tintOverlay.wantsLayer = true
        addSubview(tintOverlay)
        glassGradient.startPoint = CGPoint(x: 0, y: 1)
        glassGradient.endPoint = CGPoint(x: 1, y: 0)
        glassGradient.locations = [0, 0.55, 1]
        tintOverlay.layer?.addSublayer(glassGradient)
        // One-pixel specular edge, following the Windows card vocabulary.
        upperEdge.colors = [
            NSColor(calibratedRed: 0.44, green: 0.91, blue: 0.94,
                    alpha: 0.24).cgColor,
            NSColor(calibratedRed: 0.44, green: 0.91, blue: 0.94,
                    alpha: 0.025).cgColor
        ]
        upperEdge.startPoint = CGPoint(x: 0, y: 0.5)
        upperEdge.endPoint = CGPoint(x: 1, y: 0.5)
        tintOverlay.layer?.addSublayer(upperEdge)
        apply(.panel)
    }
    required init?(coder: NSCoder) { return nil }
    func apply(_ style: Style, accent: NSColor = NSColor(
        calibratedRed: 0.27, green: 0.67, blue: 0.74, alpha: 1),
        background: NSColor? = nil, surface: NSColor? = nil) {
        // Compose all surfaces from the panel's colors and the SAME dark
        // blue foundation as the backdrop. Actual macOS vibrancy alone
        // turns these surfaces grey on Catalina.
        let neutral: NSColor
        let strength: CGFloat
        switch style {
        case .panel:
            neutral = NSColor(calibratedRed: 0.046, green: 0.158,
                              blue: 0.207, alpha: 1)
            strength = 0.24
        case .inset:
            neutral = NSColor(calibratedRed: 0.070, green: 0.200,
                              blue: 0.255, alpha: 1)
            strength = 0.28
        case .metric:
            neutral = NSColor(calibratedRed: 0.041, green: 0.159,
                              blue: 0.223, alpha: 1)
            strength = 0.25
        case .sidebar:
            neutral = NSColor(calibratedRed: 0.024, green: 0.109,
                              blue: 0.151, alpha: 1)
            strength = 0.18
        }
        let supplied = style == .sidebar ?
            (background ?? surface) : (surface ?? background)
        let foundation = supplied.flatMap {
            neutral.blended(withFraction: 0.38, of: $0)
        } ?? neutral
        let tone = foundation.blended(withFraction: strength, of: accent) ?? foundation
        let upper = tone.blended(withFraction: 0.18, of: .white) ?? tone
        let lower = tone.blended(withFraction: 0.12, of: .black) ?? tone
        // High-enough tinted overlay to defeat the grey vibrancy material,
        // but still partially transparent over the artwork.
        let topAlpha: CGFloat = style == .sidebar ? 0.90 : 0.81
        let middleAlpha: CGFloat = style == .sidebar ? 0.82 : 0.70
        let bottomAlpha: CGFloat = style == .sidebar ? 0.88 : 0.78
        glassGradient.colors = [
            upper.withAlphaComponent(topAlpha).cgColor,
            tone.withAlphaComponent(middleAlpha).cgColor,
            lower.withAlphaComponent(bottomAlpha).cgColor
        ]
        upperEdge.colors = [
            accent.blended(withFraction: 0.42, of: .white)?
                .withAlphaComponent(0.48).cgColor ??
                accent.withAlphaComponent(0.48).cgColor,
            accent.withAlphaComponent(0.04).cgColor
        ]
    }
    override func layout() {
        super.layout()
        blur.frame = bounds
        tintOverlay.frame = bounds
        let radius = layer?.cornerRadius ?? 20
        blur.layer?.cornerRadius = radius
        blur.layer?.masksToBounds = true
        tintOverlay.layer?.cornerRadius = radius
        tintOverlay.layer?.masksToBounds = true
        glassGradient.frame = bounds
        glassGradient.cornerRadius = radius
        upperEdge.frame = NSRect(x: 1, y: bounds.height - 1.5,
                                 width: max(0, bounds.width - 2), height: 1)
    }
}

// Replicates the *disconnected* state of the shared Flutter
// TwinConnectWaveIndicator. No fake activity or synthetic RX/TX animation.
private final class TwinNativeNetworkFabric: NSView {
    // The Windows reference keeps the illustration blank when disconnected.
    // This can become true only after verified signed system-tunnel activation.
    // A successful one-shot SOCKS test must never enable the VPN animation.
    var tunnelConnected = false
    override var isOpaque: Bool { false }
    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        let rect = bounds.insetBy(dx: 1.5, dy: 1.5)
        let outline = NSBezierPath(roundedRect: rect, xRadius: 25, yRadius: 25)
        NSGradient(colors: [
            NSColor(calibratedRed: 0.063, green: 0.118, blue: 0.165, alpha: 1),
            NSColor(calibratedRed: 0.09, green: 0.208, blue: 0.263, alpha: 1),
            NSColor(calibratedRed: 0.067, green: 0.149, blue: 0.196, alpha: 1)
        ])?.draw(in: outline, angle: -40)
        outline.lineWidth = 1
        NSColor(calibratedRed: 0.54, green: 0.82, blue: 0.84,
                alpha: 0.28).setStroke()
        outline.stroke()
        guard tunnelConnected else { return }
        // Retina vector network strands modeled after the Windows dashboard.
        // Purely decorative; the actual VPN status is never inferred from them.
        let cx = rect.midX
        let cy = rect.midY
        let center = CGPoint(x: cx, y: cy)
        for radius in [CGFloat(24), 40, 63] {
            let ring = NSBezierPath(ovalIn: NSRect(
                x: cx - radius, y: cy - radius,
                width: radius * 2, height: radius * 2))
            NSColor(calibratedRed: 0.30, green: 0.82, blue: 0.83,
                    alpha: 0.10).setStroke()
            ring.lineWidth = 1
            ring.stroke()
        }
        for index in 0..<17 {
            let t = CGFloat(index) / 16
            let spread = (t - 0.5) * min(rect.height * 0.66, 105)
            for side in [CGFloat(-1), CGFloat(1)] {
                let path = NSBezierPath()
                let edgeX = cx + side * rect.width * 0.43
                path.move(to: CGPoint(x: cx + side * 13, y: cy + spread * 0.13))
                path.curve(to: CGPoint(x: edgeX, y: cy + spread),
                           controlPoint1: CGPoint(x: cx + side * rect.width * 0.20,
                                                  y: cy + spread * 0.25),
                           controlPoint2: CGPoint(x: cx + side * rect.width * 0.31,
                                                  y: cy + spread * 0.92))
                path.lineWidth = index.isMultiple(of: 4) ? 1.35 : 0.65
                NSColor(calibratedRed: 0.24, green: 0.88, blue: 0.83,
                        alpha: index.isMultiple(of: 4) ? 0.63 : 0.27).setStroke()
                path.stroke()
            }
        }
        for (x, y, radius) in [
            (-0.41, 0.00, 3.8), (-0.31, 0.12, 2.9), (-0.19, -0.12, 2.3),
            (0.19, 0.08, 2.6), (0.31, -0.16, 2.7), (0.41, 0.00, 3.8)
        ] {
            let dot = NSBezierPath(ovalIn: NSRect(
                x: cx + CGFloat(x) * rect.width - CGFloat(radius),
                y: cy + CGFloat(y) * rect.height - CGFloat(radius),
                width: CGFloat(radius) * 2, height: CGFloat(radius) * 2))
            NSColor(calibratedRed: 0.35, green: 0.96, blue: 0.84,
                    alpha: 0.90).setFill()
            dot.fill()
        }
        let centerBody = NSBezierPath(roundedRect: NSRect(
            x: center.x - 19, y: center.y - 25, width: 38, height: 50),
            xRadius: 13, yRadius: 13)
        NSColor(calibratedRed: 0.04, green: 0.20, blue: 0.25, alpha: 1).setFill()
        centerBody.fill()
        centerBody.lineWidth = 1.6
        NSColor(calibratedRed: 0.34, green: 0.94, blue: 0.82, alpha: 0.87).setStroke()
        centerBody.stroke()
        for delta in [-8.0, 0.0, 8.0] {
            let dash = NSBezierPath()
            dash.move(to: CGPoint(x: cx - 8, y: cy + CGFloat(delta)))
            dash.line(to: CGPoint(x: cx + 8, y: cy + CGFloat(delta)))
            dash.lineWidth = 1.25
            dash.stroke()
        }
    }
}

class TwinConnectMacOSNativeDashboard: NSViewController, NSTableViewDataSource,
                                       NSTableViewDelegate {
    private let directory = TwinConnectMacOSNativeDirectory()
    private var accountSession: TwinMacNativeSession?
    private var snapshot: TwinMacNativeSnapshot?
    private var status = ""
    private var busy = false
    private var refreshGeneration = 0
    private var nativeContentWidth: CGFloat = 1100
    private var observesWindowSize = false
    private var tenantLogo: NSImage?
    private var logoGeneration = 0
    // Match Flutter sections: Quick connect / Locations / Settings / Account.
    private var tab = 0
    private var country = "All countries"
    private var expandedCountries = Set<String>()
    private var locationCountryIDs = [String]()
    private var locationRowIDs = [String]()
    private var locationSearch = ""
    private var protocolChipCodes = [String?]()
    private var showAllProtocolChips = true
    private var activeProtocol: String?
    private var activeServer: String?
    private var nodePingResults = [String: TwinMacNativePingResult]()
    private var nodePingBusy = Set<String>()
    private var nodePingQueue = [TwinMacNativeServer]()
    private var pingAllBusy = false
    private var pingGeneration = 0
    private var didAutoPing = false
    private var pingRedrawScheduled = false
    private var localProxyBusy = false
    private var localProxyStatus = ""
    private var cliTunCheckBusy = false
    private weak var usernameField: NSTextField?
    private weak var passwordField: NSSecureTextField?

    private let base = NSColor(calibratedRed: 0.035, green: 0.105, blue: 0.143, alpha: 1)
    private let panelColor = NSColor(calibratedRed: 0.09, green: 0.19, blue: 0.24, alpha: 0.85)
    private let muted = NSColor(calibratedRed: 0.69, green: 0.79, blue: 0.82, alpha: 1)
    private let teal = NSColor(calibratedRed: 0.27, green: 0.67, blue: 0.74, alpha: 1)
    private let sea = NSColor(calibratedRed: 0.40, green: 0.72, blue: 0.70, alpha: 1)
    private let amber = NSColor(calibratedRed: 1.0, green: 0.78, blue: 0.51, alpha: 1)

    override func loadView() {
        view = build()
    }

    override func viewDidAppear() {
        super.viewDidAppear()
        if !observesWindowSize {
            observesWindowSize = true
            NotificationCenter.default.addObserver(
                self, selector: #selector(nativeWindowResized(_:)),
                name: NSWindow.didResizeNotification, object: nil)
        }
        if let current = view.window?.contentView?.bounds.width {
            nativeContentWidth = current
        }
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    @objc private func nativeWindowResized(_ notification: Notification) {
        guard let source = notification.object as? NSWindow,
              source === view.window, accountSession != nil else { return }
        let latest = source.contentView?.bounds.width ?? source.frame.width
        let wasWide = nativeContentWidth - 306 >= 790
        let becomesWide = latest - 306 >= 790
        let significant = abs(latest - nativeContentWidth) > 120
        nativeContentWidth = latest
        if tab == 0 && (wasWide != becomesWide || significant) {
            view = build()
        }
    }

    private func panelHexColor(_ hex: String?) -> NSColor? {
        guard let hex = hex,
              hex.range(of: "^#[0-9a-fA-F]{6}$",
                        options: .regularExpression) != nil,
              let value = UInt32(hex.dropFirst(), radix: 16) else { return nil }
        return NSColor(calibratedRed: CGFloat((value >> 16) & 255) / 255,
                       green: CGFloat((value >> 8) & 255) / 255,
                       blue: CGFloat(value & 255) / 255, alpha: 1)
    }

    private func panelBackgroundColor() -> NSColor? {
        panelHexColor(accountSession?.backgroundHex)
    }

    private func panelCardColor() -> NSColor? {
        panelHexColor(accountSession?.cardHex)
    }

    private func tint() -> NSColor {
        // The panel's primary_color is authoritative. Invalid/missing
        // values fall back to the default accent instead of assuming a tenant.
        return panelHexColor(accountSession?.accentHex) ?? teal
    }

    private func text(_ string: String, size: CGFloat = 13,
                      weight: NSFont.Weight = .regular,
                      color: NSColor? = nil) -> NSTextField {
        let label = NSTextField(wrappingLabelWithString: string)
        label.font = NSFont.systemFont(ofSize: size, weight: weight)
        label.textColor = color ?? NSColor(calibratedWhite: 0.96, alpha: 1)
        label.lineBreakMode = .byWordWrapping
        label.maximumNumberOfLines = 0
        label.alignment = .left
        label.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        return label
    }

    private func stack(_ axis: NSUserInterfaceLayoutOrientation = .vertical,
                       spacing: CGFloat = 13) -> NSStackView {
        let result = NSStackView()
        result.orientation = axis
        result.alignment = axis == .vertical ? .leading : .centerY
        result.spacing = spacing
        result.translatesAutoresizingMaskIntoConstraints = false
        return result
    }

    private func spaced(_ root: NSView, _ contents: NSView,
                        inset: CGFloat = 20) {
        contents.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(contents)
        NSLayoutConstraint.activate([
            contents.leadingAnchor.constraint(equalTo: root.leadingAnchor,
                                              constant: inset),
            contents.trailingAnchor.constraint(equalTo: root.trailingAnchor,
                                               constant: -inset),
            contents.topAnchor.constraint(equalTo: root.topAnchor,
                                          constant: inset),
            contents.bottomAnchor.constraint(equalTo: root.bottomAnchor,
                                             constant: -inset)
        ])
    }

    private func card(_ children: [NSView], radius: CGFloat = 22,
                      padding: CGFloat = 21,
                      style: TwinNativeGlassCard.Style = .panel) -> NSView {
        let box = TwinNativeGlassCard(frame: .zero)
        box.apply(style, accent: tint(),
                  background: panelBackgroundColor(), surface: panelCardColor())
        box.translatesAutoresizingMaskIntoConstraints = false
        box.wantsLayer = true
        box.layer?.cornerRadius = radius
        // Nested data tiles should read as one interface, not a maze of
        // thick outlines. Only top-level panels receive a stronger edge.
        box.layer?.borderWidth = style == .panel ? 0.8 : 0.45
        box.layer?.borderColor = tint().withAlphaComponent(
            style == .panel ? 0.35 : 0.17).cgColor
        box.layer?.shadowColor = NSColor.black.cgColor
        box.layer?.shadowOpacity = TwinNativeRenderBudget.lightweight ? 0 :
            (style == .panel ? 0.10 : 0.025)
        box.layer?.shadowRadius = style == .panel ? 14 : 5
        box.layer?.shadowOffset = CGSize(width: 0, height: -3)
        let column = stack(spacing: 13)
        // Let every glass panel fill the available width; plain NSView
        // children have no intrinsic width and otherwise disappear.
        column.alignment = .leading
        for child in children {
            child.translatesAutoresizingMaskIntoConstraints = false
            child.setContentHuggingPriority(.defaultLow, for: .horizontal)
            column.addArrangedSubview(child)
            // In AppKit a child NSView without an intrinsic width can shrink
            // to its title: every panel uses the full width of its column.
            child.widthAnchor.constraint(equalTo: column.widthAnchor).isActive = true
        }
        spaced(box, column, inset: padding)
        return box
    }

    private func pill(_ value: String, color: NSColor? = nil) -> NSView {
        let background = TwinNativeGlassCard(frame: .zero)
        background.apply(.inset, accent: color ?? tint(),
                         background: panelBackgroundColor(),
                         surface: panelCardColor())
        background.layer?.cornerRadius = 13
        background.layer?.borderColor = (color ?? tint())
            .withAlphaComponent(0.37).cgColor
        background.layer?.borderWidth = 1
        let label = text(value, size: 12, weight: .semibold,
                         color: color ?? sea)
        spaced(background, label, inset: 9)
        return background
    }

    private func button(_ title: String, action: Selector, tag: Int = 0,
                        primary: Bool = false, mutedButton: Bool = false)
                        -> TwinNativePremiumButton {
        let control = TwinNativePremiumButton(title: title, target: self,
                                               action: action)
        control.isBordered = false
        control.bezelStyle = .rounded
        control.tag = tag
        control.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
        control.wantsLayer = true
        control.layer?.cornerRadius = 14
        control.layer?.borderWidth = 1
        let color = primary ? NSColor.white :
            NSColor(calibratedWhite: 0.94, alpha: 1)
        // Never paint an opaque backing behind translucent button glass.
        control.layer?.backgroundColor = NSColor.clear.cgColor
        control.layer?.borderColor = tint().withAlphaComponent(
            primary ? 0.53 : 0.25).cgColor
        // Every clickable surface is glass, and all chroma comes from the
        // authenticated panel brand rather than a hard-coded cyan scheme.
        let brand = tint()
        let upper = primary ?
            (brand.blended(withFraction: 0.23, of: .white) ?? brand) :
            (NSColor(calibratedRed: 0.15, green: 0.25, blue: 0.30, alpha: 1)
                .blended(withFraction: 0.32, of: brand) ?? brand)
        let lower = primary ?
            (brand.blended(withFraction: 0.18, of: .black) ?? brand) :
            (NSColor(calibratedRed: 0.09, green: 0.17, blue: 0.22, alpha: 1)
                .blended(withFraction: 0.22, of: brand) ?? brand)
        control.setAccentGradient(
            upper.withAlphaComponent(primary ? 0.64 : 0.36),
            lower.withAlphaComponent(primary ? 0.52 : 0.27))
        control.layer?.borderColor = brand.withAlphaComponent(
            primary ? 0.74 : 0.38).cgColor
        control.attributedTitle = NSAttributedString(
            string: title,
            attributes: [.foregroundColor: color,
                         .font: NSFont.systemFont(ofSize: 13,
                                                 weight: .semibold)]
        )
        // Navigation stays usable while the account API is refreshing.
        control.isEnabled = true
        control.translatesAutoresizingMaskIntoConstraints = false
        control.heightAnchor.constraint(greaterThanOrEqualToConstant: 30)
            .isActive = true
        return control
    }

    private func separator() -> NSView {
        let line = NSView()
        line.wantsLayer = true
        line.layer?.backgroundColor = tint().withAlphaComponent(0.23).cgColor
        line.translatesAutoresizingMaskIntoConstraints = false
        line.heightAnchor.constraint(equalToConstant: 1).isActive = true
        return line
    }

    private func build() -> NSView {
        let root = TwinNativeBackdrop(frame:
            NSRect(x: 0, y: 0, width: 1180, height: 740))
        let configuredBackground = panelBackgroundColor()?
            .blended(withFraction: 0.60, of: base) ?? base
        root.base = configuredBackground.blended(
            withFraction: 0.19, of: tint()) ?? base
        root.glow = tint()
        root.beginAmbientMotion()
        if accountSession == nil {
            buildLogin(in: root)
        } else {
            buildShell(in: root)
        }
        return root
    }

    private func styleInputField<T: NSTextField>(_ field: T, placeholder: String) -> T {
        field.placeholderString = placeholder
        field.focusRingType = .exterior
        field.isBezeled = false
        field.isEditable = true
        field.isSelectable = true
        field.drawsBackground = true
        field.backgroundColor = NSColor(calibratedRed: 0.16, green: 0.23,
                                        blue: 0.28, alpha: 1)
        field.textColor = .white
        field.font = NSFont.systemFont(ofSize: 15)
        field.controlSize = .large
        field.translatesAutoresizingMaskIntoConstraints = false
        field.heightAnchor.constraint(equalToConstant: 40).isActive = true
        return field
    }

    private func buildLogin(in root: NSView) {
        // Match the shared login: a simple welcome heading, username,
        // password and one action. No brand or extra explanatory copy.
        let form = stack(spacing: 15)
        form.addArrangedSubview(text("Welcome back", size: 27, weight: .bold))
        let username = styleInputField(NSTextField(), placeholder: "Username")
        usernameField = username
        let password = styleInputField(NSSecureTextField(), placeholder: "Password")
        passwordField = password
        form.addArrangedSubview(username)
        form.addArrangedSubview(password)

        let enter = button(busy ? "Signing in…" : "Sign in",
                           action: #selector(signIn(_:)), primary: true)
        form.addArrangedSubview(enter)
        enter.heightAnchor.constraint(equalToConstant: 51).isActive = true
        // AppKit NSStackView uses intrinsic-width hugging by default.
        // Explicitly stretch all controls across the centered login card.
        username.widthAnchor.constraint(equalTo: form.widthAnchor).isActive = true
        password.widthAnchor.constraint(equalTo: form.widthAnchor).isActive = true
        enter.widthAnchor.constraint(equalTo: form.widthAnchor).isActive = true

        // Authentication errors are actionable and never silently swallowed.
        if !status.isEmpty {
            form.addArrangedSubview(text(status, size: 12,
                                       color: status.hasPrefix("Sign-in failed")
                                       ? amber : muted))
        }

        let glass = card([form], radius: 26, padding: 30)
        root.addSubview(glass)
        NSLayoutConstraint.activate([
            glass.centerXAnchor.constraint(equalTo: root.centerXAnchor),
            glass.centerYAnchor.constraint(equalTo: root.centerYAnchor),
            glass.widthAnchor.constraint(equalToConstant: 440),
            glass.leadingAnchor.constraint(greaterThanOrEqualTo:
                root.leadingAnchor, constant: 20),
            glass.trailingAnchor.constraint(lessThanOrEqualTo:
                root.trailingAnchor, constant: -20),
            form.widthAnchor.constraint(equalTo: glass.widthAnchor, constant: -60)
        ])
    }

    private func buildShell(in root: NSView) {
        let sidebar = buildSidebar()
        sidebar.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(sidebar)
        NSLayoutConstraint.activate([
            sidebar.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            sidebar.topAnchor.constraint(equalTo: root.topAnchor),
            sidebar.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            sidebar.widthAnchor.constraint(equalToConstant: 258)
        ])
        let workspace = stack(spacing: 18)
        // A vertical NSStackView with .leading alignment gives its NSView
        // cards no full-width constraint. They can collapse to zero width.
        workspace.alignment = .leading
        let heading = stack(.horizontal, spacing: 12)
        heading.alignment = .centerY
        let titles = ["Quick connect", "Locations", "Settings", "My account"]
        heading.addArrangedSubview(text(titles[tab], size: 25, weight: .bold))
        let headerSpace = NSView()
        headerSpace.setContentHuggingPriority(.defaultLow, for: .horizontal)
        heading.addArrangedSubview(headerSpace)
        // The Windows reference has its only offline badge above the hero,
        // not a duplicate badge in the page title.
        // Keep the title outside the scroll view so it never scrolls offscreen.
        root.addSubview(heading)
        heading.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            heading.leadingAnchor.constraint(equalTo: sidebar.trailingAnchor,
                                             constant: 24),
            heading.trailingAnchor.constraint(equalTo: root.trailingAnchor,
                                              constant: -24),
            heading.topAnchor.constraint(equalTo: root.topAnchor, constant: 21)
        ])
        // NSStackView's .width alignment equalizes widths without fixing
        // horizontal origins. That caused Locations, Settings, and Account
        // panels to collect along the right edge of the macOS viewport.
        // Anchor every page to the leading edge and the full content width.
        func addPage(_ page: NSView) {
            page.translatesAutoresizingMaskIntoConstraints = false
            page.setContentHuggingPriority(.defaultLow, for: .horizontal)
            workspace.addArrangedSubview(page)
            page.widthAnchor.constraint(equalTo: workspace.widthAnchor)
                .isActive = true
        }
        switch tab {
        case 0:
            let availableWidth = nativeContentWidth - 258 - 48
            if availableWidth >= 790 {
                let pair = stack(.horizontal, spacing: 14)
                pair.alignment = .top
                pair.distribution = .fillEqually
                let connection = connectPage()
                let network = networkStatusPage()
                pair.addArrangedSubview(connection)
                pair.addArrangedSubview(network)
                network.heightAnchor.constraint(equalTo: connection.heightAnchor)
                    .isActive = true
                addPage(pair)
            } else {
                addPage(connectPage())
                addPage(networkStatusPage())
            }
        case 1: addPage(locationsPage())
        case 2: addPage(settingsPage())
        default: addPage(accountPage())
        }
        // Technical diagnostics belong in Settings, not in the user-facing
        // page canvas. The shell mirrors the clean Windows dashboard.
        // Keep the dashboard visible even before the account snapshot arrives
        // or when its contents exceed the macOS window height.
        let scroll = NSScrollView()
        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.drawsBackground = false
        scroll.hasVerticalScroller = true
        // On Catalina remote desktops, overlay scrollbars and trackpad
        // gestures can hide the only indication that content continues.
        scroll.autohidesScrollers = false
        scroll.verticalScrollElasticity = .allowed
        scroll.hasHorizontalScroller = false
        scroll.borderType = .noBorder

        let document = TwinNativeFlippedDocument()
        document.translatesAutoresizingMaskIntoConstraints = false
        document.addSubview(workspace)
        NSLayoutConstraint.activate([
            workspace.leadingAnchor.constraint(equalTo: document.leadingAnchor,
                                               constant: 24),
            workspace.trailingAnchor.constraint(equalTo: document.trailingAnchor,
                                                constant: -24),
            workspace.topAnchor.constraint(equalTo: document.topAnchor,
                                           constant: 4),
            workspace.bottomAnchor.constraint(equalTo: document.bottomAnchor,
                                              constant: -18)
        ])
        scroll.documentView = document
        scroll.contentView.scroll(to: .zero)
        root.addSubview(scroll)
        NSLayoutConstraint.activate([
            scroll.leadingAnchor.constraint(equalTo: sidebar.trailingAnchor),
            scroll.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            scroll.topAnchor.constraint(equalTo: heading.bottomAnchor,
                                          constant: 11),
            scroll.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            document.widthAnchor.constraint(equalTo: scroll.contentView.widthAnchor),
            document.heightAnchor.constraint(greaterThanOrEqualTo:
                                             scroll.contentView.heightAnchor)
        ])
        // Force the document to lay out its full natural height rather than
        // treating the visible clip as the entire page. No off-screen cards
        // should be unreachable by the mouse wheel or scrollbar.
        workspace.setContentHuggingPriority(.required, for: .vertical)
        document.layoutSubtreeIfNeeded()
        scroll.reflectScrolledClipView(scroll.contentView)
    }

    // Native vector glyphs keep the Windows icon language sharp on Retina
    // and on Catalina, where SF Symbols systemSymbolName is unavailable.
    // 0 bolt, 1 location, 2 settings, 3 account, 4 support,
    // 5 renewal, 6 website.
    private func sidebarIcon(_ kind: Int) -> NSImage {
        let output = NSImage(size: NSSize(width: 23, height: 23),
                             flipped: false) { rect in
            let unit = rect.width / 20
            func pt(_ x: CGFloat, _ y: CGFloat) -> NSPoint {
                NSPoint(x: x * unit, y: y * unit)
            }
            let path = NSBezierPath()
            path.lineWidth = 1.85 * unit
            path.lineCapStyle = .round
            path.lineJoinStyle = .round
            switch kind {
            case 0:
                path.move(to: pt(11, 18))
                path.line(to: pt(5, 9))
                path.line(to: pt(10, 9))
                path.line(to: pt(8, 2))
                path.line(to: pt(16, 12))
                path.line(to: pt(11, 12))
                path.close()
            case 1:
                path.move(to: pt(10, 2))
                path.curve(to: pt(4, 11), controlPoint1: pt(7, 6),
                          controlPoint2: pt(4, 8))
                path.curve(to: pt(16, 11), controlPoint1: pt(4, 19),
                          controlPoint2: pt(16, 19))
                path.curve(to: pt(10, 2), controlPoint1: pt(16, 8),
                          controlPoint2: pt(13, 6))
                path.appendOval(in: NSRect(x: 8 * unit, y: 10 * unit,
                                          width: 4 * unit, height: 4 * unit))
            case 2:
                // Windows sidebar uses the three horizontal sliders icon.
                for (y, knob) in [(CGFloat(5), CGFloat(7)),
                                  (CGFloat(10), CGFloat(13)),
                                  (CGFloat(15), CGFloat(8))] {
                    path.move(to: pt(2, y))
                    path.line(to: pt(18, y))
                    path.appendOval(in: NSRect(x: (knob - 1.8) * unit,
                                              y: (y - 1.8) * unit,
                                              width: 3.6 * unit,
                                              height: 3.6 * unit))
                }
            case 3:
                path.appendOval(in: NSRect(x: 7 * unit, y: 11 * unit,
                                          width: 6 * unit, height: 6 * unit))
                path.move(to: pt(3, 3))
                path.curve(to: pt(17, 3), controlPoint1: pt(2, 12),
                          controlPoint2: pt(18, 12))
            case 4:
                path.move(to: pt(3, 9))
                path.curve(to: pt(17, 9), controlPoint1: pt(2, 20),
                          controlPoint2: pt(18, 20))
                path.move(to: pt(3, 10))
                path.line(to: pt(3, 5))
                path.line(to: pt(6, 5))
                path.line(to: pt(6, 11))
                path.move(to: pt(17, 10))
                path.line(to: pt(17, 5))
                path.line(to: pt(14, 5))
                path.line(to: pt(14, 11))
            case 5:
                path.move(to: pt(16, 12))
                path.curve(to: pt(5, 6), controlPoint1: pt(18, 5),
                          controlPoint2: pt(9, 2))
                path.move(to: pt(5, 6))
                path.line(to: pt(5, 11))
                path.line(to: pt(10, 11))
                path.move(to: pt(4, 9))
                path.curve(to: pt(15, 14), controlPoint1: pt(2, 16),
                          controlPoint2: pt(11, 18))
            default:
                path.appendOval(in: NSRect(x: 2 * unit, y: 2 * unit,
                                          width: 16 * unit, height: 16 * unit))
                path.appendOval(in: NSRect(x: 7 * unit, y: 2 * unit,
                                          width: 6 * unit, height: 16 * unit))
                path.move(to: pt(2, 10))
                path.line(to: pt(18, 10))
            }
            NSColor.white.setStroke()
            path.stroke()
            return true
        }
        output.isTemplate = true
        return output
    }

    private func buildSidebar() -> NSView {
        // One continuous Windows-style canvas spans BOTH the navigation
        // and content. Do not install a second full-height tinted glass card
        // over the sidebar: it creates a hard vertical seam and hides the
        // branded radial artwork beneath it.
        let side = NSView(frame: .zero)
        side.translatesAutoresizingMaskIntoConstraints = false
        side.wantsLayer = true
        side.layer?.backgroundColor = NSColor.clear.cgColor
        side.layer?.borderWidth = 0
        // Individual navigation controls stay glass. The sidebar itself
        // intentionally paints nothing, exposing TwinNativeBackdrop below.

        let content = stack(spacing: 12)
        content.alignment = .leading
        let logo = NSView()
        logo.wantsLayer = true
        logo.layer?.cornerRadius = 13
        logo.layer?.backgroundColor = tint().cgColor
        logo.layer?.borderColor = sea.withAlphaComponent(0.38).cgColor
        logo.layer?.borderWidth = 1
        logo.translatesAutoresizingMaskIntoConstraints = false
        logo.widthAnchor.constraint(equalToConstant: 47).isActive = true
        logo.heightAnchor.constraint(equalToConstant: 47).isActive = true
        if let tenantLogo = tenantLogo {
            let image = NSImageView(image: tenantLogo)
            image.imageScaling = .scaleProportionallyUpOrDown
            image.translatesAutoresizingMaskIntoConstraints = false
            logo.addSubview(image)
            NSLayoutConstraint.activate([
                image.leadingAnchor.constraint(equalTo: logo.leadingAnchor, constant: 3),
                image.trailingAnchor.constraint(equalTo: logo.trailingAnchor, constant: -3),
                image.topAnchor.constraint(equalTo: logo.topAnchor, constant: 3),
                image.bottomAnchor.constraint(equalTo: logo.bottomAnchor, constant: -3)
            ])
        } else {
            let infinity = text("∞", size: 26, weight: .bold)
            infinity.translatesAutoresizingMaskIntoConstraints = false
            logo.addSubview(infinity)
            NSLayoutConstraint.activate([
                infinity.centerXAnchor.constraint(equalTo: logo.centerXAnchor),
                infinity.centerYAnchor.constraint(equalTo: logo.centerYAnchor)
            ])
        }
        let logoRow = stack(.horizontal, spacing: 0)
        let startSpace = NSView()
        let endSpace = NSView()
        logoRow.addArrangedSubview(startSpace)
        logoRow.addArrangedSubview(logo)
        logoRow.addArrangedSubview(endSpace)
        startSpace.widthAnchor.constraint(equalTo: endSpace.widthAnchor).isActive = true
        content.addArrangedSubview(logoRow)
        logoRow.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        let brand = text(accountSession?.brandName ?? "TwinConnect",
                         size: 18, weight: .bold)
        brand.alignment = .center
        content.addArrangedSubview(brand)
        brand.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        content.setCustomSpacing(31, after: brand)

        let navs = ["Quick connect", "Locations", "Settings", "Account"]
        let selectedLocation = snapshot?.servers.first { $0.id == activeServer }
        let selectedFlag = selectedLocation.map { flag($0.country) } ?? "🌐"
        for (index, label) in navs.enumerated() {
            // Center the whole icon + label group inside each navigation
            // card. Leading alignment plus whitespace in the title pushed
            // all labels against the left edge on Catalina.
            // NSButton's imageLeft cell keeps the image anchored to the
            // leading edge even when its title is centered. Use one centered
            // overlay for BOTH glyph and text, preserving the real button hit
            // target and accessibility title.
            let control = button(label,
                action: #selector(changeTab(_:)), tag: index,
                primary: tab == index, mutedButton: true)
            control.title = ""
            control.attributedTitle = NSAttributedString(string: "")
            control.setAccessibilityLabel(label)
            let centeredLabel = stack(.horizontal, spacing: 12)
            centeredLabel.alignment = .centerY
            if index == 1 {
                centeredLabel.addArrangedSubview(
                    text(selectedFlag, size: 21, weight: .medium))
            } else {
                let glyph = NSImageView(image: sidebarIcon(index))
                glyph.imageScaling = .scaleProportionallyDown
                glyph.contentTintColor = tab == index ? NSColor.white : tint()
                glyph.translatesAutoresizingMaskIntoConstraints = false
                glyph.widthAnchor.constraint(equalToConstant: 23).isActive = true
                glyph.heightAnchor.constraint(equalToConstant: 23).isActive = true
                centeredLabel.addArrangedSubview(glyph)
            }
            centeredLabel.addArrangedSubview(
                text(label, size: 13, weight: .semibold))
            centeredLabel.setContentHuggingPriority(.required, for: .horizontal)
            control.addSubview(centeredLabel)
            NSLayoutConstraint.activate([
                centeredLabel.centerXAnchor.constraint(equalTo: control.centerXAnchor),
                centeredLabel.centerYAnchor.constraint(equalTo: control.centerYAnchor),
                centeredLabel.leadingAnchor.constraint(
                    greaterThanOrEqualTo: control.leadingAnchor, constant: 12),
                centeredLabel.trailingAnchor.constraint(
                    lessThanOrEqualTo: control.trailingAnchor, constant: -12)
            ])
            control.heightAnchor.constraint(equalToConstant: 54).isActive = true
            control.layer?.cornerRadius = 16
            control.layer?.borderWidth = 1
            if tab == index {
                control.setAccentGradient(
                    (tint().blended(withFraction: 0.26, of: .white) ?? tint())
                        .withAlphaComponent(0.70),
                    (tint().blended(withFraction: 0.16, of: .black) ?? tint())
                        .withAlphaComponent(0.54))
                control.layer?.borderColor = tint().withAlphaComponent(0.48).cgColor
            } else {
                control.setAccentGradient(
                    (NSColor(calibratedRed: 0.14, green: 0.25, blue: 0.30, alpha: 1)
                        .blended(withFraction: 0.30, of: tint()) ?? tint())
                        .withAlphaComponent(0.38),
                    (NSColor(calibratedRed: 0.09, green: 0.17, blue: 0.21, alpha: 1)
                        .blended(withFraction: 0.19, of: tint()) ?? tint())
                        .withAlphaComponent(0.26))
                control.layer?.borderColor = tint().withAlphaComponent(0.22).cgColor
            }
            content.addArrangedSubview(control)
            control.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        }

        let quick = stack(.horizontal, spacing: 5)
        quick.distribution = .fillEqually
        let linkDefinitions: [(String, Int, Selector, URL?)] = [
            ("Support", 4, #selector(openSupport(_:)), accountSession?.supportURL),
            ("Renew", 5, #selector(openRenewal(_:)), accountSession?.renewalURL),
            ("Website", 6, #selector(openWebsite(_:)), accountSession?.websiteURL)
        ]
        for (title, kind, action, target) in linkDefinitions where target != nil {
            let link = button(title, action: action, mutedButton: true)
            link.image = sidebarIcon(kind)
            link.imagePosition = .imageAbove
            link.imageScaling = .scaleProportionallyDown
            link.contentTintColor = sea
            link.heightAnchor.constraint(equalToConstant: 62).isActive = true
            link.layer?.cornerRadius = 12
            link.layer?.borderColor = sea.withAlphaComponent(0.35).cgColor
            link.setAccentGradient(
                (NSColor(calibratedRed: 0.15, green: 0.27, blue: 0.32, alpha: 1)
                    .blended(withFraction: 0.32, of: tint()) ?? tint())
                    .withAlphaComponent(0.39),
                (NSColor(calibratedRed: 0.09, green: 0.19, blue: 0.23, alpha: 1)
                    .blended(withFraction: 0.20, of: tint()) ?? tint())
                    .withAlphaComponent(0.27))
            quick.addArrangedSubview(link)
        }
        if accountSession?.supportURL != nil ||
           accountSession?.renewalURL != nil ||
           accountSession?.websiteURL != nil {
            let links = card([quick], radius: 14, padding: 7)
            content.addArrangedSubview(links)
            links.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        }

        // Keep account details at the bottom, like the Windows sidebar.
        let flexSpacer = NSView()
        flexSpacer.translatesAutoresizingMaskIntoConstraints = false
        flexSpacer.setContentHuggingPriority(.defaultLow, for: .vertical)
        content.addArrangedSubview(flexSpacer)
        let summary = stack(spacing: 5)
        summary.addArrangedSubview(text(accountSession?.username ?? "",
                                        size: 11, weight: .semibold))
        summary.addArrangedSubview(text("Signed in", size: 10, color: muted))
        let identity = card([summary], radius: 18, padding: 12)
        content.addArrangedSubview(identity)
        identity.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        // Match Windows: language control and settings gear live below
        // the signed-in identity; sign-out is in Account, not the sidebar.
        let languageRow = stack(.horizontal, spacing: 0)
        let languageLeft = NSView()
        let languageRight = NSView()
        languageRow.addArrangedSubview(languageLeft)
        let languageButton = button("◎   EN   ⌄",
                                    action: #selector(openLanguageSettings(_:)),
                                    mutedButton: true)
        languageButton.toolTip = "Language preferences (English is available)"
        languageButton.widthAnchor.constraint(equalToConstant: 118).isActive = true
        languageButton.heightAnchor.constraint(equalToConstant: 38).isActive = true
        languageRow.addArrangedSubview(languageButton)
        languageRow.addArrangedSubview(languageRight)
        languageLeft.widthAnchor.constraint(equalTo: languageRight.widthAnchor)
            .isActive = true
        content.addArrangedSubview(languageRow)
        languageRow.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true

        let settingsRow = stack(.horizontal, spacing: 0)
        let settingsLeft = NSView()
        let settingsRight = NSView()
        settingsRow.addArrangedSubview(settingsLeft)
        let gear = button("⚙", action: #selector(openLanguageSettings(_:)),
                          mutedButton: true)
        gear.widthAnchor.constraint(equalToConstant: 39).isActive = true
        gear.heightAnchor.constraint(equalToConstant: 34).isActive = true
        gear.toolTip = "Settings"
        settingsRow.addArrangedSubview(gear)
        settingsRow.addArrangedSubview(settingsRight)
        settingsLeft.widthAnchor.constraint(equalTo: settingsRight.widthAnchor)
            .isActive = true
        content.addArrangedSubview(settingsRow)
        settingsRow.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        // Independent vertical safe-areas match the Windows navigation:
        // branding starts below the title bar; the language/gear controls
        // float above the bottom edge rather than touching the window.
        content.translatesAutoresizingMaskIntoConstraints = false
        side.addSubview(content)
        NSLayoutConstraint.activate([
            content.leadingAnchor.constraint(equalTo: side.leadingAnchor,
                                             constant: 17),
            content.trailingAnchor.constraint(equalTo: side.trailingAnchor,
                                              constant: -17),
            content.topAnchor.constraint(equalTo: side.topAnchor, constant: 27),
            content.bottomAnchor.constraint(equalTo: side.bottomAnchor,
                                            constant: -46)
        ])
        return side
    }

    private func connectPage() -> NSView {
        let main = stack(spacing: 10)
        main.alignment = .leading

        let offlineRow = stack(.horizontal, spacing: 8)
        let leadingSpace = NSView()
        let trailingSpace = NSView()
        offlineRow.addArrangedSubview(leadingSpace)
        offlineRow.addArrangedSubview(pill("◌  You are offline", color: muted))
        offlineRow.addArrangedSubview(trailingSpace)
        leadingSpace.widthAnchor.constraint(equalTo: trailingSpace.widthAnchor)
            .isActive = true
        main.addArrangedSubview(offlineRow)
        offlineRow.widthAnchor.constraint(equalTo: main.widthAnchor).isActive = true

        let fabric = TwinNativeNetworkFabric(frame:
            NSRect(x: 0, y: 0, width: 330, height: 165))
        fabric.translatesAutoresizingMaskIntoConstraints = false
        fabric.heightAnchor.constraint(equalToConstant: 162).isActive = true
        // The old backdrop was an empty rectangle. This status overlay is
        // explicitly a selectable local proxy test, not a connected VPN.
        // The vector illustration itself remains in the hero; the current
        // selection appears below so no text obscures the network strands.
        main.addArrangedSubview(fabric)
        fabric.widthAnchor.constraint(equalTo: main.widthAnchor).isActive = true
        // Windows places the selected location only in Network Status,
        // not as a second caption underneath the hero illustration.

        let buttonRow = stack(.horizontal, spacing: 0)
        let leftGap = NSView()
        let rightGap = NSView()
        buttonRow.addArrangedSubview(leftGap)
        // Mirror the original Windows primary button. An unsigned macOS
        // build cannot connect a system VPN, so this button must NEVER
        // silently launch the Hysteria2 diagnostic SOCKS engine.
        let connect = button("ϟ    Check TUN readiness     ›",
                             action: #selector(unavailableConnect(_:)), primary: true)
        connect.isEnabled = accountSession != nil && !cliTunCheckBusy
        connect.toolTip = "Validate the selected Hysteria2 TUN profile without changing routes or starting VPN."
        connect.heightAnchor.constraint(equalToConstant: 54).isActive = true
        connect.layer?.cornerRadius = 17
        connect.layer?.borderColor = sea.withAlphaComponent(0.9).cgColor
        connect.layer?.shadowColor = sea.cgColor
        connect.layer?.shadowOpacity = TwinNativeRenderBudget.lightweight ? 0 : 0.17
        connect.layer?.shadowRadius = 10
        connect.layer?.shadowOffset = CGSize(width: 0, height: -2)
        connect.widthAnchor.constraint(equalToConstant: 255).isActive = true
        // On unsigned cloud Macs the system VPN remains disabled. Offer a
        // separate, explicitly labelled, one-request local SOCKS egress test.
        // Never label proxy egress as a connected system VPN.

        buttonRow.addArrangedSubview(connect)
        buttonRow.addArrangedSubview(rightGap)
        leftGap.widthAnchor.constraint(equalTo: rightGap.widthAnchor).isActive = true
        main.addArrangedSubview(buttonRow)
        buttonRow.widthAnchor.constraint(equalTo: main.widthAnchor).isActive = true
        // Diagnostics, emergency shutdown and technical warnings belong
        // in Settings. This visual dashboard has the same clean composition
        // as Windows; no SOCKS process starts from Quick Connect.
        if !status.isEmpty && (status.contains("TUN") || status.contains("Connection unavailable")) {
            let advisory = text(status,
                                size: 10, color: amber)
            main.addArrangedSubview(advisory)
        }


        // NSStackView with .leading alignment does not automatically
        // stretch this nested account card. Pin it to the full hero width.
        let subscription = homeSubscriptionSummary()
        main.addArrangedSubview(subscription)
        subscription.widthAnchor.constraint(equalTo: main.widthAnchor).isActive = true

        let selectedServer = snapshot?.servers.first { $0.id == activeServer }
        let location = selectedServer.map {
            flag($0.country) + " " + countryName($0.country)
        } ?? "Choose location"
        let protocolName = snapshot?.protocols.first {
            $0.code == activeProtocol
        }?.name ?? "Choose protocol"

        // The Windows Quick Connect layout has no redundant three-tile
        // location/IP/protocol footer. Selection is available in the
        // Network status location bar; keep this pane compact and unclipped.
        return card([main], radius: 25, padding: 15, style: .panel)
    }

    private func networkMetric(_ title: String, value: String,
                               subtitle: String = "",
                               valueColor: NSColor? = nil) -> NSView {
        let content = stack(spacing: 12)
        content.alignment = .leading
        let iconName: String
        if title.contains("ping") { iconName = "ϟ" }
        else if title.contains("IP") { iconName = "◎" }
        else if title.contains("Download") { iconName = "↓" }
        else { iconName = "↑" }
        let heading = stack(.horizontal, spacing: 9)
        let iconPlate = NSView()
        iconPlate.wantsLayer = true
        iconPlate.layer?.cornerRadius = 9
        iconPlate.layer?.backgroundColor = sea.withAlphaComponent(0.19).cgColor
        iconPlate.layer?.borderColor = sea.withAlphaComponent(0.34).cgColor
        iconPlate.layer?.borderWidth = 1
        iconPlate.translatesAutoresizingMaskIntoConstraints = false
        iconPlate.widthAnchor.constraint(equalToConstant: 30).isActive = true
        iconPlate.heightAnchor.constraint(equalToConstant: 30).isActive = true
        let symbol = text(iconName, size: 19, weight: .semibold, color: sea)
        symbol.translatesAutoresizingMaskIntoConstraints = false
        iconPlate.addSubview(symbol)
        NSLayoutConstraint.activate([
            symbol.centerXAnchor.constraint(equalTo: iconPlate.centerXAnchor),
            symbol.centerYAnchor.constraint(equalTo: iconPlate.centerYAnchor)
        ])
        heading.addArrangedSubview(iconPlate)
        heading.addArrangedSubview(text(title, size: 12,
                                       weight: .medium, color: muted))
        content.addArrangedSubview(heading)
        let number = text(value, size: 23, weight: .bold,
                          color: valueColor ?? NSColor.white)
        number.lineBreakMode = .byTruncatingTail
        number.maximumNumberOfLines = 1
        number.toolTip = value
        content.addArrangedSubview(number)
        if !subtitle.isEmpty {
            let subtitleText = text(subtitle, size: 10, color: muted)
            subtitleText.lineBreakMode = .byTruncatingTail
            subtitleText.maximumNumberOfLines = 2
            subtitleText.toolTip = subtitle
            content.addArrangedSubview(subtitleText)
        }
        if title == "Download" || title == "Upload" {
            // A neutral divider represents unavailable traffic while offline,
            // never a fabricated chart or session throughput.
            let idleLine = NSView()
            idleLine.translatesAutoresizingMaskIntoConstraints = false
            idleLine.wantsLayer = true
            idleLine.layer?.backgroundColor = sea.withAlphaComponent(0.28).cgColor
            idleLine.heightAnchor.constraint(equalToConstant: 1).isActive = true
            content.addArrangedSubview(idleLine)
            idleLine.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        }
        let panel = card([content], radius: 17, padding: 14, style: .metric)
        panel.heightAnchor.constraint(greaterThanOrEqualToConstant: 126)
            .isActive = true
        return panel
    }

    private func networkStatusPage() -> NSView {
        let content = stack(spacing: 13)
        content.alignment = .leading
        let header = stack(.horizontal, spacing: 9)
        header.addArrangedSubview(text("Network status", size: 17,
                                       weight: .semibold))
        let spacer = NSView()
        spacer.setContentHuggingPriority(.defaultLow, for: .horizontal)
        header.addArrangedSubview(spacer)
        header.addArrangedSubview(pill("Disconnected", color: muted))
        content.addArrangedSubview(header)
        header.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true

        // Windows layout: timing and manual refresh share a single row.
        // The timer remains at zero until a real PacketTunnel is connected.
        let timing = stack(.horizontal, spacing: 8)
        timing.addArrangedSubview(text("◷  Connected for    00:00:00",
                                       size: 12, color: muted))
        let timingSpace = NSView()
        timingSpace.setContentHuggingPriority(.defaultLow, for: .horizontal)
        timing.addArrangedSubview(timingSpace)
        let timingRefresh = button("↻", action: #selector(refresh(_:)),
                                   mutedButton: true)
        timingRefresh.widthAnchor.constraint(equalToConstant: 35).isActive = true
        timingRefresh.heightAnchor.constraint(equalToConstant: 32).isActive = true
        timingRefresh.toolTip = "Refresh actual subscription and ping status"
        timing.addArrangedSubview(timingRefresh)
        content.addArrangedSubview(timing)
        timing.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true

        let selected = snapshot?.servers.first { $0.id == activeServer }
        let reportedPing = pingText(selected)

        let network = stack(.horizontal, spacing: 10)
        network.distribution = .fillEqually
        network.addArrangedSubview(networkMetric("Server ping", value: reportedPing,
            subtitle: pingDetails(selected), valueColor: pingColor(selected)))
        network.addArrangedSubview(networkMetric("Public IP", value: "—"))
        content.addArrangedSubview(network)
        network.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true

        let traffic = stack(.horizontal, spacing: 10)
        traffic.distribution = .fillEqually
        traffic.addArrangedSubview(networkMetric("Download", value: "—",
                                                  subtitle: "Session total: —"))
        traffic.addArrangedSubview(networkMetric("Upload", value: "—",
                                                  subtitle: "Session total: —"))
        content.addArrangedSubview(traffic)
        traffic.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true

        let location = selected.map {
            flag($0.country) + "  " + countryName($0.country)
        } ?? "Select location"
        let locationRow = stack(.horizontal, spacing: 9)
        locationRow.addArrangedSubview(text(location, size: 13, weight: .semibold))
        let locationSpacer = NSView()
        locationSpacer.setContentHuggingPriority(.defaultLow, for: .horizontal)
        locationRow.addArrangedSubview(locationSpacer)
        let change = button("Locations  ›",
            action: #selector(showLocations(_:)), mutedButton: true)
        change.heightAnchor.constraint(equalToConstant: 38).isActive = true
        change.widthAnchor.constraint(equalToConstant: 118).isActive = true
        locationRow.addArrangedSubview(change)
        let locationCard = card([locationRow], radius: 13, padding: 8,
                                style: .inset)
        content.addArrangedSubview(locationCard)
        locationCard.widthAnchor.constraint(equalTo: content.widthAnchor)
            .isActive = true
        // The previous equal-height dashboard stretched this single
        // location row into a huge empty rectangle.
        locationCard.heightAnchor.constraint(equalToConstant: 55).isActive = true
        let flexibleBottom = NSView()
        flexibleBottom.setContentHuggingPriority(.defaultLow, for: .vertical)
        content.addArrangedSubview(flexibleBottom)

        // Offline mode never fabricates session bytes, handshakes or an IP.
        return card([content], radius: 25, padding: 20, style: .panel)
    }

    // Prefer a fresh local ICMP reply. A panel latency is identified as
    // approximate and never presented as an on-device ping.
    private func pingText(_ server: TwinMacNativeServer?) -> String {
        guard let server = server else { return "— ms" }
        if nodePingBusy.contains(server.id) { return "…" }
        if let result = nodePingResults[server.id] {
            if let rtt = result.measuredMs { return "\(rtt) ms" }
            return result.errorCode == "NO_PROBE_ADDRESS" ? "No IP" : "— ms"
        }
        if let reported = server.latencyMs { return "≈\(reported) ms" }
        return server.probeIP == nil ? "No IP" : "— ms"
    }

    private func pingColor(_ server: TwinMacNativeServer?) -> NSColor {
        guard let server = server else { return muted }
        let value: Int?
        if let result = nodePingResults[server.id] {
            value = result.measuredMs
        } else {
            value = server.latencyMs
        }
        guard let latency = value else { return muted }
        if latency <= 300 {
            return NSColor(calibratedRed: 0.21, green: 0.85, blue: 0.65, alpha: 1)
        }
        if latency <= 700 { return amber }
        return NSColor(calibratedRed: 1.0, green: 0.41, blue: 0.48, alpha: 1)
    }

    private func pingDetails(_ server: TwinMacNativeServer?) -> String {
        guard let server = server else { return "No location selected" }
        if nodePingBusy.contains(server.id) { return "ICMP ping in progress" }
        if let result = nodePingResults[server.id] {
            if result.measuredMs != nil { return "ICMP round-trip time from this Mac" }
            switch result.errorCode {
            case "NO_PROBE_ADDRESS": return "Panel provided no public ping address"
            case "ICMP_TIMEOUT_OR_BLOCKED": return "No ping reply (ICMP may be blocked)"
            case "PING_PROGRAM_UNAVAILABLE": return "macOS ping executable unavailable"
            default: return "ICMP reply could not be measured"
            }
        }
        return server.latencyMs != nil ? "Approximate latency reported by panel" :
            "ICMP has not been measured"
    }

    private func beginNodePing(_ server: TwinMacNativeServer) {
        guard let current = accountSession,
              !nodePingBusy.contains(server.id) else { return }
        let generation = pingGeneration
        let token = current.accessToken
        nodePingBusy.insert(server.id)
        TwinMacNativePing.probe(server.probeIP) { [weak self] result in
            guard let self = self, self.pingGeneration == generation,
                  self.accountSession?.accessToken == token else { return }
            self.nodePingBusy.remove(server.id)
            self.nodePingResults[server.id] = result
            if self.pingAllBusy { self.startNextNodePings() }
            self.schedulePingRedraw()
        }
    }

    // Coalesce ping redraws to keep low-powered remote AppKit desktops responsive.
    private func schedulePingRedraw() {
        guard !pingRedrawScheduled else { return }
        pingRedrawScheduled = true
        let generation = pingGeneration
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in
            guard let self = self else { return }
            self.pingRedrawScheduled = false
            guard self.pingGeneration == generation, self.accountSession != nil,
                  self.tab == 0 || self.tab == 1 else { return }
            self.view = self.build()
        }
    }

    // At most four simultaneous ICMP processes, same concurrency as Windows.
    private func startNextNodePings() {
        while pingAllBusy && nodePingBusy.count < 4 && !nodePingQueue.isEmpty {
            let server = nodePingQueue.removeFirst()
            if !nodePingBusy.contains(server.id) {
                beginNodePing(server)
            }
        }
        if pingAllBusy && nodePingQueue.isEmpty && nodePingBusy.isEmpty {
            pingAllBusy = false
        }
    }

    private func pingNodes(_ nodes: [TwinMacNativeServer]) {
        guard accountSession != nil, !pingAllBusy, !nodes.isEmpty else { return }
        pingAllBusy = true
        nodePingQueue = nodes
        startNextNodePings()
        view = build()
    }

    @objc private func selectFastestMeasuredServer(_ sender: NSButton) {
        guard let servers = snapshot?.servers else { return }
        let eligible = servers.filter {
            $0.online && nodePingResults[$0.id]?.measuredMs != nil
        }
        guard let best = eligible.min(by: {
            (nodePingResults[$0.id]?.measuredMs ?? Int.max) <
                (nodePingResults[$1.id]?.measuredMs ?? Int.max)
        }) else { return }
        activeServer = best.id
        expandedCountries.insert(best.country.uppercased())
        persistCurrentSelection()
        view = build()
    }

    @objc private func pingAllServers(_ sender: NSButton) {
        guard let nodes = snapshot?.servers, !nodes.isEmpty else { return }
        pingNodes(nodes)
    }

    @objc private func pingOneServer(_ sender: NSButton) {
        guard !pingAllBusy,
              locationRowIDs.indices.contains(sender.tag),
              let server = snapshot?.servers.first(where: {
                  $0.id == locationRowIDs[sender.tag]
              }), !nodePingBusy.contains(server.id) else { return }
        beginNodePing(server)
        view = build()
    }

    private func selectionPreferenceKey(_ session: TwinMacNativeSession) -> String {
        // Tenant-scoped and account-scoped; never place credentials or
        // usernames in UserDefaults keys.
        let identity = session.namespace + ":" + session.username.lowercased()
        let digest = SHA256.hash(data: Data(identity.utf8))
        let hex = digest.map { String(format: "%02x", $0) }.joined()
        return "twinconnect.macos.selection.v1." + hex
    }

    private func persistCurrentSelection() {
        guard let session = accountSession else { return }
        let key = selectionPreferenceKey(session)
        UserDefaults.standard.set([
            "server": activeServer ?? "",
            "protocol": activeProtocol ?? ""
        ], forKey: key)
    }

    private func restoreCurrentSelection(_ session: TwinMacNativeSession) {
        guard let record = UserDefaults.standard.dictionary(
            forKey: selectionPreferenceKey(session)) else {
            activeServer = nil
            activeProtocol = nil
            return
        }
        let savedServer = record["server"] as? String ?? ""
        let savedProtocol = record["protocol"] as? String ?? ""
        activeServer = savedServer.isEmpty ? nil : savedServer
        activeProtocol = savedProtocol.isEmpty ? nil : savedProtocol
    }

    private func countryName(_ code: String) -> String {
        Locale(identifier: "en_US").localizedString(forRegionCode: code.uppercased())
            ?? code.uppercased()
    }

    private func friendlyServerName(_ server: TwinMacNativeServer,
                                    index: Int) -> String {
        let trimmed = server.name.trimmingCharacters(in: .whitespacesAndNewlines)
        let plain = trimmed.lowercased()
        let code = server.country.lowercased()
        let aliases: [String: Set<String>] = [
            "fi": ["fin", "finland", "fi", "fin1", "fin-1"],
            "de": ["des", "ger", "germany", "de", "de1", "de-1"],
            "ca": ["can", "canada", "ca"],
            "tr": ["tur", "turkey", "turkiye", "tr"],
            "us": ["usa", "united states", "us"],
            "gb": ["uk", "eng", "england", "united kingdom", "gb"],
            "fr": ["fra", "france", "fr"],
            "hk": ["hongkong", "hong kong", "hk"],
            "ir": ["iran", "ir"],
            "nl": ["netherlands", "nld", "nl"]
        ]
        // Only change the PRESENTATION. The real node ID and server config
        // still come from the authorized panel record.
        if plain == code || plain == countryName(code).lowercased() ||
           plain == "server" || plain.isEmpty ||
           (aliases[code]?.contains(plain) ?? false) {
            return countryName(code) + "  ·  Server " + String(index + 1)
        }
        return trimmed
    }

    private func protocolChips() -> NSView {
        let list = snapshot?.protocols ?? []
        let favorites = Set(["hysteria2", "v2ray", "wireguard", "openvpn"])
        let options = [("All", Optional<String>.none)] +
            list.filter { showAllProtocolChips || favorites.contains($0.code) ||
                          $0.code == activeProtocol }
                .map { ($0.name, Optional($0.code)) }
        protocolChipCodes = options.map { $0.1 }
        let group = stack(spacing: 7)
        group.alignment = .leading
        // Use the same horizontal, wrapping protocol pills as Flutter.
        // Fit by actual label width, not arbitrary protocol counts per row.
        let width = max(430, nativeContentWidth - 258 - 102)
        var row = stack(.horizontal, spacing: 7)
        row.alignment = .centerY
        var used: CGFloat = 0
        for (index, option) in options.enumerated() {
            let size = (option.0 as NSString).size(withAttributes: [
                .font: NSFont.systemFont(ofSize: 11, weight: .semibold)
            ]).width
            let chipWidth = min(185, max(58, ceil(size) + 27))
            if used + chipWidth > width && used > 0 {
                group.addArrangedSubview(row)
                row.widthAnchor.constraint(equalTo: group.widthAnchor).isActive = true
                row = stack(.horizontal, spacing: 7)
                row.alignment = .centerY
                used = 0
            }
            let selected = activeProtocol == option.1
            let chip = button(option.0, action: #selector(selectProtocolChip(_:)),
                              tag: index, primary: selected, mutedButton: !selected)
            chip.font = .systemFont(ofSize: 11, weight: .medium)
            chip.layer?.cornerRadius = 15
            chip.heightAnchor.constraint(equalToConstant: 31).isActive = true
            chip.widthAnchor.constraint(equalToConstant: chipWidth).isActive = true
            row.addArrangedSubview(chip)
            used += chipWidth + 7
        }
        group.addArrangedSubview(row)
        row.widthAnchor.constraint(equalTo: group.widthAnchor).isActive = true
        if list.count > options.count - 1 || showAllProtocolChips {
            let more = button(showAllProtocolChips ? "Show fewer protocols  ⌃" :
                              "All protocols (" + String(list.count) + ")  ⌄",
                              action: #selector(toggleAllProtocolChips(_:)),
                              mutedButton: true)
            more.heightAnchor.constraint(equalToConstant: 33).isActive = true
            group.addArrangedSubview(more)
        }
        return group
    }

    // Locations follow Flutter's Search -> protocol chips -> country accordion.
    // All data is scoped to the authenticated panel session. Node inventory
    // alone never guarantees a protocol-specific connection profile.
    // The country accordion is the real interactive server directory.
    // Compact, clearly selected rows; latency means ICMP only, not VPN health.
    private func locationsPage() -> NSView {
        let wrapper = stack(spacing: 16)
        wrapper.alignment = .leading

        let heading = stack(.horizontal, spacing: 12)
        heading.addArrangedSubview(text("Server locations", size: 23, weight: .bold))
        let spacer = NSView()
        spacer.setContentHuggingPriority(.defaultLow, for: .horizontal)
        heading.addArrangedSubview(spacer)
        let refresh = button("↻  Refresh", action: #selector(refresh(_:)),
                             mutedButton: true)
        refresh.heightAnchor.constraint(equalToConstant: 34).isActive = true
        heading.addArrangedSubview(refresh)
        wrapper.addArrangedSubview(heading)
        heading.widthAnchor.constraint(equalTo: wrapper.widthAnchor).isActive = true
        wrapper.addArrangedSubview(text(
            "Choose a location and protocol. Ping is measured from this Mac.",
            size: 12, color: muted))

        let searchRow = stack(.horizontal, spacing: 10)
        searchRow.alignment = .centerY
        let search = NSSearchField()
        search.placeholderString = "Search by server or country"
        search.stringValue = locationSearch
        search.sendsWholeSearchString = true
        search.sendsSearchStringImmediately = false
        search.toolTip = "Press Return to filter available locations"
        search.target = self
        search.action = #selector(searchLocations(_:))
        search.translatesAutoresizingMaskIntoConstraints = false
        search.heightAnchor.constraint(equalToConstant: 42).isActive = true
        searchRow.addArrangedSubview(search)
        let pingAll = button(pingAllBusy ? "Measuring…" : "↻  Ping all",
                             action: #selector(pingAllServers(_:)),
                             mutedButton: true)
        pingAll.isEnabled = !pingAllBusy && !(snapshot?.servers.isEmpty ?? true)
        pingAll.toolTip = "Measure real ICMP latency to authorized public probe addresses"
        pingAll.heightAnchor.constraint(equalToConstant: 40).isActive = true
        searchRow.addArrangedSubview(pingAll)
        wrapper.addArrangedSubview(searchRow)
        searchRow.widthAnchor.constraint(equalTo: wrapper.widthAnchor).isActive = true

        let protocolsTitle = text("PROTOCOLS", size: 11, weight: .bold, color: muted)
        wrapper.addArrangedSubview(protocolsTitle)
        let chips = protocolChips()
        wrapper.addArrangedSubview(chips)
        chips.widthAnchor.constraint(equalTo: wrapper.widthAnchor).isActive = true

        // A fastest-node action must use real local ICMP measurements,
        // never panel estimates or synthetic timers.
        let fastest = (snapshot?.servers ?? []).filter { server in
            server.online && nodePingResults[server.id]?.measuredMs != nil
        }.min {
            (nodePingResults[$0.id]?.measuredMs ?? Int.max) <
                (nodePingResults[$1.id]?.measuredMs ?? Int.max)
        }
        let fastestButton = button(
            fastest.map {
                "✦  Fastest measured: " + countryName($0.country) +
                "  ·  " + pingText($0)
            } ?? "✦  Fastest server  ·  Measure ping first",
            action: #selector(selectFastestMeasuredServer(_:)),
            mutedButton: true)
        fastestButton.isEnabled = fastest != nil
        fastestButton.heightAnchor.constraint(equalToConstant: 39).isActive = true
        fastestButton.toolTip = "Choose the lowest real ICMP RTT among online nodes"
        wrapper.addArrangedSubview(fastestButton)

        let visible = (snapshot?.servers ?? []).filter { server in
            if locationSearch.isEmpty { return true }
            let needle = locationSearch.localizedLowercase
            return server.name.localizedLowercase.contains(needle) ||
                countryName(server.country).localizedLowercase.contains(needle) ||
                server.country.localizedLowercase.contains(needle)
        }
        let grouped = Dictionary(grouping: visible) { $0.country.uppercased() }
        let codes = grouped.keys.sorted {
            countryName($0).localizedStandardCompare(countryName($1)) == .orderedAscending
        }
        locationCountryIDs = codes
        locationRowIDs = visible.map { $0.id }

        let count = visible.count
        wrapper.addArrangedSubview(text(
            String(codes.count) + " COUNTRIES  ·  " + String(count) + " SERVERS",
            size: 11, weight: .semibold, color: sea))
        if codes.isEmpty {
            let message: String
            if let issue = snapshot?.errors["servers"] {
                message = "Server list unavailable: " + issue
            } else if snapshot?.sectionsLoaded.contains("servers") == true {
                message = locationSearch.isEmpty ?
                    "No servers assigned to this account." : "No matching locations."
            } else {
                message = "Loading assigned locations…"
            }
            let placeholder = card([text(message, color: muted)],
                                   radius: 17, padding: 19)
            wrapper.addArrangedSubview(placeholder)
            placeholder.widthAnchor.constraint(equalTo: wrapper.widthAnchor).isActive = true
        }

        for (countryIndex, code) in codes.enumerated() {
            let items = (grouped[code] ?? []).sorted {
                $0.name.localizedStandardCompare($1.name) == .orderedAscending
            }
            let expanded = expandedCountries.contains(code)
            let selectedHere = items.contains { $0.id == activeServer }
            let group = stack(spacing: 12)
            group.alignment = .leading

            let countryHeader = stack(.horizontal, spacing: 10)
            countryHeader.alignment = .centerY
            let countryFlag = text(flag(code), size: 22, weight: .medium)
            countryHeader.addArrangedSubview(countryFlag)
            let countryInfo = stack(spacing: 4)
            countryInfo.alignment = .leading
            countryInfo.addArrangedSubview(text(countryName(code), size: 14,
                                                weight: .semibold))
            countryInfo.addArrangedSubview(text(
                String(items.count) + (items.count == 1 ? " server" : " servers") +
                (selectedHere ? "    ·    Selected" : ""),
                size: 10, color: selectedHere ? sea : muted))
            countryHeader.addArrangedSubview(countryInfo)
            let headerSpacer = NSView()
            headerSpacer.setContentHuggingPriority(.defaultLow,
                                                   for: .horizontal)
            countryHeader.addArrangedSubview(headerSpacer)
            let expand = button(expanded ? "⌃" : "⌄",
                                action: #selector(toggleLocationCountry(_:)),
                                tag: countryIndex, mutedButton: true)
            expand.widthAnchor.constraint(equalToConstant: 40).isActive = true
            expand.heightAnchor.constraint(equalToConstant: 34).isActive = true
            expand.toolTip = (expanded ? "Collapse " : "Expand ") + countryName(code)
            countryHeader.addArrangedSubview(expand)
            let headerCard = card([countryHeader], radius: 15, padding: 12)
            headerCard.layer?.borderColor = (selectedHere ? sea : tint())
                .withAlphaComponent(selectedHere ? 0.67 : 0.22).cgColor
            group.addArrangedSubview(headerCard)
            headerCard.widthAnchor.constraint(equalTo: group.widthAnchor)
                .isActive = true
            if expanded {
                for (position, server) in items.enumerated() {
                    let serverIndex = locationRowIDs.firstIndex(of: server.id) ?? -1
                    let selected = activeServer == server.id
                    let stateColor = server.online ? sea : muted

                    let info = stack(spacing: 4)
                    info.alignment = .leading
                    let rowTitle = stack(.horizontal, spacing: 7)
                    rowTitle.addArrangedSubview(
                        text(flag(code), size: 18, weight: .medium))
                    let name = text(friendlyServerName(server, index: position),
                                    size: 13, weight: .semibold)
                    name.lineBreakMode = .byTruncatingTail
                    name.maximumNumberOfLines = 1
                    name.toolTip = server.name
                    rowTitle.addArrangedSubview(name)
                    info.addArrangedSubview(rowTitle)
                    info.addArrangedSubview(text(
                        (server.online ? "● Online node" : "○ Offline node") +
                        (selected ? "    ·    Selected" : ""),
                        size: 10, weight: .medium, color: stateColor))

                    let stats = stack(spacing: 4)
                    stats.alignment = .trailing
                    let ping = text(pingText(server), size: 12,
                                    weight: .bold, color: pingColor(server))
                    ping.alignment = .right
                    ping.toolTip = pingDetails(server)
                    stats.addArrangedSubview(ping)

                    let probe = button(nodePingBusy.contains(server.id) ? "…" : "ϟ",
                                       action: #selector(pingOneServer(_:)),
                                       tag: serverIndex, mutedButton: true)
                    probe.widthAnchor.constraint(equalToConstant: 31).isActive = true
                    probe.heightAnchor.constraint(equalToConstant: 31).isActive = true
                    probe.toolTip = server.probeIP == nil ?
                        "No public probe address supplied by the panel" :
                        "Measure this server's ICMP latency"
                    probe.isEnabled = !pingAllBusy &&
                        !nodePingBusy.contains(server.id) && server.probeIP != nil

                    let select = button(selected ? "✓" : "›",
                        action: #selector(selectLocationServer(_:)),
                        tag: serverIndex, primary: selected,
                        mutedButton: !selected)
                    select.widthAnchor.constraint(equalToConstant: 39).isActive = true
                    select.heightAnchor.constraint(equalToConstant: 34).isActive = true
                    select.toolTip = selected ? "Selected server" :
                        "Select " + server.name

                    let row = stack(.horizontal, spacing: 11)
                    row.alignment = .centerY
                    row.addArrangedSubview(info)
                    info.setContentHuggingPriority(.defaultLow, for: .horizontal)
                    let filler = NSView()
                    filler.setContentHuggingPriority(.defaultLow, for: .horizontal)
                    row.addArrangedSubview(filler)
                    row.addArrangedSubview(stats)
                    row.addArrangedSubview(probe)
                    row.addArrangedSubview(select)

                    let tile = card([row], radius: 15, padding: 13)
                    tile.wantsLayer = true
                    tile.layer?.backgroundColor = (selected ?
                        tint().withAlphaComponent(0.25) :
                        NSColor(calibratedRed: 0.10, green: 0.18,
                                blue: 0.22, alpha: 0.89)).cgColor
                    tile.layer?.borderColor = (selected ? sea : tint())
                        .withAlphaComponent(selected ? 0.77 : 0.23).cgColor
                    tile.layer?.borderWidth = selected ? 1.5 : 1
                    group.addArrangedSubview(tile)
                    tile.widthAnchor.constraint(equalTo: group.widthAnchor).isActive = true
                }
            }

            let section = card([group], radius: 19, padding: 12)
            wrapper.addArrangedSubview(section)
            section.widthAnchor.constraint(equalTo: wrapper.widthAnchor).isActive = true
        }
        return card([wrapper], radius: 23, padding: 20)
    }

    private func createTable() -> NSView {
        let table = NSTableView(frame: .zero)
        table.rowHeight = 39
        table.usesAlternatingRowBackgroundColors = true
        table.backgroundColor = panelColor
        for (id, label, width) in [
            ("name", "Server", CGFloat(235)),
            ("country", "Country", CGFloat(135)),
            ("network", "Status / latency", CGFloat(200))
        ] {
            let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier(id))
            column.title = label
            column.minWidth = 85
            column.width = width
            table.addTableColumn(column)
        }
        table.delegate = self
        table.dataSource = self
        table.target = self
        table.action = #selector(selectRow(_:))
        let scroller = NSScrollView()
        scroller.documentView = table
        scroller.hasVerticalScroller = true
        scroller.translatesAutoresizingMaskIntoConstraints = false
        scroller.heightAnchor.constraint(equalToConstant: 330).isActive = true
        scroller.widthAnchor.constraint(greaterThanOrEqualToConstant: 390)
            .isActive = true
        return scroller
    }

    private func settingRow(_ title: String, subtitle: String,
                            state: String, tone: NSColor? = nil) -> NSView {
        let row = stack(.horizontal, spacing: 12)
        let info = stack(spacing: 5)
        info.addArrangedSubview(text(title, size: 13, weight: .semibold))
        info.addArrangedSubview(text(subtitle, size: 11, color: muted))
        row.addArrangedSubview(info)
        let spacer = NSView()
        spacer.setContentHuggingPriority(.defaultLow, for: .horizontal)
        row.addArrangedSubview(spacer)
        row.addArrangedSubview(pill(state, color: tone ?? muted))
        return card([row], radius: 16, padding: 15)
    }

    private func settingsPage() -> NSView {
        let section = stack(spacing: 12)
        section.alignment = .leading
        section.addArrangedSubview(text("Connection & privacy",
                                        size: 18, weight: .semibold))
        // Render disabled state rather than non-functional toggles. These
        // settings are controlled by the actual tunnel runtime when signed.
        let killSwitch = settingRow(
            "◈  Kill Switch",
            subtitle: "Block unprotected traffic when the VPN disconnects",
            state: "Unavailable", tone: amber)
        section.addArrangedSubview(killSwitch)
        killSwitch.widthAnchor.constraint(equalTo: section.widthAnchor).isActive = true
        let splitTunneling = settingRow(
            "≡  Split Tunneling",
            subtitle: "Choose which apps use the secure connection",
            state: "Unavailable", tone: amber)
        section.addArrangedSubview(splitTunneling)
        splitTunneling.widthAnchor.constraint(equalTo: section.widthAnchor).isActive = true
        let dns = settingRow(
            "◉  DNS protection",
            subtitle: "Secure resolver and DNS leak protection",
            state: "Unavailable", tone: amber)
        section.addArrangedSubview(dns)
        dns.widthAnchor.constraint(equalTo: section.widthAnchor).isActive = true
        let reconnect = settingRow(
            "↻  Auto reconnect",
            subtitle: "Restore a connection if its network path changes",
            state: "Unavailable", tone: amber)
        section.addArrangedSubview(reconnect)
        reconnect.widthAnchor.constraint(equalTo: section.widthAnchor).isActive = true

        section.addArrangedSubview(text("Application", size: 18,
                                        weight: .semibold))
        let language = settingRow("◎  App language", subtitle: "English",
                                  state: "EN")
        section.addArrangedSubview(language)
        language.widthAnchor.constraint(equalTo: section.widthAnchor).isActive = true
        let appearance = settingRow("◉  Appearance",
                                    subtitle: "TwinConnect dark glass",
                                    state: "Dark")
        section.addArrangedSubview(appearance)
        appearance.widthAnchor.constraint(equalTo: section.widthAnchor).isActive = true

        // Independent diagnostics; cannot be confused with the Connect
        // action. Keep verified emergency stop available at all times.
        section.addArrangedSubview(text("Local proxy diagnostics",
                                        size: 18, weight: .semibold))
        section.addArrangedSubview(text(
            "Only a single HTTPS request uses Hysteria2. This is not a system VPN.",
            size: 11, color: amber))
        let proxyActions = stack(.horizontal, spacing: 10)
        proxyActions.distribution = .fillEqually
        let testProxy = button("Test Hysteria2 SOCKS",
                               action: #selector(primaryProxyAction(_:)),
                               mutedButton: true)
        testProxy.heightAnchor.constraint(equalToConstant: 44).isActive = true
        testProxy.isEnabled = !localProxyBusy
        proxyActions.addArrangedSubview(testProxy)
        let stopProxy = button("■  Stop local proxy",
                               action: #selector(stopLocalProxyNow(_:)),
                               mutedButton: true)
        stopProxy.heightAnchor.constraint(equalToConstant: 44).isActive = true
        proxyActions.addArrangedSubview(stopProxy)
        section.addArrangedSubview(proxyActions)
        proxyActions.widthAnchor.constraint(equalTo: section.widthAnchor).isActive = true
        if !localProxyStatus.isEmpty {
            section.addArrangedSubview(text(localProxyStatus, size: 11, color: muted))
        }

        let actions = stack(.horizontal, spacing: 10)
        actions.distribution = .fillEqually
        actions.addArrangedSubview(button("↻  Refresh servers & account",
            action: #selector(refresh(_:)), primary: true))
        actions.addArrangedSubview(button("Copy diagnostics",
            action: #selector(copyDiagnostics(_:)), mutedButton: true))
        section.addArrangedSubview(actions)
        actions.widthAnchor.constraint(equalTo: section.widthAnchor).isActive = true

        let detail = snapshot?.errors.keys.sorted().map { name in
            name + ": " + (snapshot?.errors[name] ?? "unavailable")
        }.joined(separator: " · ") ?? ""
        let count = snapshot?.sectionsLoaded.count ?? 0
        section.addArrangedSubview(text(
            "Panel information: " + String(count) + "/4 sections loaded" +
                (detail.isEmpty ? "" : " · " + detail),
            size: 11, color: detail.isEmpty ? muted : amber))
        section.addArrangedSubview(text(
            "VPN controls require a verified Packet Tunnel. This preview " +
            "does not claim a working VPN connection.",
            size: 11, color: muted))
        return section
    }

    private func expiryText(_ account: TwinMacNativeAccount?) -> String {
        guard let account = account else { return "—" }
        if let expiry = account.expiresAt {
            return DateFormatter.localizedString(from: expiry, dateStyle: .medium,
                                                 timeStyle: .none)
        }
        return (account.activationDurationDays ?? 0) > 0 ?
            "After first connection" : "Unlimited"
    }

    private func reservedRenewalCard(_ renewal: TwinMacReservedRenewal,
                                     compact: Bool) -> NSView {
        let fields = stack(spacing: 7)
        fields.alignment = .leading
        fields.addArrangedSubview(text(
            renewal.needsReview ? "◷  Renewal needs review" :
                                  "▣  Reserved renewal",
            size: compact ? 12 : 15, weight: .bold,
            color: renewal.needsReview ? amber : sea))
        fields.addArrangedSubview(text(renewal.planName,
                                      size: compact ? 11 : 13, weight: .semibold))
        let capacity = ByteCountFormatter.string(fromByteCount:
            renewal.trafficBytes, countStyle: .file)
        fields.addArrangedSubview(text(
            capacity + "  •  " + String(renewal.durationDays) + " days",
            size: compact ? 11 : 12))
        fields.addArrangedSubview(text(
            renewal.needsReview ?
                "Pending review. The next period has not been applied." :
                "Next period activates after current quota or expiry ends.",
            size: 10, color: muted))
        if !compact {
            let recorded = DateFormatter.localizedString(
                from: renewal.reservedAt, dateStyle: .medium, timeStyle: .none)
            fields.addArrangedSubview(text("Reserved on: " + recorded,
                                          size: 10, color: muted))
        }
        return card([fields], radius: 16, padding: compact ? 12 : 17)
    }

    private func accountPage() -> NSView {
        let content = stack(spacing: 14)
        content.alignment = .leading
        let account = snapshot?.account

        let hero = stack(.horizontal, spacing: 15)
        hero.alignment = .centerY
        let emblem = NSView()
        emblem.wantsLayer = true
        emblem.layer?.cornerRadius = 18
        emblem.layer?.backgroundColor = tint().withAlphaComponent(0.60).cgColor
        emblem.translatesAutoresizingMaskIntoConstraints = false
        emblem.widthAnchor.constraint(equalToConstant: 62).isActive = true
        emblem.heightAnchor.constraint(equalToConstant: 62).isActive = true
        let shield = text("◇", size: 34, weight: .bold)
        shield.translatesAutoresizingMaskIntoConstraints = false
        emblem.addSubview(shield)
        NSLayoutConstraint.activate([
            shield.centerXAnchor.constraint(equalTo: emblem.centerXAnchor),
            shield.centerYAnchor.constraint(equalTo: emblem.centerYAnchor)
        ])
        hero.addArrangedSubview(emblem)
        let identity = stack(spacing: 7)
        identity.alignment = .leading
        let username = text(accountSession?.username ?? "—", size: 16,
                            weight: .semibold)
        username.lineBreakMode = .byTruncatingMiddle
        username.maximumNumberOfLines = 1
        identity.addArrangedSubview(username)
        let accountState = account?.status.lowercased() == "active" ?
            "◆  Active subscription" : (account?.status ?? "Loading account…")
        identity.addArrangedSubview(text(accountState, size: 12, color: sea))
        hero.addArrangedSubview(identity)
        let heroCard = card([hero], radius: 23, padding: 19)
        content.addArrangedSubview(heroCard)
        heroCard.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true

        if let reserved = account?.reservedRenewal {
            content.addArrangedSubview(text("Reserved renewal list",
                                          size: 13, weight: .bold))
            let reservedCard = reservedRenewalCard(reserved, compact: false)
            content.addArrangedSubview(reservedCard)
            reservedCard.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        }

        let usage = stack(spacing: 14)
        usage.alignment = .leading
        let head = stack(.horizontal, spacing: 8)
        head.addArrangedSubview(text("◉  Data usage", size: 15, weight: .semibold))
        let gap = NSView()
        gap.setContentHuggingPriority(.defaultLow, for: .horizontal)
        head.addArrangedSubview(gap)
        if let account = account, account.limitBytes == 0 {
            head.addArrangedSubview(pill("Unlimited", color: sea))
        }
        usage.addArrangedSubview(head)
        head.widthAnchor.constraint(equalTo: usage.widthAnchor).isActive = true

        let used = account.map {
            ByteCountFormatter.string(fromByteCount: $0.usedBytes,
                                      countStyle: .file)
        } ?? "—"
        let limit = account.map {
            $0.limitBytes == 0 ? "Unlimited" :
                ByteCountFormatter.string(fromByteCount: $0.limitBytes,
                                          countStyle: .file)
        } ?? "—"
        let totals = stack(.horizontal, spacing: 9)
        totals.addArrangedSubview(text(used, size: 31, weight: .bold))
        totals.addArrangedSubview(text("/ " + limit, size: 17,
                                      weight: .semibold,
                                      color: account?.limitBytes == 0 ? sea : muted))
        usage.addArrangedSubview(totals)
        let remaining: String
        if let account = account {
            remaining = account.limitBytes == 0 ? "Unlimited" :
                ByteCountFormatter.string(fromByteCount: max(0,
                    account.limitBytes - account.usedBytes), countStyle: .file)
        } else {
            remaining = "—"
        }
        usage.addArrangedSubview(text("Remaining: " + remaining, color: muted))
        let meter = NSProgressIndicator()
        meter.style = .bar
        meter.isIndeterminate = false
        meter.minValue = 0
        meter.maxValue = 100
        if let account = account, account.limitBytes > 0 {
            meter.doubleValue = min(100,
                Double(account.usedBytes) / Double(account.limitBytes) * 100)
        }
        meter.translatesAutoresizingMaskIntoConstraints = false
        usage.addArrangedSubview(meter)
        meter.widthAnchor.constraint(equalTo: usage.widthAnchor).isActive = true
        usage.addArrangedSubview(text(
            account == nil ? "Fetching current usage from your panel" :
            account!.limitBytes == 0 ? "No traffic cap" :
                String(format: "%.1f%% used", meter.doubleValue),
            size: 11, color: muted))
        let usageCard = card([usage], radius: 23, padding: 20)
        content.addArrangedSubview(usageCard)
        usageCard.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true

        let metrics = stack(.horizontal, spacing: 12)
        metrics.distribution = .fillEqually
        metrics.addArrangedSubview(networkMetric("▣  Expires on",
            value: expiryText(account)))
        let devices = snapshot?.deviceLimit.map {
            $0 == 0 ? "Unlimited" : String($0)
        } ?? "—"
        metrics.addArrangedSubview(networkMetric("▣  Device limit", value: devices))
        content.addArrangedSubview(metrics)
        metrics.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true

        if let details = snapshot?.errors["account"] {
            content.addArrangedSubview(text("Account unavailable: " + details,
                                          size: 12, color: amber))
        }
        let refreshButton = button("↻  Refresh account",
                                    action: #selector(refresh(_:)))
        content.addArrangedSubview(refreshButton)
        refreshButton.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        let signOutButton = button("Sign out", action: #selector(signOut(_:)),
                                   mutedButton: true)
        signOutButton.heightAnchor.constraint(equalToConstant: 42).isActive = true
        content.addArrangedSubview(signOutButton)
        signOutButton.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        return content
    }

    private func compactMetric(_ title: String, value: String) -> NSView {
        let metric = stack(spacing: 5)
        metric.addArrangedSubview(text(title, size: 10, color: muted))
        metric.addArrangedSubview(text(value, size: 12, weight: .bold))
        return card([metric], radius: 13, padding: 10)
    }

    private func homeSubscriptionSummary() -> NSView {
        let items = stack(spacing: 8)
        items.alignment = .leading
        let header = stack(.horizontal, spacing: 9)
        header.addArrangedSubview(text("◈  Subscription details",
                                       size: 13, weight: .semibold))
        let space = NSView()
        space.setContentHuggingPriority(.defaultLow, for: .horizontal)
        header.addArrangedSubview(space)
        let limitLabel = snapshot?.account.map {
            $0.limitBytes == 0 ? "Unlimited" : "Limited"
        } ?? "—"
        header.addArrangedSubview(text(limitLabel, size: 10, color: sea))
        let reload = button("↻", action: #selector(refresh(_:)),
                            mutedButton: true)
        reload.widthAnchor.constraint(equalToConstant: 32).isActive = true
        reload.heightAnchor.constraint(equalToConstant: 32).isActive = true
        header.addArrangedSubview(reload)
        items.addArrangedSubview(header)
        header.widthAnchor.constraint(equalTo: items.widthAnchor).isActive = true

        let account = snapshot?.account
        let used = account.map {
            ByteCountFormatter.string(fromByteCount: $0.usedBytes, countStyle: .file)
        } ?? "—"
        let quota = account.map {
            $0.limitBytes == 0 ? "Unlimited" :
                ByteCountFormatter.string(fromByteCount: $0.limitBytes,
                                          countStyle: .file)
        } ?? "—"
        let usage = stack(spacing: 7)
        usage.alignment = .leading
        let usageHeading = stack(.horizontal, spacing: 8)
        usageHeading.addArrangedSubview(text("◌  Data usage", size: 11,
                                             color: muted))
        let usageFiller = NSView()
        usageFiller.setContentHuggingPriority(.defaultLow, for: .horizontal)
        usageHeading.addArrangedSubview(usageFiller)
        usageHeading.addArrangedSubview(text(used + " / " + quota,
                                            size: 12, weight: .semibold))
        usage.addArrangedSubview(usageHeading)
        usageHeading.widthAnchor.constraint(equalTo: usage.widthAnchor).isActive = true
        // Thin custom usage rail matches Windows. Values still come
        // exclusively from the panel; unlimited never implies a full bar.
        let track = NSView()
        track.translatesAutoresizingMaskIntoConstraints = false
        track.wantsLayer = true
        track.layer?.cornerRadius = 3
        track.layer?.backgroundColor = sea.withAlphaComponent(0.20).cgColor
        track.heightAnchor.constraint(equalToConstant: 5).isActive = true
        usage.addArrangedSubview(track)
        track.widthAnchor.constraint(equalTo: usage.widthAnchor).isActive = true
        if let account = account, account.limitBytes > 0 {
            let fraction = max(0, min(1,
                CGFloat(account.usedBytes) / CGFloat(account.limitBytes)))
            if fraction > 0 {
                let filled = NSView()
                filled.translatesAutoresizingMaskIntoConstraints = false
                filled.wantsLayer = true
                filled.layer?.cornerRadius = 3
                filled.layer?.backgroundColor = sea.withAlphaComponent(0.88).cgColor
                track.addSubview(filled)
                NSLayoutConstraint.activate([
                    filled.leadingAnchor.constraint(equalTo: track.leadingAnchor),
                    filled.topAnchor.constraint(equalTo: track.topAnchor),
                    filled.bottomAnchor.constraint(equalTo: track.bottomAnchor),
                    filled.widthAnchor.constraint(equalTo: track.widthAnchor,
                                                 multiplier: fraction)
                ])
            }
        }
        let remaining: String
        if let account = account {
            remaining = account.limitBytes == 0 ? "Unlimited" :
                ByteCountFormatter.string(fromByteCount: max(0,
                    account.limitBytes - account.usedBytes), countStyle: .file)
        } else {
            remaining = "—"
        }
        usage.addArrangedSubview(text("Remaining: " + remaining,
                                      size: 10, color: sea))
        let usageCard = card([usage], radius: 13, padding: 10, style: .inset)
        items.addArrangedSubview(usageCard)
        usageCard.widthAnchor.constraint(equalTo: items.widthAnchor).isActive = true

        let expiry = account?.expiresAt.map {
            DateFormatter.localizedString(from: $0, dateStyle: .medium,
                                          timeStyle: .none)
        } ?? "—"
        let days: String
        if let date = account?.expiresAt {
            let remaining = date.timeIntervalSinceNow
            days = remaining < 0 ? "Expired" :
                String(Int(ceil(remaining / 86400))) + " days"
        } else if account != nil {
            days = "Unlimited / not started"
        } else {
            days = "—"
        }
        let chips = stack(.horizontal, spacing: 8)
        chips.distribution = .fillEqually
        chips.addArrangedSubview(compactMetric("Expiry date", value: expiry))
        chips.addArrangedSubview(compactMetric("Time remaining", value: days))
        items.addArrangedSubview(chips)
        chips.widthAnchor.constraint(equalTo: items.widthAnchor).isActive = true
        if let reserved = account?.reservedRenewal {
            let reservedCard = reservedRenewalCard(reserved, compact: true)
            items.addArrangedSubview(reservedCard)
            reservedCard.widthAnchor.constraint(equalTo: items.widthAnchor).isActive = true
        }

        if let error = snapshot?.errors["account"] {
            items.addArrangedSubview(text("Account: " + error,
                                          size: 10, color: amber))
        }
        return card([items], radius: 20, padding: 14, style: .inset)
    }

    private func filteredServers() -> [TwinMacNativeServer] {
        guard let servers = snapshot?.servers else { return [] }
        return country == "All countries"
            ? servers : servers.filter { $0.country == country }
    }

    func numberOfRows(in tableView: NSTableView) -> Int {
        return filteredServers().count
    }

    private func flag(_ country: String) -> String {
        let chars = country.uppercased().unicodeScalars
        guard chars.count == 2, chars.allSatisfy({
            $0.value >= 65 && $0.value <= 90
        }) else { return "◎" }
        let scalars = chars.compactMap {
            UnicodeScalar(127397 + $0.value)
        }
        return String(String.UnicodeScalarView(scalars))
    }

    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?,
                   row: Int) -> NSView? {
        let entries = filteredServers()
        guard let key = tableColumn?.identifier.rawValue,
              entries.indices.contains(row) else { return nil }
        let item = entries[row]
        let value: String
        switch key {
        case "name": value = item.name
        case "country": value = flag(item.country) + "  " + item.country.uppercased()
        default:
            value = (item.online ? "● Online (panel)" : "○ Offline (panel)") +
                (item.latencyMs.map { " • \($0) ms" } ?? "")
        }
        let cell = NSTableCellView()
        let label = text(value, size: 12,
                         color: key == "name" ? .white : muted)
        label.translatesAutoresizingMaskIntoConstraints = false
        cell.addSubview(label)
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: cell.leadingAnchor, constant: 8),
            label.trailingAnchor.constraint(lessThanOrEqualTo:
                cell.trailingAnchor, constant: -8),
            label.centerYAnchor.constraint(equalTo: cell.centerYAnchor)
        ])
        return cell
    }

    @objc private func signIn(_ sender: NSButton) {
        guard !busy, let username = usernameField?.stringValue,
              let password = passwordField?.stringValue else { return }
        busy = true
        sender.isEnabled = false
        status = "Signing in securely…"
        passwordField?.stringValue = ""
        directory.login(username: username, password: password) { [weak self] result in
            guard let self = self else { return }
            self.busy = false
            switch result {
            case .failure(let error):
                self.status = "Sign-in failed: " + error.localizedDescription
            case .success(let session):
                self.accountSession = session
                self.restoreCurrentSelection(session)
                self.snapshot = nil
                self.pingGeneration += 1
                self.nodePingResults.removeAll()
                self.nodePingBusy.removeAll()
                self.nodePingQueue.removeAll()
                self.pingAllBusy = false
                self.didAutoPing = false
                self.tenantLogo = nil
                self.logoGeneration += 1
                let logoVersion = self.logoGeneration
                self.directory.loadBrandLogo(session) { [weak self] data in
                    guard let self = self,
                          self.logoGeneration == logoVersion,
                          self.accountSession?.accessToken == session.accessToken
                    else { return }
                    if let bytes = data, let image = NSImage(data: bytes) {
                        self.tenantLogo = image
                        self.view = self.build()
                    }
                }
                self.tab = 0
                self.status = "Retrieving live subscription data…"
                NSLog("TwinConnect AppKit: authenticated; showing dashboard shell")
                // Match Flutter desktop's two equal cards on large displays
                // without clipping them on smaller remote Mac desktops.
                if let window = self.view.window {
                    if let visible = (window.screen ?? NSScreen.main)?.visibleFrame,
                       visible.width >= 1120 {
                        window.setContentSize(NSSize(
                            width: min(1240, visible.width - 32),
                            height: min(800, visible.height - 32)
                        ))
                        window.center()
                    }
                    self.nativeContentWidth = window.contentView?.bounds.width
                        ?? window.frame.width
                }
                // Present the dashboard first. Panel fetch must never gate
                // rendering the tabs or make the content disappear.
                self.view = self.build()
                self.refreshData()
                return
            }
            self.view = self.build()
        }
    }

    private func refreshData() {
        guard let current = accountSession, !busy else { return }
        busy = true
        refreshGeneration += 1
        let generation = refreshGeneration
        status = "Retrieving panel data…"
        directory.loadSnapshot(current) { [weak self] data in
            guard let self = self else { return }
            guard self.refreshGeneration == generation,
                  self.accountSession?.accessToken == current.accessToken else {
                return
            }
            self.snapshot = data
            if data.sectionsLoaded.contains("servers") {
                let validIDs = Set(data.servers.map { $0.id })
                self.nodePingResults = self.nodePingResults.filter {
                    validIDs.contains($0.key)
                }
                // Avoid automatic ICMP subprocess bursts while signing in.
                // Users can explicitly request Ping all on the Locations tab.
            }
            if data.sectionsLoaded.contains("protocols"),
               let selected = self.activeProtocol,
               !data.protocols.contains(where: { $0.code == selected }) {
                self.activeProtocol = nil
                self.persistCurrentSelection()
            }
            if data.sectionsLoaded.contains("servers"),
               let selected = self.activeServer,
               !data.servers.contains(where: { $0.id == selected }) {
                self.activeServer = nil
                self.persistCurrentSelection()
            }
            self.busy = !data.isComplete
            let count = data.sectionsLoaded.count
            if data.isComplete {
                if data.errors.isEmpty {
                    self.status = "Panel synchronized: 4 of 4 sections."
                } else {
                    let details = data.errors.keys.sorted().map { name in
                        name + ": " + (data.errors[name] ?? "unavailable")
                    }.joined(separator: " · ")
                    self.status = "Panel: \(count)/4 sections loaded. " + details
                }
            } else {
                self.status = "Panel: \(count)/4 sections loaded…"
            }
            self.view = self.build()
            NSLog("TwinConnect AppKit: panel sections loaded %d/4; completed: %@",
                  count, data.isComplete ? "YES" : "NO")
        }
    }

    @objc private func refresh(_ sender: NSButton) {
        status = "Refreshing subscription data…"
        refreshData()
        view = build()
    }

    @objc private func signOut(_ sender: NSButton) {
        refreshGeneration += 1
        pingGeneration += 1
        nodePingResults.removeAll()
        nodePingBusy.removeAll()
        nodePingQueue.removeAll()
        pingAllBusy = false
        didAutoPing = false
        logoGeneration += 1
        tenantLogo = nil
        accountSession = nil
        localProxyStatus = ""
        snapshot = nil
        activeProtocol = nil
        activeServer = nil
        country = "All countries"
        expandedCountries.removeAll()
        locationCountryIDs.removeAll()
        locationRowIDs.removeAll()
        protocolChipCodes.removeAll()
        locationSearch = ""
        busy = false
        tab = 0
        status = ""
        view = build()
    }

    @objc private func showLocations(_ sender: NSButton) {
        tab = 1
        view = build()
    }

    @objc private func openLanguageSettings(_ sender: NSButton) {
        tab = 2
        view = build()
    }

    @objc private func changeTab(_ sender: NSButton) {
        tab = sender.tag
        view = build()
    }

    @objc private func searchLocations(_ sender: NSSearchField) {
        locationSearch = sender.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        view = build()
    }

    @objc private func toggleAllProtocolChips(_ sender: NSButton) {
        showAllProtocolChips.toggle()
        view = build()
    }

    @objc private func selectProtocolChip(_ sender: NSButton) {
        guard protocolChipCodes.indices.contains(sender.tag) else { return }
        activeProtocol = protocolChipCodes[sender.tag]
        persistCurrentSelection()
        view = build()
    }

    @objc private func toggleLocationCountry(_ sender: NSButton) {
        guard locationCountryIDs.indices.contains(sender.tag) else { return }
        let code = locationCountryIDs[sender.tag]
        if !expandedCountries.insert(code).inserted {
            expandedCountries.remove(code)
        }
        view = build()
    }

    @objc private func selectLocationServer(_ sender: NSButton) {
        guard locationRowIDs.indices.contains(sender.tag) else { return }
        activeServer = locationRowIDs[sender.tag]
        persistCurrentSelection()
        status = "Location selected. A signed VPN engine is required to connect."
        view = build()
    }

    @objc private func changeQuickServer(_ sender: NSPopUpButton) {
        activeServer = sender.selectedItem?.representedObject as? String
        persistCurrentSelection()
        status = "Location selected. VPN connection remains unavailable."
        view = build()
    }

    @objc private func changeQuickProtocol(_ sender: NSPopUpButton) {
        activeProtocol = sender.selectedItem?.representedObject as? String
        persistCurrentSelection()
        status = "Protocol selected. VPN connection remains unavailable."
        view = build()
    }

    @objc private func changeCountry(_ sender: NSPopUpButton) {
        country = sender.titleOfSelectedItem ?? "All countries"
        view = build()
    }

    @objc private func selectRow(_ sender: NSTableView) {
        let row = sender.selectedRow
        let list = filteredServers()
        if list.indices.contains(row) { activeServer = list[row].id }
    }


    @objc private func stopLocalProxyNow(_ sender: NSButton) {
        // Never block the AppKit main thread while waiting for the engine.
        // The manager validates the PID and confirms exit before clearing state.
        let root = NSHomeDirectory() + "/twinpanel/clients/twinconnect"
        sender.isEnabled = false
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }
            let result = self.runLocalManager(["stop"], root: root)
            DispatchQueue.main.async { [weak self] in
                guard let self = self else { return }
                self.localProxyStatus = result.0 == 0 ?
                    "Local proxy stopped. System VPN remains offline." :
                    "Local proxy stop failed: " + self.safeManagerReason(result.2)
                self.view = self.build()
            }
        }
    }

    @objc private func primaryProxyAction(_ sender: NSButton) {
        guard accountSession != nil, !localProxyBusy else { return }
        guard activeProtocol == "hysteria2" else {
            localProxyStatus = "Select Hysteria2 from Locations first. Other protocols are not yet available in AppKit proxy mode."
            tab = 1
            view = build()
            return
        }
        guard activeServer != nil else {
            localProxyStatus = "Choose a subscription server in Locations first."
            tab = 1
            view = build()
            return
        }
        guard snapshot?.protocols.contains(where: {
            $0.code == "hysteria2" && $0.configured
        }) == true else {
            localProxyStatus = "Hysteria2 is not enabled/configured for this subscription."
            view = build()
            return
        }
        testNativeHysteria2Proxy(sender)
    }

    @objc private func testNativeHysteria2Proxy(_ sender: NSButton) {
        guard !localProxyBusy,
              let session = accountSession,
              let serverID = activeServer,
              activeProtocol == "hysteria2",
              snapshot?.protocols.contains(where: {
                  $0.code == "hysteria2" && $0.configured
              }) == true else { return }
        localProxyBusy = true
        localProxyStatus = "Checking current panel permissions…"
        view = build()
        directory.prepareLocalHysteria2(session, serverID: serverID) {
            [weak self] response in
            guard let self = self else { return }
            guard self.accountSession?.accessToken == session.accessToken else {
                self.localProxyBusy = false
                return
            }
            switch response {
            case .failure(let error):
                self.localProxyBusy = false
                self.localProxyStatus = "Proxy test blocked: " + error.localizedDescription
                self.view = self.build()
            case .success(let bytes):
                self.localProxyStatus = "Sending a test request via Hysteria2…"
                self.view = self.build()
                DispatchQueue.global(qos: .userInitiated).async {
                    let result = self.oneShotHysteria2Probe(bytes)
                    DispatchQueue.main.async { [weak self] in
                        guard let self = self else { return }
                        self.localProxyBusy = false
                        guard self.accountSession?.accessToken == session.accessToken
                        else { return }
                        self.localProxyStatus = result
                        self.view = self.build()
                    }
                }
            }
        }
    }

    /// Never changes a system route. Reuses the standalone manager's verified
    /// local SOCKS process and cleans up test credentials even on failure.
    private func oneShotHysteria2Probe(_ config: Data) -> String {
        let root = NSHomeDirectory() +
            "/twinpanel/clients/twinconnect"
        let manager = root + "/macos_native/standalone_connection_manager.py"
        #if arch(arm64)
        let archName = "arm64"
        #else
        let archName = "amd64"
        #endif
        let executable = root + "/macos_native/build/singbox/" +
            archName + "/sing-box"
        guard FileManager.default.isExecutableFile(atPath: executable),
              FileManager.default.fileExists(atPath: manager) else {
            return "Proxy engine not installed on this Mac"
        }
        let folder = FileManager.default.temporaryDirectory
            .appendingPathComponent("twinconnect-local-" + UUID().uuidString,
                                    isDirectory: true)
        do {
            try FileManager.default.createDirectory(
                at: folder, withIntermediateDirectories: false,
                attributes: [.posixPermissions: 0o700])
        } catch {
            return "Could not prepare private proxy test directory"
        }
        let file = folder.appendingPathComponent("client.json")
        defer { try? FileManager.default.removeItem(at: folder) }
        let created = FileManager.default.createFile(
            atPath: file.path, contents: config,
            attributes: [.posixPermissions: 0o600])
        guard created else { return "Could not write private proxy test profile" }
        // Only a single managed engine is permitted; don't interrupt existing
        // user-owned processes. Manager start refuses an existing instance.
        let started = runLocalManager([
            "start", "hysteria2", file.path, "--owner-pid",
            String(ProcessInfo.processInfo.processIdentifier)
        ], root: root)
        guard started.0 == 0 else {
            let diagnosis = runLocalManager(["diagnose"], root: root)
            let cause = safeManagerReason(diagnosis.1)
            return "Proxy startup failed: " + (
                cause == "UNKNOWN_PROXY_FAILURE" ? safeManagerReason(started.2) : cause
            )
        }
        let response = runLocalManager(["probe"], root: root)
        // Never report successful proxy egress as completed until the
        // temporary engine is actually stopped and verified by the manager.
        let stopped = runLocalManager(["stop"], root: root)
        guard stopped.0 == 0 else {
            return "Proxy stop failed: " + safeManagerReason(stopped.2) +
                " — use Stop local proxy before retrying"
        }
        guard response.0 == 0,
              let data = response.1.data(using: .utf8),
              let json = (try? JSONSerialization.jsonObject(with: data))
                  as? [String: Any],
              json["state"] as? String == "proxy_egress_reachable",
              let address = json["egress_ip"] as? String
        else {
            let curlReason = safeManagerReason(response.2)
            let engineReason = safeManagerReason(
                runLocalManager(["diagnose"], root: root).1
            )
            // SOCKS error 97 often means the outgoing Hysteria2 stream was
            // rejected, NOT that the local SOCKS handshake is malformed.
            // Expose both independent, redacted findings.
            let detail = engineReason == "ENGINE_FAILURE_NOT_CLASSIFIED" ||
                         engineReason == "UNKNOWN_PROXY_FAILURE" ||
                         engineReason == "ENGINE_LOG_UNAVAILABLE" ?
                curlReason : curlReason + " · " + engineReason
            return "Hysteria2 test failed: " + detail + " (VPN offline)"
        }
        return "Proxied HTTPS exit: " + address + " (not a system VPN)"
    }

    private func safeManagerReason(_ output: String) -> String {
        guard let data = output.data(using: .utf8),
              let json = (try? JSONSerialization.jsonObject(with: data))
                  as? [String: Any],
              let reason = json["reason"] as? String,
              reason.range(of: "^[A-Z][A-Z0-9_]{2,79}$",
                           options: .regularExpression) != nil else {
            return "UNKNOWN_PROXY_FAILURE"
        }
        return reason
    }

    private func runLocalManager(_ args: [String], root: String)
        -> (Int32, String, String) {
        let program = Process()
        program.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        program.arguments = [
            root + "/macos_native/standalone_connection_manager.py"
        ] + args
        let output = Pipe()
        let errors = Pipe()
        program.standardOutput = output
        program.standardError = errors
        do {
            try program.run()
            program.waitUntilExit()
            let stdout = output.fileHandleForReading.readDataToEndOfFile()
            let stderr = errors.fileHandleForReading.readDataToEndOfFile()
            return (program.terminationStatus,
                    String(data: stdout, encoding: .utf8) ?? "",
                    String(data: stderr, encoding: .utf8) ?? "")
        } catch {
            return (-1, "", "")
        }
    }

    /// First-stage CLI TUN integration: validate only. Running a privileged
    /// tunnel and routing system traffic requires a separately protected helper.
    /// Never report Connected after a config check.
    @objc private func unavailableConnect(_ sender: NSButton) {
        guard !cliTunCheckBusy, let session = accountSession else { return }
        guard activeProtocol == "hysteria2",
              let serverID = activeServer,
              snapshot?.protocols.contains(where: {
                  $0.code == "hysteria2" && $0.configured
              }) == true else {
            status = "TUN preflight: select an entitled Hysteria2 server in Locations."
            view = build()
            return
        }
        cliTunCheckBusy = true
        status = "TUN preflight: retrieving authorized profile…"
        view = build()
        directory.prepareUnroutedHysteria2TUN(session, serverID: serverID) {
            [weak self] result in
            DispatchQueue.main.async {
                guard let self = self else { return }
                guard self.accountSession?.accessToken == session.accessToken else {
                    self.cliTunCheckBusy = false
                    return
                }
                switch result {
                case .failure(let error):
                    self.cliTunCheckBusy = false
                    // Only expose stable diagnostic identifiers, never API
                    // response bodies or profile credentials in the UI.
                    let rawCode = error.localizedDescription
                    let safeCode = rawCode.range(
                        of: "^[A-Z0-9_]{3,64}$", options: .regularExpression
                    ) != nil ? rawCode : "UNEXPECTED_PROFILE_ERROR"
                    let hint: String
                    switch safeCode {
                    case "PROFILES_NOT_READY":
                        hint = "The panel has not generated this Hysteria2 profile."
                    case "PROTOCOL_NOT_SELECTED", "PROTOCOL_NOT_ALLOWED":
                        hint = "Hysteria2 is not entitled for this account."
                    case "SERVER_NOT_ALLOWED":
                        hint = "This server is not in the current account inventory."
                    case "HYSTERIA2_PROFILE_INVALID":
                        hint = "The selected server profile cannot be converted to sing-box."
                    case "NETWORK_UNAVAILABLE":
                        hint = "The panel could not be reached."
                    default:
                        hint = "Check the account, server, and panel connection."
                    }
                    self.status = "TUN preflight blocked (" + safeCode + "): " + hint
                    self.view = self.build()
                case .success(let profile):
                    DispatchQueue.global(qos: .userInitiated).async {
                        let checked = self.checkUnroutedTUNProfile(profile)
                        DispatchQueue.main.async { [weak self] in
                            guard let self = self else { return }
                            self.cliTunCheckBusy = false
                            guard self.accountSession?.accessToken == session.accessToken else { return }
                            self.status = checked ?
                                "TUN configuration valid. VPN offline; privileged engine not started." :
                                "TUN validation failed. VPN remains offline."
                            self.view = self.build()
                        }
                    }
                }
            }
        }
    }

    /// Config never reaches a shell. Private temporary data is removed on all
    /// exits; no system route, DNS, or proxy is modified.
    private func checkUnroutedTUNProfile(_ profile: Data) -> Bool {
        let root = NSHomeDirectory() + "/twinpanel/clients/twinconnect"
        #if arch(arm64)
        let architecture = "arm64"
        #else
        let architecture = "amd64"
        #endif
        let binary = root + "/macos_native/build/singbox/" +
            architecture + "/sing-box"
        guard FileManager.default.isExecutableFile(atPath: binary) else { return false }
        let folder = FileManager.default.temporaryDirectory
            .appendingPathComponent("twinconnect-tun-preflight-" + UUID().uuidString,
                                    isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: folder,
                withIntermediateDirectories: false,
                attributes: [.posixPermissions: 0o700])
        } catch { return false }
        defer { try? FileManager.default.removeItem(at: folder) }
        let configURL = folder.appendingPathComponent("config.json")
        guard FileManager.default.createFile(atPath: configURL.path,
            contents: profile, attributes: [.posixPermissions: 0o600]) else { return false }
        let task = Process()
        task.executableURL = URL(fileURLWithPath: binary)
        task.arguments = ["check", "-c", configURL.path]
        task.standardOutput = Pipe()
        task.standardError = Pipe()
        do {
            try task.run()
            // Validation is bounded; timed out processes are terminated.
            let finished = DispatchSemaphore(value: 0)
            task.terminationHandler = { _ in finished.signal() }
            if !task.isRunning {
                // Avoid racing terminationHandler installation for very fast checks.
                return task.terminationStatus == 0
            }
            if finished.wait(timeout: .now() + 15) == .timedOut {
                if task.isRunning { task.terminate() }
                task.waitUntilExit()
                return false
            }
            return task.terminationStatus == 0
        } catch { return false }
    }

    @objc private func openSupport(_ sender: NSButton) {
        if let url = accountSession?.supportURL { NSWorkspace.shared.open(url) }
    }

    @objc private func openRenewal(_ sender: NSButton) {
        if let url = accountSession?.renewalURL { NSWorkspace.shared.open(url) }
    }

    @objc private func openWebsite(_ sender: NSButton) {
        if let url = accountSession?.websiteURL { NSWorkspace.shared.open(url) }
    }

    @objc private func copyDiagnostics(_ sender: NSButton) {
        let hysteriaAvailable = snapshot?.protocols.contains(where: {
            $0.code == "hysteria2" && $0.configured
        }) == true
        let report = [
            "TwinConnect macOS diagnostics (no credentials included)",
            "System VPN: offline — unsigned Network Extension",
            "App account: " + (accountSession == nil ? "signed out" : "signed in"),
            "Panel: " + String(snapshot?.sectionsLoaded.count ?? 0) + "/4 sections loaded",
            "Hysteria2 entitled/configured: " + (hysteriaAvailable ? "yes" : "no"),
            "Protocol selected: " + (activeProtocol ?? "none"),
            "Server selected: " + (activeServer == nil ? "no" : "yes"),
            "TUN preflight: " + (status.contains("TUN") ? status : "not run"),
            "Local SOCKS test: " + (localProxyStatus.isEmpty ? "not run" : localProxyStatus)
        ].joined(separator: "\n")
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(report, forType: .string)
        sender.title = "Copied"
    }
}
