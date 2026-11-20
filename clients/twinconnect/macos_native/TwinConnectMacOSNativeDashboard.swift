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

private final class TwinNativePowerRing: NSView {
    override var isFlipped: Bool { false }
    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        let r = min(bounds.width, bounds.height) * 0.42
        let center = NSPoint(x: bounds.midX, y: bounds.midY)
        let outer = NSBezierPath(ovalIn: NSRect(
            x: center.x - r, y: center.y - r,
            width: r * 2, height: r * 2
        ))
        NSColor(calibratedRed: 0.27, green: 0.43, blue: 0.50, alpha: 0.22).setFill()
        outer.fill()
        NSColor(calibratedRed: 0.47, green: 0.72, blue: 0.76, alpha: 0.38).setStroke()
        outer.lineWidth = 1.7
        outer.stroke()
        let arc = NSBezierPath()
        arc.appendArc(withCenter: center, radius: r * 0.68,
                      startAngle: 47, endAngle: 312, clockwise: true)
        arc.lineCapStyle = .round
        arc.lineWidth = 8
        NSColor(calibratedRed: 0.43, green: 0.72, blue: 0.75, alpha: 0.90).setStroke()
        arc.stroke()
        let stem = NSBezierPath()
        stem.move(to: NSPoint(x: center.x, y: center.y + r * 0.83))
        stem.line(to: NSPoint(x: center.x, y: center.y + r * 0.08))
        stem.lineCapStyle = .round
        stem.lineWidth = 8
        NSColor(calibratedRed: 0.67, green: 0.88, blue: 0.86, alpha: 0.96).setStroke()
        stem.stroke()
    }
}

