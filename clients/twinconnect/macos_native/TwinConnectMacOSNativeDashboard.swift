// Native AppKit rendering of the shared TwinConnect appearance, without Metal.
// The visual design mirrors the Flutter desktop/mobile experience while
// strictly keeping VPN unavailable until a signed and verified PacketTunnel.
import Cocoa

private final class TwinNativeFlippedDocument: NSView {
    override var isFlipped: Bool { true }
}

private final class TwinNativeBackdrop: NSView {
    var base = NSColor(calibratedRed: 0.059, green: 0.091, blue: 0.125, alpha: 1)
    var glow = NSColor(calibratedRed: 0.32, green: 0.55, blue: 0.64, alpha: 1)

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        NSGradient(colors: [
            base,
            base.blended(withFraction: 0.23, of: glow) ?? base,
            base.blended(withFraction: 0.10, of: glow) ?? base
        ])?.draw(in: bounds, angle: -25)
        let area = bounds
        for index in 0..<9 {
            let y = area.height * (0.17 + CGFloat(index) * 0.083)
            let curve = NSBezierPath()
            curve.move(to: CGPoint(x: -40, y: y))
            curve.curve(to: CGPoint(x: area.width + 40, y: y + 100),
                        controlPoint1: CGPoint(x: area.width * 0.26, y: y + 110),
                        controlPoint2: CGPoint(x: area.width * 0.72, y: y - 130))
            let light = glow.withAlphaComponent(0.035 + CGFloat(index % 3) * 0.009)
            light.setStroke()
            curve.lineWidth = 1
            curve.stroke()
        }
    }
}

// Replicates the *disconnected* state of the shared Flutter
// TwinConnectWaveIndicator. No fake activity or synthetic RX/TX animation.
private final class TwinNativeNetworkFabric: NSView {
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
        let line = NSBezierPath()
        line.move(to: CGPoint(x: rect.minX + rect.width * 0.065, y: rect.midY))
        line.line(to: CGPoint(x: rect.minX + rect.width * 0.935, y: rect.midY))
        line.lineWidth = 1
        NSColor(calibratedRed: 0.52, green: 0.78, blue: 0.92,
                alpha: 0.13).setStroke()
        line.stroke()
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
    private var activeProtocol: String?
    private var activeServer: String?
    private var nodePingResults = [String: TwinMacNativePingResult]()
    private var nodePingBusy = Set<String>()
    private var nodePingQueue = [TwinMacNativeServer]()
    private var pingAllBusy = false
    private var pingGeneration = 0
    private var didAutoPing = false
    private weak var usernameField: NSTextField?
    private weak var passwordField: NSSecureTextField?

    private let base = NSColor(calibratedRed: 0.059, green: 0.091, blue: 0.125, alpha: 1)
    private let panelColor = NSColor(calibratedRed: 0.11, green: 0.17, blue: 0.21, alpha: 0.83)
    private let muted = NSColor(calibratedRed: 0.69, green: 0.79, blue: 0.82, alpha: 1)
    private let teal = NSColor(calibratedRed: 0.33, green: 0.57, blue: 0.65, alpha: 1)
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

    private func tint() -> NSColor {
        guard let hex = accountSession?.accentHex,
              hex.range(of: "^#[0-9a-fA-F]{6}$",
                        options: .regularExpression) != nil,
              let value = UInt32(hex.dropFirst(), radix: 16) else { return teal }
        let proposed = NSColor(calibratedRed: CGFloat((value >> 16) & 255) / 255,
                               green: CGFloat((value >> 8) & 255) / 255,
                               blue: CGFloat(value & 255) / 255,
                               alpha: 1)
        // Match Flutter's BrandTheme.legacyViolet() migration to teal.
        let hue = proposed.hueComponent * 360
        return (hue >= 225 && hue <= 330 && proposed.saturationComponent > 0.27)
            ? teal : proposed
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
                      padding: CGFloat = 21) -> NSView {
        let box = NSView()
        box.translatesAutoresizingMaskIntoConstraints = false
        box.wantsLayer = true
        box.layer?.cornerRadius = radius
        box.layer?.backgroundColor = panelColor.cgColor
        box.layer?.borderWidth = 1
        box.layer?.borderColor = tint().withAlphaComponent(0.22).cgColor
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
        let background = NSView()
        background.wantsLayer = true
        background.layer?.cornerRadius = 13
        background.layer?.backgroundColor = (color ?? tint())
            .withAlphaComponent(0.16).cgColor
        background.layer?.borderColor = (color ?? tint())
            .withAlphaComponent(0.32).cgColor
        background.layer?.borderWidth = 1
        let label = text(value, size: 12, weight: .semibold,
                         color: color ?? sea)
        spaced(background, label, inset: 9)
        return background
    }

