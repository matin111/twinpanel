// Native AppKit rendering of the shared TwinConnect appearance, without Metal.
// The visual design mirrors the Flutter desktop/mobile experience while
// strictly keeping VPN unavailable until a signed and verified PacketTunnel.
import Cocoa

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
    // Match Flutter sections: Quick connect / Locations / Settings / Account.
    private var tab = 0
    private var country = "All countries"
    private var activeProtocol: String?
    private var activeServer: String?
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
        column.alignment = .width
        for child in children { column.addArrangedSubview(child) }
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
        control.isEnabled = !busy
        control.translatesAutoresizingMaskIntoConstraints = false
        control.heightAnchor.constraint(greaterThanOrEqualToConstant: 39)
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
        workspace.alignment = .width
        let heading = stack(.horizontal, spacing: 12)
        let titles = ["Quick connect", "Locations", "Settings", "Account"]
        heading.addArrangedSubview(text(titles[tab], size: 26, weight: .bold))
        heading.addArrangedSubview(pill("● Offline", color: muted))
        workspace.addArrangedSubview(heading)
        workspace.addArrangedSubview(text(
            accountSession?.brandName ?? "TwinConnect",
            size: 13, color: muted))
        switch tab {
        case 0:
            // The shared Flutter desktop layout uses two equally weighted
            // connection/network cards when the usable main column is >=740.
            let availableWidth = nativeContentWidth - 258 - 48
            if availableWidth >= 790 {
                let pair = stack(.horizontal, spacing: 14)
                pair.alignment = .top
                pair.distribution = .fillEqually
                pair.addArrangedSubview(connectPage())
                pair.addArrangedSubview(networkStatusPage())
                workspace.addArrangedSubview(pair)
                pair.widthAnchor.constraint(equalTo: workspace.widthAnchor).isActive = true
            } else {
                workspace.addArrangedSubview(connectPage())
                workspace.addArrangedSubview(networkStatusPage())
            }
        case 1: workspace.addArrangedSubview(locationsPage())
        case 2: workspace.addArrangedSubview(settingsPage())
        default: workspace.addArrangedSubview(accountPage())
        }
        if !status.isEmpty {
            workspace.addArrangedSubview(text(status, size: 11, color: muted))
        }
        workspace.addArrangedSubview(text(
            "Native macOS • panel data is read-only • VPN requires signed PacketTunnel",
            size: 11, color: muted))
        // Keep the dashboard visible even before the account snapshot arrives
        // or when its contents exceed the macOS window height.
        let scroll = NSScrollView()
        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.drawsBackground = false
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.borderType = .noBorder

        let document = NSView()
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
        side.layer?.backgroundColor = base.withAlphaComponent(0.12).cgColor
        side.layer?.borderColor = tint().withAlphaComponent(0.18).cgColor
        side.layer?.borderWidth = 1
        let content = stack(spacing: 15)
        let logo = pill("∞", color: sea)
        content.addArrangedSubview(logo)
        content.addArrangedSubview(text(accountSession?.brandName ?? "TwinConnect",
                                        size: 18, weight: .bold))
        content.addArrangedSubview(text("TwinConnect",
                                        size: 10, weight: .medium, color: muted))
        content.setCustomSpacing(26, after: logo)
        let navs = [
            ("⚡", "Quick connect"), ("◎", "Locations"),
            ("⚙", "Settings"), ("◉", "Account")
        ]
        for (index, item) in navs.enumerated() {
            let prefix = item.0 + "   "
            let entry = button(prefix + item.1, action: #selector(changeTab(_:)),
                               tag: index, primary: tab == index, mutedButton: true)
            entry.alignment = .left
            content.addArrangedSubview(entry)
            entry.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        }
        content.addArrangedSubview(separator())
        content.addArrangedSubview(text("Offline — no verified VPN",
                                        size: 11, color: amber))
        if let data = snapshot {
            content.addArrangedSubview(text(
                "Panel API: \(data.sectionsLoaded.count)/4 sections",
                size: 11, color: data.errors.isEmpty ? sea : amber))
        } else {
            content.addArrangedSubview(text(
                "Panel login accepted • loading data",
                size: 11, color: sea))
        }
        content.addArrangedSubview(button("↻  Refresh",
                                          action: #selector(refresh(_:))))
        content.addArrangedSubview(button("Sign out",
                                          action: #selector(signOut(_:))))
        spaced(side, content, inset: 21)
        return side
    }

    private func connectPage() -> NSView {
        let content = stack(spacing: 12)
        content.alignment = .centerX
        content.addArrangedSubview(pill("⏻  You are offline", color: muted))

        let fabric = TwinNativeNetworkFabric(frame:
            NSRect(x: 0, y: 0, width: 342, height: 178))
        fabric.translatesAutoresizingMaskIntoConstraints = false
        fabric.widthAnchor.constraint(equalToConstant: 342).isActive = true
        fabric.heightAnchor.constraint(equalToConstant: 178).isActive = true
        content.addArrangedSubview(fabric)

        // Exact Windows call-to-action hierarchy. The button stays disabled
        // until an Apple-signed PacketTunnel is proven ready.
        let connectButton = button("⚡    Connect now    ›",
            action: #selector(unavailableConnect(_:)), primary: true)
        connectButton.isEnabled = false
        connectButton.widthAnchor.constraint(equalToConstant: 266).isActive = true
        connectButton.heightAnchor.constraint(equalToConstant: 59).isActive = true
        content.addArrangedSubview(connectButton)

        let subscription = homeSubscriptionSummary()
        content.addArrangedSubview(subscription)
        subscription.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        content.addArrangedSubview(text(
            "A signed macOS Packet Tunnel is required to connect.",
            size: 10, color: amber))
        return card([content], radius: 28, padding: 17)
    }

    // Layout parity with Flutter's independent "Network status" panel.
    // No traffic totals, IP or ping are fabricated in unsigned AppKit mode.
    private func networkStatusPage() -> NSView {
        let content = stack(spacing: 13)
        content.alignment = .width
        let header = stack(.horizontal, spacing: 12)
        header.addArrangedSubview(text("Network status", size: 17,
                                       weight: .semibold))
        header.addArrangedSubview(pill("Disconnected", color: muted))
        content.addArrangedSubview(header)
        content.addArrangedSubview(separator())
        content.addArrangedSubview(text("Connected for   00:00:00",
                                       color: muted))

        let metrics = stack(.horizontal, spacing: 13)
        let selected = snapshot?.servers.first { $0.id == activeServer }
        let reportedPing = selected?.latencyMs.map { String($0) + " ms (panel)" }
            ?? "—"
        for (title, value) in [
            ("Server ping", reportedPing),
            ("Public IP", "—")
        ] {
            let metric = stack(spacing: 8)
            metric.addArrangedSubview(text(title, size: 11, color: muted))
            metric.addArrangedSubview(text(value, size: 17, weight: .bold))
            metrics.addArrangedSubview(card([metric], radius: 17, padding: 15))
        }
        content.addArrangedSubview(metrics)

        let traffic = stack(.horizontal, spacing: 13)
        for (title, value) in [
            ("↓ Download", "—"), ("↑ Upload", "—")
        ] {
            let metric = stack(spacing: 8)
            metric.addArrangedSubview(text(title, size: 11, color: muted))
            metric.addArrangedSubview(text(value, size: 17, weight: .bold))
            traffic.addArrangedSubview(card([metric], radius: 17, padding: 15))
        }
        content.addArrangedSubview(traffic)
        content.addArrangedSubview(text(
            "No VPN interface or verified network traffic in native graphics mode.",
            size: 11, color: amber))
        return card([content], radius: 23, padding: 20)
    }

    private func locationsPage() -> NSView {
        let wrapper = stack(spacing: 12)
        wrapper.alignment = .width
        let title = stack(.horizontal, spacing: 14)
        title.addArrangedSubview(text("Available locations",
                                       size: 20, weight: .bold))
        title.addArrangedSubview(button("↻ Refresh",
                                        action: #selector(refresh(_:))))
        wrapper.addArrangedSubview(title)
        wrapper.addArrangedSubview(text(
            "Panel-reported node status and latency, not an active VPN ping.",
            size: 12, color: muted))
        let selector = NSPopUpButton(frame: .zero, pullsDown: false)
        let countries = Set(snapshot?.servers.map { $0.country } ?? [])
        selector.addItems(withTitles: ["All countries"] + countries.sorted())
        selector.selectItem(withTitle: country)
        selector.target = self
        selector.action = #selector(changeCountry(_:))
        wrapper.addArrangedSubview(selector)
        let table = createTable()
        wrapper.addArrangedSubview(table)
        wrapper.addArrangedSubview(text(
            "Select a location to remember it in this window; VPN remains disabled.",
            size: 11, color: muted))
        if let data = snapshot, let failure = data.errors["servers"] {
            wrapper.addArrangedSubview(text(
                "Server inventory unavailable: " + failure,
                size: 12, color: amber))
        }
        return card([wrapper])
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

    private func settingsPage() -> NSView {
        let group = stack(spacing: 15)
        group.alignment = .width
        group.addArrangedSubview(text("Preferences",
                                       size: 20, weight: .bold))
        group.addArrangedSubview(text(
            "Native macOS appearance  •  Secure HTTPS directory",
            size: 13, color: muted))
        group.addArrangedSubview(separator())
        group.addArrangedSubview(text(
            "Kill Switch • Split Tunneling • DNS",
            size: 15, weight: .semibold))
        group.addArrangedSubview(text(
            "These controls remain unavailable until the native tunnel is signed " +
            "and verified. No unprotected toggle is presented as working.",
            size: 12, color: muted))
        group.addArrangedSubview(pill("Connection protection: not verified",
                                       color: amber))
        group.addArrangedSubview(button("Copy diagnostics",
                                        action: #selector(copyDiagnostics(_:))))
        if accountSession?.supportURL != nil {
            group.addArrangedSubview(button("Support",
                                            action: #selector(openSupport(_:))))
        }
        if accountSession?.renewalURL != nil {
            group.addArrangedSubview(button("Renew subscription",
                                            action: #selector(openRenewal(_:))))
        }
        return card([group])
    }

    private func accountPage() -> NSView {
        let group = stack(spacing: 13)
        group.alignment = .width
        group.addArrangedSubview(text("Your subscription",
                                       size: 20, weight: .bold))
        group.addArrangedSubview(pill(snapshot?.account?.status ?? "Account not loaded",
                                       color: muted))
        group.addArrangedSubview(text("User: " +
            (accountSession?.username ?? ""), color: muted))
        if let data = snapshot {
            group.addArrangedSubview(separator())
            group.addArrangedSubview(text("Plan: " + (data.planName ?? "Not available")))
            group.addArrangedSubview(text("Device limit: " +
                (data.deviceLimit.map { String($0) } ?? "—")))
            if let account = data.account {
                let used = ByteCountFormatter.string(fromByteCount:
                    account.usedBytes, countStyle: .file)
                let limit = account.limitBytes == 0 ? "Unlimited" :
                    ByteCountFormatter.string(fromByteCount:
                        account.limitBytes, countStyle: .file)
                let expiry = account.expiresAt.map {
                    DateFormatter.localizedString(from: $0, dateStyle: .medium,
                                                  timeStyle: .none)
                } ?? "No fixed expiry"
                group.addArrangedSubview(text("Traffic: " + used + " / " + limit))
                group.addArrangedSubview(text("Expires: " + expiry))
            } else {
                group.addArrangedSubview(text("Account: " +
                    (data.errors["account"] ?? "Loading…"), color: amber))
            }
            if data.sectionsLoaded.contains("protocols") {
                group.addArrangedSubview(text("Reported protocols: " +
                    String(data.protocols.count) +
                    (data.sectionsLoaded.contains("plan") ? "" : " • plan not verified"),
                    color: muted))
            }
            if data.sectionsLoaded.contains("servers") {
                group.addArrangedSubview(text("Assigned servers: " +
                    String(data.servers.count), color: muted))
            }
        } else {
            group.addArrangedSubview(text("Loading live account details…",
                                           color: muted))
        }
        group.addArrangedSubview(button("↻ Refresh account",
                                        action: #selector(refresh(_:))))
        return card([group])
    }

    private func compactMetric(_ title: String, value: String) -> NSView {
        let metric = stack(spacing: 5)
        metric.addArrangedSubview(text(title, size: 10, color: muted))
        metric.addArrangedSubview(text(value, size: 12, weight: .bold))
        return card([metric], radius: 13, padding: 10)
    }

    private func homeSubscriptionSummary() -> NSView {
        let items = stack(spacing: 8)
        items.alignment = .width
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
        items.addArrangedSubview(card([usage], radius: 13, padding: 10))

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
        accountSession = nil
        snapshot = nil
        activeProtocol = nil
        activeServer = nil
        country = "All countries"
        busy = false
        tab = 0
        status = ""
        view = build()
    }

    @objc private func changeTab(_ sender: NSButton) {
        tab = sender.tag
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