class TwinConnectMacOSNativeDashboard: NSViewController, NSTableViewDataSource,
                                       NSTableViewDelegate {
    private let directory = TwinConnectMacOSNativeDirectory()
    private var accountSession: TwinMacNativeSession?
    private var snapshot: TwinMacNativeSnapshot?
    private var status = ""
    private var busy = false
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

    private func inputField(_ placeholder: String, password: Bool) -> NSTextField {
        let field: NSTextField = password ? NSSecureTextField() : NSTextField()
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
        // Same pre-auth privacy as Flutter: no TwinConnect/reseller branding.
        let form = stack(spacing: 16)
        form.addArrangedSubview(pill("◆", color: sea))
        form.addArrangedSubview(text("Welcome back", size: 29, weight: .bold))
        form.addArrangedSubview(text("Sign in with your TwinConnect app credentials",
                                  size: 13, color: muted))

        let nameTitle = text("Username", size: 13, weight: .semibold)
        let username = inputField("Enter app username", password: false)
        usernameField = username
        let secretTitle = text("Password", size: 13, weight: .semibold)
        let password = inputField("Enter password", password: true)
        passwordField = password
        let fields = stack(spacing: 8)
        for field in [nameTitle, username, secretTitle, password] {
            fields.addArrangedSubview(field)
        }
        fields.setCustomSpacing(18, after: username)
        form.addArrangedSubview(fields)
        username.widthAnchor.constraint(equalTo: fields.widthAnchor).isActive = true
        password.widthAnchor.constraint(equalTo: fields.widthAnchor).isActive = true
        fields.widthAnchor.constraint(equalTo: form.widthAnchor).isActive = true

        let enter = button(busy ? "Signing in…" : "Sign in",
                           action: #selector(signIn(_:)), primary: true)
        form.addArrangedSubview(enter)
        enter.widthAnchor.constraint(equalTo: form.widthAnchor).isActive = true
        enter.heightAnchor.constraint(equalToConstant: 51).isActive = true

        form.addArrangedSubview(separator())
        form.addArrangedSubview(text("Secure app login • Encrypted HTTPS",
                                  size: 11, color: muted))
        if !status.isEmpty {
            form.addArrangedSubview(text(status, size: 12,
                                       color: status.hasPrefix("Sign-in failed")
                                       ? amber : muted))
        }

        let glass = card([form], radius: 28, padding: 31)
        root.addSubview(glass)
        NSLayoutConstraint.activate([
            glass.centerXAnchor.constraint(equalTo: root.centerXAnchor),
            glass.centerYAnchor.constraint(equalTo: root.centerYAnchor),
            glass.widthAnchor.constraint(equalToConstant: 505),
            glass.leadingAnchor.constraint(greaterThanOrEqualTo:
                root.leadingAnchor, constant: 20),
            glass.trailingAnchor.constraint(lessThanOrEqualTo:
                root.trailingAnchor, constant: -20),
        ])
    }

    private func buildShell(in root: NSView) {
        let sidebar = buildSidebar()
        root.addSubview(sidebar)
        NSLayoutConstraint.activate([
            sidebar.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            sidebar.topAnchor.constraint(equalTo: root.topAnchor),
            sidebar.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            sidebar.widthAnchor.constraint(equalToConstant: 234)
        ])
        let workspace = stack(spacing: 17)
        let heading = stack(.horizontal, spacing: 12)
        let titles = ["Quick connect", "Locations", "Settings", "Account"]
        heading.addArrangedSubview(text(titles[tab], size: 26, weight: .bold))
        heading.addArrangedSubview(pill("● Offline", color: muted))
        workspace.addArrangedSubview(heading)
        workspace.addArrangedSubview(text(
            accountSession?.brandName ?? "TwinConnect",
            size: 13, color: muted))
        switch tab {
        case 0: workspace.addArrangedSubview(connectPage())
        case 1: workspace.addArrangedSubview(locationsPage())
        case 2: workspace.addArrangedSubview(settingsPage())
        default: workspace.addArrangedSubview(accountPage())
        }
        if !status.isEmpty {
            workspace.addArrangedSubview(text(status, size: 11, color: muted))
        }
        workspace.addArrangedSubview(text(
            "Live account data from your panel  •  macOS native graphics",
            size: 11, color: muted))
        let area = NSView()
        area.translatesAutoresizingMaskIntoConstraints = false
        spaced(area, workspace, inset: 24)
        root.addSubview(area)
        NSLayoutConstraint.activate([
            area.leadingAnchor.constraint(equalTo: sidebar.trailingAnchor),
            area.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            area.topAnchor.constraint(equalTo: root.topAnchor),
            area.bottomAnchor.constraint(equalTo: root.bottomAnchor)
        ])
        workspace.widthAnchor.constraint(equalTo: area.widthAnchor,
                                         constant: -48).isActive = true
    }

    private func buildSidebar() -> NSView {
        let side = NSView()
        side.wantsLayer = true
        side.layer?.backgroundColor = base.withAlphaComponent(0.90).cgColor
        side.layer?.borderColor = tint().withAlphaComponent(0.18).cgColor
        side.layer?.borderWidth = 1
        let content = stack(spacing: 15)
        let logo = pill("∞", color: sea)
        content.addArrangedSubview(logo)
        content.addArrangedSubview(text(accountSession?.brandName ?? "TwinConnect",
                                        size: 18, weight: .bold))
        content.addArrangedSubview(text("YOUR SECURE WORKSPACE",
                                        size: 9, weight: .bold, color: muted))
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
        content.addArrangedSubview(button("↻  Refresh",
                                          action: #selector(refresh(_:))))
        content.addArrangedSubview(button("Sign out",
                                          action: #selector(signOut(_:))))
        spaced(side, content, inset: 21)
        return side
    }

    private func connectPage() -> NSView {
        let content = stack(spacing: 13)
        let centered = stack(spacing: 9)
        let offline = pill("●  You are offline", color: muted)
        centered.addArrangedSubview(offline)
        let emblem = TwinNativePowerRing(frame:
            NSRect(x: 0, y: 0, width: 160, height: 160))
        emblem.translatesAutoresizingMaskIntoConstraints = false
        emblem.widthAnchor.constraint(equalToConstant: 160).isActive = true
        emblem.heightAnchor.constraint(equalToConstant: 160).isActive = true
        centered.addArrangedSubview(emblem)
        centered.addArrangedSubview(text("Secure connection", size: 21,
                                        weight: .bold))
        centered.addArrangedSubview(text(
            "Choose your server and protocol below", color: muted))
        content.addArrangedSubview(centered)

        let action = button("⏻   Connect", action: #selector(unavailableConnect(_:)),
                            primary: true)
        action.isEnabled = false
        action.heightAnchor.constraint(equalToConstant: 50).isActive = true
        content.addArrangedSubview(action)
        action.widthAnchor.constraint(equalTo: content.widthAnchor).isActive = true
        content.addArrangedSubview(text(
            "VPN unavailable: a signed Apple Network Extension is required.",
            size: 11, color: amber))
        content.addArrangedSubview(separator())
        let stats = stack(.horizontal, spacing: 18)
        for (title, value) in [
            ("PUBLIC IP", "Not connected"), ("PING", "—"),
            ("DOWNLOAD", "0 B/s"), ("UPLOAD", "0 B/s")
        ] {
            let part = stack(spacing: 5)
            part.addArrangedSubview(text(title, size: 10, color: muted))
            part.addArrangedSubview(text(value, size: 12, weight: .semibold))
            stats.addArrangedSubview(part)
        }
        content.addArrangedSubview(stats)
        let selection = stack(.horizontal, spacing: 15)
        selection.addArrangedSubview(text("Location: " +
            (snapshot?.servers.first { $0.id == activeServer }?.name ?? "Not selected"),
            size: 12, color: muted))
        selection.addArrangedSubview(text("Protocol: " +
            (activeProtocol ?? "Not selected"), size: 12, color: muted))
        content.addArrangedSubview(selection)
        let power = card([content], radius: 28, padding: 23)
        power.widthAnchor.constraint(equalTo: content.widthAnchor,
                                     constant: 46).isActive = false
        return power
    }

    private func locationsPage() -> NSView {
        let wrapper = stack(spacing: 12)
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
        scroller.widthAnchor.constraint(greaterThanOrEqualToConstant: 520)
            .isActive = true
        return scroller
    }

    private func settingsPage() -> NSView {
        let group = stack(spacing: 15)
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
        group.addArrangedSubview(text("Your subscription",
                                       size: 20, weight: .bold))
        group.addArrangedSubview(pill(snapshot?.account.status ?? "Loading",
                                       color: muted))
        group.addArrangedSubview(text("User: " +
            (accountSession?.username ?? ""), color: muted))
        if let data = snapshot {
            let used = ByteCountFormatter.string(fromByteCount:
                data.account.usedBytes, countStyle: .file)
            let limit = data.account.limitBytes == 0 ? "Unlimited" :
                ByteCountFormatter.string(fromByteCount: data.account.limitBytes,
                                          countStyle: .file)
            let expiry = data.account.expiresAt.map {
                DateFormatter.localizedString(from: $0, dateStyle: .medium,
                                              timeStyle: .none)
            } ?? "No fixed expiry"
            group.addArrangedSubview(separator())
            group.addArrangedSubview(text("Plan: " + data.planName))
            group.addArrangedSubview(text("Traffic: " + used + " / " + limit))
            group.addArrangedSubview(text("Expires: " + expiry))
            group.addArrangedSubview(text("Device limit: " + String(data.deviceLimit)))
            group.addArrangedSubview(text("Allowed protocols: " +
                String(data.protocols.count), color: muted))
        } else {
            group.addArrangedSubview(text("Loading live account details…",
                                           color: muted))
        }
        group.addArrangedSubview(button("↻ Refresh account",
                                        action: #selector(refresh(_:))))
        return card([group])
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
                self.refreshData()
            }
            self.view = self.build()
        }
    }

    private func refreshData() {
        guard let current = accountSession, !busy else { return }
        busy = true
        directory.loadSnapshot(current) { [weak self] result in
            guard let self = self else { return }
            guard self.accountSession?.accessToken == current.accessToken else { return }
            self.busy = false
            switch result {
            case .failure(let error):
                self.snapshot = nil
                self.status = "Could not refresh panel data: " + error.localizedDescription
                if error.localizedDescription == "APP_LOGIN_INVALID" ||
                   error.localizedDescription == "APP_NOT_AUTHORIZED" {
                    self.accountSession = nil
                }
            case .success(let data):
                self.snapshot = data
                self.status = "Account and node information refreshed."
            }
            self.view = self.build()
        }
    }

    @objc private func refresh(_ sender: NSButton) {
        status = "Refreshing subscription data…"
        refreshData()
        view = build()
    }

    @objc private func signOut(_ sender: NSButton) {
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