    private func button(_ title: String, action: Selector, tag: Int = 0,
                        primary: Bool = false, mutedButton: Bool = false)
                        -> NSButton {
        let control = NSButton(title: title, target: self, action: action)
        control.isBordered = false
        control.bezelStyle = .rounded
        control.tag = tag
        control.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
        control.wantsLayer = true
        control.layer?.cornerRadius = 13
        control.layer?.borderWidth = 1
        let color = primary ? tint() : NSColor(calibratedWhite: 0.86, alpha: 1)
        let background = primary
            ? tint().withAlphaComponent(0.87)
            : tint().withAlphaComponent(mutedButton ? 0.08 : 0.15)
        control.layer?.backgroundColor = background.cgColor
        control.layer?.borderColor = tint().withAlphaComponent(0.33).cgColor
        control.attributedTitle = NSAttributedString(
            string: title,
            attributes: [.foregroundColor: primary ? NSColor.white : color,
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
            NSRect(x: 0, y: 0, width: 1100, height: 730))
        root.base = base
        root.glow = tint()
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
        let workspace = stack(spacing: 17)
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
        heading.addArrangedSubview(pill("● Offline", color: muted))
        workspace.addArrangedSubview(heading)
        heading.widthAnchor.constraint(equalTo: workspace.widthAnchor).isActive = true
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
        scroll.autohidesScrollers = true
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
                                           constant: 24),
            workspace.bottomAnchor.constraint(equalTo: document.bottomAnchor,
                                              constant: -24)
        ])
        scroll.documentView = document
        root.addSubview(scroll)
        NSLayoutConstraint.activate([
            scroll.leadingAnchor.constraint(equalTo: sidebar.trailingAnchor),
            scroll.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            scroll.topAnchor.constraint(equalTo: root.topAnchor),
            scroll.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            document.widthAnchor.constraint(equalTo: scroll.contentView.widthAnchor),
            document.heightAnchor.constraint(greaterThanOrEqualTo:
                                             scroll.contentView.heightAnchor)
        ])
    }

    private func buildSidebar() -> NSView {
        let side = NSView()
        side.translatesAutoresizingMaskIntoConstraints = false
        side.wantsLayer = true
        // Flutter shares its ambient gradient with the side navigation.
        side.layer?.backgroundColor = base.withAlphaComponent(0.12).cgColor
        side.layer?.borderColor = tint().withAlphaComponent(0.18).cgColor
        side.layer?.borderWidth = 1

        let content = stack(spacing: 12)
        content.alignment = .leading
        let logo = NSView()
        logo.wantsLayer = true
        logo.layer?.cornerRadius = 13
        logo.layer?.backgroundColor = tint().cgColor
        logo.layer?.borderColor = sea.withAlphaComponent(0.38).cgColor
        logo.layer?.borderWidth = 1
        logo.translatesAutoresizingMaskIntoConstraints = false
        logo.widthAnchor.constraint(equalToConstant: 42).isActive = true
        logo.heightAnchor.constraint(equalToConstant: 42).isActive = true
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
                         size: 17, weight: .bold)
        brand.alignment = .center
        content.addArrangedSubview(brand)
        brand.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        content.setCustomSpacing(31, after: brand)

        let navs = [
            ("⚡", "Quick connect"), ("◎", "Locations"),
            ("⚙", "Settings"), ("◉", "Account")
        ]
        for (index, entry) in navs.enumerated() {
            let control = button(entry.0 + "    " + entry.1,
                action: #selector(changeTab(_:)), tag: index,
                primary: tab == index, mutedButton: true)
            control.alignment = .left
            control.heightAnchor.constraint(equalToConstant: 54).isActive = true
            content.addArrangedSubview(control)
            control.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        }

        let quick = stack(.horizontal, spacing: 5)
        quick.distribution = .fillEqually
        if accountSession?.supportURL != nil {
            quick.addArrangedSubview(button("Support",
                action: #selector(openSupport(_:)), mutedButton: true))
        }
        if accountSession?.renewalURL != nil {
            quick.addArrangedSubview(button("Renew",
                action: #selector(openRenewal(_:)), mutedButton: true))
        }
        if accountSession?.websiteURL != nil {
            quick.addArrangedSubview(button("Website",
                action: #selector(openWebsite(_:)), mutedButton: true))
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
        let logout = button("Sign out", action: #selector(signOut(_:)),
                            mutedButton: true)
        logout.alignment = .left
        content.addArrangedSubview(logout)
        logout.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        spaced(side, content, inset: 17)
        return side
    }

    private func connectPage() -> NSView {
        let main = stack(spacing: 11)
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
        fabric.heightAnchor.constraint(equalToConstant: 165).isActive = true
        main.addArrangedSubview(fabric)
        fabric.widthAnchor.constraint(equalTo: main.widthAnchor).isActive = true

        let buttonRow = stack(.horizontal, spacing: 0)
        let leftGap = NSView()
        let rightGap = NSView()
        buttonRow.addArrangedSubview(leftGap)
        let connect = button("ϟ    Connect now     ›",
            action: #selector(unavailableConnect(_:)), primary: true)
        connect.isEnabled = false
        connect.toolTip = "VPN startup requires an installed and signed Packet Tunnel"
        connect.heightAnchor.constraint(equalToConstant: 53).isActive = true
        connect.widthAnchor.constraint(equalToConstant: 255).isActive = true
        buttonRow.addArrangedSubview(connect)
        buttonRow.addArrangedSubview(rightGap)
        leftGap.widthAnchor.constraint(equalTo: rightGap.widthAnchor).isActive = true
        main.addArrangedSubview(buttonRow)
        buttonRow.widthAnchor.constraint(equalTo: main.widthAnchor).isActive = true

        main.addArrangedSubview(homeSubscriptionSummary())

        let selectedServer = snapshot?.servers.first { $0.id == activeServer }
        let location = selectedServer.map {
            flag($0.country) + " " + countryName($0.country) + " · " + $0.name
        } ?? "Choose location"
        let protocolName = snapshot?.protocols.first {
            $0.code == activeProtocol
        }?.name ?? "Choose protocol"

        let footer = stack(.horizontal, spacing: 9)
        footer.distribution = .fillEqually
        footer.addArrangedSubview(compactMetric("Location", value: location))
        footer.addArrangedSubview(compactMetric("Public IP", value: "—"))
        footer.addArrangedSubview(compactMetric("Protocol", value: protocolName))
        main.addArrangedSubview(footer)
        footer.widthAnchor.constraint(equalTo: main.widthAnchor).isActive = true
        main.addArrangedSubview(button("Change location or protocol   ›",
            action: #selector(showLocations(_:)), mutedButton: true))
        return card([main], radius: 27, padding: 17)
    }

    private func networkMetric(_ title: String, value: String,
                               subtitle: String = "",
                               valueColor: NSColor? = nil) -> NSView {
        let content = stack(spacing: 13)
        content.alignment = .leading
        content.addArrangedSubview(text(title, size: 11,
                                       weight: .semibold, color: muted))
        content.addArrangedSubview(text(value, size: 22, weight: .bold,
                                        color: valueColor))
        if !subtitle.isEmpty {
            content.addArrangedSubview(text(subtitle, size: 10, color: muted))
        }
        let panel = card([content], radius: 16, padding: 13)
        panel.heightAnchor.constraint(greaterThanOrEqualToConstant: 97).isActive = true
        return panel
    }

    private func networkStatusPage() -> NSView {
        let content = stack(spacing: 16)
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

        let divider = separator()
        content.addArrangedSubview(divider)
        divider.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        content.addArrangedSubview(text("◷  Connected for    00:00:00",
                                       size: 12, color: muted))

        let selected = snapshot?.servers.first { $0.id == activeServer }
        let reportedPing = pingText(selected)

        let network = stack(.horizontal, spacing: 10)
        network.distribution = .fillEqually
        network.addArrangedSubview(networkMetric("⚡  Server ping", value: reportedPing,
            subtitle: pingDetails(selected), valueColor: pingColor(selected)))
        network.addArrangedSubview(networkMetric("◉  Public IP", value: "—"))
        content.addArrangedSubview(network)
        network.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true

        let traffic = stack(.horizontal, spacing: 10)
        traffic.distribution = .fillEqually
        traffic.addArrangedSubview(networkMetric("↓  Download", value: "—",
                                                  subtitle: "Session total: —"))
        traffic.addArrangedSubview(networkMetric("↑  Upload", value: "—",
                                                  subtitle: "Session total: —"))
        content.addArrangedSubview(traffic)
        traffic.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true

        let location = selected.map {
            flag($0.country) + "  " + countryName($0.country) + " · " + $0.name
        } ?? "Select location"
        let change = button(location + "                   Locations  ›",
            action: #selector(showLocations(_:)), mutedButton: true)
        change.alignment = .left
        change.heightAnchor.constraint(equalToConstant: 45).isActive = true
        content.addArrangedSubview(change)
        change.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true

        // Offline mode never fabricates session bytes, handshakes or an IP.
        return card([content], radius: 25, padding: 20)
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

    private func countryName(_ code: String) -> String {
        Locale(identifier: "en_US").localizedString(forRegionCode: code.uppercased())
            ?? code.uppercased()
    }

    private func protocolChips() -> NSView {
        let list = snapshot?.protocols ?? []
        protocolChipCodes = [nil] + list.map { Optional($0.code) }
        let options = [("All", Optional<String>.none)] +
            list.map { ($0.name, Optional($0.code)) }
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
        return group
    }

    // Locations follow Flutter's Search -> protocol chips -> country accordion.
    // All data is scoped to the authenticated panel session. Node inventory
    // alone never guarantees a protocol-specific connection profile.
    private func locationsPage() -> NSView {
        let wrapper = stack(spacing: 14)
        wrapper.alignment = .leading

        let searchRow = stack(.horizontal, spacing: 10)
        searchRow.alignment = .centerY
        let search = NSSearchField()
        search.placeholderString = "Search servers"
        search.stringValue = locationSearch
        search.sendsWholeSearchString = true
        search.sendsSearchStringImmediately = false
        search.toolTip = "Press Return to filter by name or country"
        search.target = self
        search.action = #selector(searchLocations(_:))
        search.translatesAutoresizingMaskIntoConstraints = false
        search.heightAnchor.constraint(equalToConstant: 40).isActive = true
        searchRow.addArrangedSubview(search)
        searchRow.addArrangedSubview(button("↻", action: #selector(refresh(_:))))
        wrapper.addArrangedSubview(searchRow)
        searchRow.widthAnchor.constraint(equalTo: wrapper.widthAnchor).isActive = true

        let ping = button(pingAllBusy ? "⚡  Testing server ping…" :
                "⚡  Ping all servers",
                action: #selector(pingAllServers(_:)), mutedButton: true)
        ping.isEnabled = !pingAllBusy && !(snapshot?.servers.isEmpty ?? true)
        ping.toolTip = "Send one ICMP echo to each public server probe IP"
        ping.heightAnchor.constraint(equalToConstant: 32).isActive = true
        wrapper.addArrangedSubview(ping)
        ping.widthAnchor.constraint(equalTo: wrapper.widthAnchor).isActive = true
        let chips = protocolChips()
        wrapper.addArrangedSubview(chips)
        chips.widthAnchor.constraint(equalTo: wrapper.widthAnchor).isActive = true

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
                                   radius: 17, padding: 17)
            wrapper.addArrangedSubview(placeholder)
            placeholder.widthAnchor.constraint(equalTo: wrapper.widthAnchor).isActive = true
        }
        for (index, code) in codes.enumerated() {
            let items = grouped[code] ?? []
            let expanded = expandedCountries.contains(code)
            let group = stack(spacing: 10)
            group.alignment = .leading
            let header = button(
                flag(code) + "    " + countryName(code) + "     " +
                String(items.count) + (items.count == 1 ? " server" : " servers") +
                (expanded ? "    ⌃" : "    ⌄"),
                action: #selector(toggleLocationCountry(_:)), tag: index)
            header.alignment = .left
            header.heightAnchor.constraint(equalToConstant: 49).isActive = true
            group.addArrangedSubview(header)
            header.widthAnchor.constraint(equalTo: group.widthAnchor).isActive = true
            if expanded {
                for server in items {
                    let index = locationRowIDs.firstIndex(of: server.id) ?? -1
                    let indicator = server.online ? "● Online" : "○ Offline"
                    let line = (activeServer == server.id ? "✓ " : "  ") +
                        server.name + "    " + indicator
                    let choose = button(line,
                        action: #selector(selectLocationServer(_:)),
                        tag: index, primary: activeServer == server.id,
                        mutedButton: activeServer != server.id)
                    choose.alignment = .left
                    choose.heightAnchor.constraint(equalToConstant: 43).isActive = true
                    choose.setContentHuggingPriority(.defaultLow, for: .horizontal)

                    let pingLabel = text(pingText(server), size: 11,
                                         weight: .semibold, color: pingColor(server))
                    pingLabel.toolTip = pingDetails(server)
                    pingLabel.widthAnchor.constraint(equalToConstant: 76).isActive = true
                    let probe = button(nodePingBusy.contains(server.id) ? "…" : "↻",
                                       action: #selector(pingOneServer(_:)),
                                       tag: index, mutedButton: true)
                    probe.widthAnchor.constraint(equalToConstant: 40).isActive = true
                    probe.heightAnchor.constraint(equalToConstant: 35).isActive = true
                    probe.isEnabled = !pingAllBusy &&
                        !nodePingBusy.contains(server.id) && server.probeIP != nil
                    probe.toolTip = server.probeIP == nil ?
                        "No public probe address supplied by the panel" :
                        "Ping this server from your Mac"
                    let serverRow = stack(.horizontal, spacing: 9)
                    serverRow.alignment = .centerY
                    serverRow.addArrangedSubview(choose)
                    serverRow.addArrangedSubview(pingLabel)
                    serverRow.addArrangedSubview(probe)
                    group.addArrangedSubview(serverRow)
                    serverRow.widthAnchor.constraint(equalTo: group.widthAnchor)
                        .isActive = true
                }
            }
            let row = card([group], radius: 17, padding: 11)
            wrapper.addArrangedSubview(row)
            row.widthAnchor.constraint(equalTo: wrapper.widthAnchor).isActive = true
        }
        return card([wrapper], radius: 23, padding: 19)
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
        header.addArrangedSubview(text("✓  Subscription details",
                                       size: 12, weight: .semibold))
        header.addArrangedSubview(button("↻",
                                         action: #selector(refresh(_:)), mutedButton: true))
        items.addArrangedSubview(header)

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
        usage.addArrangedSubview(text("Data usage     " + used + " / " + quota,
                                      size: 11))
        let progress = NSProgressIndicator()
        progress.isIndeterminate = false
        progress.minValue = 0
        progress.maxValue = 100
        if let account = account, account.limitBytes > 0 {
            progress.doubleValue = max(0, min(100,
                Double(account.usedBytes) / Double(account.limitBytes) * 100))
        } else {
            progress.doubleValue = 0
        }
        progress.style = .bar
        progress.translatesAutoresizingMaskIntoConstraints = false
        usage.addArrangedSubview(progress)
        progress.widthAnchor.constraint(equalTo: usage.widthAnchor).isActive = true
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
        let usageCard = card([usage], radius: 13, padding: 10)
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
        return card([items], radius: 20, padding: 12)
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
                // Like the Windows client, automatically probe up to 24
                // public node addresses without delaying authenticated UI.
                if !self.didAutoPing {
                    self.didAutoPing = true
                    let targets = Array(data.servers.filter {
                        $0.probeIP != nil
                    }.prefix(24))
                    self.pingNodes(targets)
                }
            }
            if data.sectionsLoaded.contains("protocols"),
               let selected = self.activeProtocol,
               !data.protocols.contains(where: { $0.code == selected }) {
                self.activeProtocol = nil
            }
            if data.sectionsLoaded.contains("servers"),
               let selected = self.activeServer,
               !data.servers.contains(where: { $0.id == selected }) {
                self.activeServer = nil
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

    @objc private func changeTab(_ sender: NSButton) {
        tab = sender.tag
        view = build()
    }

    @objc private func searchLocations(_ sender: NSSearchField) {
        locationSearch = sender.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        view = build()
    }

    @objc private func selectProtocolChip(_ sender: NSButton) {
        guard protocolChipCodes.indices.contains(sender.tag) else { return }
        activeProtocol = protocolChipCodes[sender.tag]
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
        status = "Location selected. A signed VPN engine is required to connect."
        view = build()
    }

    @objc private func changeQuickServer(_ sender: NSPopUpButton) {
        activeServer = sender.selectedItem?.representedObject as? String
        status = "Location selected. VPN connection remains unavailable."
        view = build()
    }

    @objc private func changeQuickProtocol(_ sender: NSPopUpButton) {
        activeProtocol = sender.selectedItem?.representedObject as? String
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

    @objc private func unavailableConnect(_ sender: NSButton) {
        // Defensive: never claim a live VPN or request private profiles here.
        status = "Connection unavailable: Apple-signed PacketTunnel required."
        view = build()
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
        let report = [
            "TwinConnect native AppKit UI (Flutter/Metal unavailable)",
            "VPN: unavailable — unsigned Network Extension",
            "App account: " + (accountSession == nil ? "signed out" : "signed in"),
            "Server inventory: " + (snapshot == nil ? "not loaded" : "panel loaded")
        ].joined(separator: "\n")
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(report, forType: .string)
        sender.title = "Copied"
    }
}
