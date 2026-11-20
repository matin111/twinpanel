// Metal-independent AppKit TwinConnect shell: live login, plan, protocols and nodes.
// This mode does NOT request native profiles or start a VPN tunnel.
import Cocoa

class TwinConnectMacOSNativeDashboard: NSViewController,
                                       NSTableViewDataSource, NSTableViewDelegate {
    private let directory = TwinConnectMacOSNativeDirectory()
    private var accountSession: TwinMacNativeSession?
    private var snapshot: TwinMacNativeSnapshot?
    private var status = "Sign in with your TwinConnect app username and password."
    private var busy = false
    private var tab = 0
    private var country = "All countries"
    private var activeProtocol: String?
    private var activeServer: String?
    private weak var usernameField: NSTextField?
    private weak var passwordField: NSSecureTextField?
    private weak var listView: NSTableView?

    private let ink = NSColor(calibratedRed: 0.065, green: 0.085, blue: 0.15, alpha: 1)
    private let surface = NSColor(calibratedRed: 0.105, green: 0.13, blue: 0.205, alpha: 1)
    private let muted = NSColor(calibratedWhite: 0.72, alpha: 1)
    private let purple = NSColor(calibratedRed: 0.45, green: 0.30, blue: 0.94, alpha: 1)
    private let green = NSColor(calibratedRed: 0.30, green: 0.91, blue: 0.68, alpha: 1)

    override func loadView() {
        view = build()
    }

    private func text(_ string: String, size: CGFloat = 14,
                      weight: NSFont.Weight = .regular,
                      color: NSColor? = nil) -> NSTextField {
        let label = NSTextField(wrappingLabelWithString: string)
        label.font = NSFont.systemFont(ofSize: size, weight: weight)
        label.textColor = color ?? .white
        label.isSelectable = true
        label.maximumNumberOfLines = 0
        return label
    }

    private func stack(_ axis: NSUserInterfaceLayoutOrientation = .vertical,
                       spacing: CGFloat = 12) -> NSStackView {
        let v = NSStackView()
        v.orientation = axis
        v.alignment = axis == .vertical ? .leading : .centerY
        v.spacing = spacing
        v.translatesAutoresizingMaskIntoConstraints = false
        return v
    }

    private func button(_ label: String, action: Selector, tag: Int = 0,
                        primary: Bool = false) -> NSButton {
        let control = NSButton(title: label, target: self, action: action)
        control.bezelStyle = .rounded
        control.controlSize = .large
        control.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
        control.tag = tag
        control.isEnabled = !busy
        if primary {
            control.contentTintColor = purple
        }
        return control
    }

    private func panel(_ children: [NSView]) -> NSView {
        let box = NSView()
        box.wantsLayer = true
        box.layer?.backgroundColor = surface.cgColor
        box.layer?.cornerRadius = 17
        let contents = stack(spacing: 14)
        children.forEach { contents.addArrangedSubview($0) }
        box.addSubview(contents)
        NSLayoutConstraint.activate([
            contents.topAnchor.constraint(equalTo: box.topAnchor, constant: 20),
            contents.bottomAnchor.constraint(equalTo: box.bottomAnchor, constant: -20),
            contents.leadingAnchor.constraint(equalTo: box.leadingAnchor, constant: 23),
            contents.trailingAnchor.constraint(equalTo: box.trailingAnchor, constant: -23)
        ])
        return box
    }

    private func build() -> NSView {
        let root = NSView(frame: NSRect(x: 0, y: 0, width: 1000, height: 660))
        root.wantsLayer = true
        root.layer?.backgroundColor = ink.cgColor

        let layout = stack(spacing: 18)
        root.addSubview(layout)
        NSLayoutConstraint.activate([
            layout.topAnchor.constraint(equalTo: root.topAnchor, constant: 28),
            layout.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 40),
            layout.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -40),
            layout.bottomAnchor.constraint(lessThanOrEqualTo: root.bottomAnchor,
                                            constant: -20)
        ])

        let heading = stack(.horizontal, spacing: 16)
        heading.addArrangedSubview(text("●  TwinConnect", size: 28, weight: .bold))
        heading.addArrangedSubview(text("macOS native", size: 12,
                                        weight: .medium, color: green))
        layout.addArrangedSubview(heading)

        let warning = panel([
            text("NATIVE GRAPHICS MODE", size: 11,
                 weight: .bold, color: green),
            text("VPN connection is unavailable in this mode. Login and live account " +
                 "information work without Metal; a signed Network Extension is still " +
                 "required for an actual tunnel.", size: 13, color: muted)
        ])
        layout.addArrangedSubview(warning)
        warning.widthAnchor.constraint(equalTo: layout.widthAnchor).isActive = true

        if accountSession == nil {
            layout.addArrangedSubview(loginPanel())
        } else {
            layout.addArrangedSubview(accountControls())
        }
        layout.addArrangedSubview(text(status, size: 12, color: muted))
        return root
    }

    private func loginPanel() -> NSView {
        let title = text("Sign in to your account", size: 24, weight: .bold)
        let subtitle = text("Use your app username (with tenant prefix) and password. " +
                            "No account credentials are saved on this Mac.",
                            size: 13, color: muted)

        let username = NSTextField()
        username.placeholderString = "App username"
        username.font = NSFont.systemFont(ofSize: 15)
        username.controlSize = .large
        username.translatesAutoresizingMaskIntoConstraints = false
        username.widthAnchor.constraint(greaterThanOrEqualToConstant: 420).isActive = true
        usernameField = username
        let password = NSSecureTextField()
        password.placeholderString = "Password"
        password.font = NSFont.systemFont(ofSize: 15)
        password.controlSize = .large
        password.translatesAutoresizingMaskIntoConstraints = false
        password.widthAnchor.constraint(greaterThanOrEqualToConstant: 420).isActive = true
        passwordField = password

        let login = button(busy ? "Signing in…" : "Sign in",
                           action: #selector(signIn(_:)), primary: true)
        return panel([title, subtitle, username, password, login,
                      text("Directory: verified HTTPS • Native UI: AppKit",
                           size: 11, color: muted)])
    }

    private func accountControls() -> NSView {
        guard let session = accountSession else { return NSView() }
        let column = stack(spacing: 17)
        let title = stack(.horizontal, spacing: 12)
        title.addArrangedSubview(text(session.brandName, size: 22, weight: .bold))
        title.addArrangedSubview(text(session.username, size: 12, color: muted))
        column.addArrangedSubview(title)

        let navigation = stack(.horizontal, spacing: 8)
        ["Dashboard", "Servers", "Protocols", "Settings"].enumerated().forEach {
            index, name in
            let item = button((index == tab ? "● " : "") + name,
                              action: #selector(changeTab(_:)), tag: index,
                              primary: tab == index)
            navigation.addArrangedSubview(item)
        }
        navigation.addArrangedSubview(button("Refresh", action: #selector(refresh(_:))))
        navigation.addArrangedSubview(button("Sign out", action: #selector(signOut(_:))))
        column.addArrangedSubview(navigation)

        switch tab {
        case 0:
            column.addArrangedSubview(homePanel())
        case 1:
            column.addArrangedSubview(serverPanel())
        case 2:
            column.addArrangedSubview(protocolPanel())
        default:
            column.addArrangedSubview(settingsPanel())
        }
        return column
    }

    private func homePanel() -> NSView {
        let info: [NSView]
        if let data = snapshot {
            let account = data.account
            let usage = ByteCountFormatter.string(fromByteCount: account.usedBytes,
                                                  countStyle: .file)
            let limit = account.limitBytes == 0 ? "Unlimited" :
                ByteCountFormatter.string(fromByteCount: account.limitBytes, countStyle: .file)
            let expiry = account.expiresAt.map {
                DateFormatter.localizedString(from: $0, dateStyle: .medium, timeStyle: .none)
            } ?? "No fixed expiry"
            info = [
                text("Subscription overview", size: 21, weight: .bold),
                text("Status: " + account.status + "   •   Plan: " + data.planName),
                text("Traffic: " + usage + " / " + limit),
                text("Expires: " + expiry + "   •   Device limit: " +
                     String(data.deviceLimit)),
                text("Nodes from panel: " + String(data.servers.count) +
                     "   •   Allowed protocols: " + String(data.protocols.count)),
                text("VPN: Disconnected — engine unavailable without Apple signing",
                     size: 13, weight: .semibold, color: green)
            ]
        } else {
            info = [
                text("Subscription overview", size: 21, weight: .bold),
                text("Loading your plan, account, servers and protocol permissions…",
                     size: 13, color: muted)
            ]
        }
        return panel(info)
    }

    private func filteredServers() -> [TwinMacNativeServer] {
        guard let servers = snapshot?.servers else { return [] }
        if country == "All countries" { return servers }
        return servers.filter { $0.country == country }
    }

    private func serverPanel() -> NSView {
        let column = stack(spacing: 12)
        column.addArrangedSubview(text("Your servers", size: 21, weight: .bold))
        column.addArrangedSubview(text(
            "Live inventory from your panel. Online and latency are panel-reported, " +
            "not an active VPN connection or a fresh ping from this Mac.",
            size: 12, color: muted
        ))
        let selector = NSPopUpButton(frame: .zero, pullsDown: false)
        let countries = Set(snapshot?.servers.map { $0.country } ?? [])
        selector.addItems(withTitles: ["All countries"] + countries.sorted())
        selector.selectItem(withTitle: country)
        selector.target = self
        selector.action = #selector(changeCountry(_:))
        column.addArrangedSubview(selector)
        column.addArrangedSubview(makeTable(protocols: false))
        column.addArrangedSubview(text("Selected node: " +
            (snapshot?.servers.first { $0.id == activeServer }?.name ?? "None") +
            "  •  Connect disabled in native graphics mode.",
            size: 12, color: muted))
        return panel([column])
    }

    private func protocolPanel() -> NSView {
        let column = stack(spacing: 12)
        column.addArrangedSubview(text("Protocols allowed by your plan",
                                     size: 21, weight: .bold))
        column.addArrangedSubview(text(
            "Only protocols explicitly selected by the panel and permitted " +
            "by your plan appear here. A stored configuration is NOT proof " +
            "that the macOS VPN engine is ready.", size: 12, color: muted))
        column.addArrangedSubview(makeTable(protocols: true))
        column.addArrangedSubview(text(
            "Selected protocol: " + (activeProtocol ?? "None") +
            "  •  Native packet tunneling is unavailable in this mode.",
            size: 12, color: muted))
        return panel([column])
    }

    private func settingsPanel() -> NSView {
        let column = stack(spacing: 14)
        column.addArrangedSubview(text("Settings and support",
                                     size: 21, weight: .bold))
        column.addArrangedSubview(text(
            "Interface: Native AppKit (without Flutter/Metal)",
            size: 13))
        column.addArrangedSubview(text(
            "Connection engine: Unavailable without signed PacketTunnel",
            size: 13, color: muted))
        column.addArrangedSubview(text(
            "The app never stores your password or access token in this mode.",
            size: 12, color: muted))
        if accountSession?.supportURL != nil {
            column.addArrangedSubview(button("Support",
                action: #selector(openSupport(_:))))
        }
        if accountSession?.renewalURL != nil {
            column.addArrangedSubview(button("Renew subscription",
                action: #selector(openRenewal(_:))))
        }
        column.addArrangedSubview(button("Copy diagnostics",
            action: #selector(copyDiagnostics(_:))))
        return panel([column])
    }

    private func makeTable(protocols: Bool) -> NSView {
        let table = NSTableView(frame: .zero)
        table.headerView = NSTableHeaderView()
        table.usesAlternatingRowBackgroundColors = true
        table.backgroundColor = surface
        table.rowHeight = 31
        table.intercellSpacing = NSSize(width: 10, height: 3)
        let columns: [(String, String, CGFloat)] = protocols
            ? [("main", "Protocol", 290), ("detail", "Profile", 240)]
            : [("main", "Server", 310), ("country", "Country", 130),
               ("detail", "Panel status / latency", 250)]
        for (key, title, width) in columns {
            let col = NSTableColumn(identifier: NSUserInterfaceItemIdentifier(key))
            col.title = title
            col.width = width
            col.minWidth = 95
            table.addTableColumn(col)
        }
        table.dataSource = self
        table.delegate = self
        table.target = self
        table.action = #selector(selectRow(_:))
        listView = table
        let scrolling = NSScrollView(frame: .zero)
        scrolling.documentView = table
        scrolling.hasVerticalScroller = true
        scrolling.borderType = .noBorder
        scrolling.translatesAutoresizingMaskIntoConstraints = false
        scrolling.widthAnchor.constraint(greaterThanOrEqualToConstant: 690).isActive = true
        scrolling.heightAnchor.constraint(equalToConstant: 275).isActive = true
        return scrolling
    }

    func numberOfRows(in tableView: NSTableView) -> Int {
        if tab == 2 { return snapshot?.protocols.count ?? 0 }
        return filteredServers().count
    }

    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?,
                   row: Int) -> NSView? {
        guard let key = tableColumn?.identifier.rawValue else { return nil }
        let string: String
        if tab == 2 {
            guard let items = snapshot?.protocols, items.indices.contains(row) else {
                return nil
            }
            let item = items[row]
            string = key == "main" ? item.name :
                (item.configured ? "Record present • VPN unavailable" :
                                 "No profile record • VPN unavailable")
        } else {
            let items = filteredServers()
            guard items.indices.contains(row) else { return nil }
            let item = items[row]
            if key == "main" {
                string = item.name
            } else if key == "country" {
                string = item.country.uppercased()
            } else {
                string = (item.online ? "Online (panel)" : "Offline (panel)") +
                    (item.latencyMs.map { " • \($0) ms" } ?? " • no latency")
            }
        }
        let cell = NSTableCellView()
        let label = text(string, size: 12,
                         color: key == "main" ? .white : muted)
        label.translatesAutoresizingMaskIntoConstraints = false
        cell.addSubview(label)
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: cell.leadingAnchor, constant: 6),
            label.trailingAnchor.constraint(lessThanOrEqualTo:
                cell.trailingAnchor, constant: -6),
            label.centerYAnchor.constraint(equalTo: cell.centerYAnchor)
        ])
        return cell
    }

    @objc private func signIn(_ sender: NSButton) {
        guard !busy, let username = usernameField?.stringValue,
              let password = passwordField?.stringValue else { return }
        busy = true
        sender.isEnabled = false
        status = "Signing in to your panel securely…"
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
                self.status = "Signed in. Retrieving live subscription information…"
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
            // A logout or new login invalidates responses from the old session.
            guard self.accountSession?.accessToken == current.accessToken else { return }
            self.busy = false
            switch result {
            case .failure(let error):
                self.snapshot = nil
                self.status = "Could not load live account data: " + error.localizedDescription
                if error.localizedDescription == "APP_LOGIN_INVALID" ||
                   error.localizedDescription == "APP_NOT_AUTHORIZED" {
                    self.accountSession = nil
                }
            case .success(let data):
                self.snapshot = data
                self.status = "Account information refreshed from your panel."
            }
            self.view = self.build()
        }
    }

    @objc private func refresh(_ sender: NSButton) {
        status = "Refreshing from your panel…"
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
        status = "Signed out. Credentials are not stored."
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
        guard row >= 0 else { return }
        if tab == 2 {
            let list = snapshot?.protocols ?? []
            if list.indices.contains(row) { activeProtocol = list[row].name }
        } else {
            let list = filteredServers()
            if list.indices.contains(row) { activeServer = list[row].id }
        }
        status = "Selection saved in this window. VPN connection is not available."
    }

    @objc private func openSupport(_ sender: NSButton) {
        if let url = accountSession?.supportURL { NSWorkspace.shared.open(url) }
    }

    @objc private func openRenewal(_ sender: NSButton) {
        if let url = accountSession?.renewalURL { NSWorkspace.shared.open(url) }
    }

    @objc private func copyDiagnostics(_ sender: NSButton) {
        let message = [
            "TwinConnect macOS native AppKit mode",
            "Flutter/Metal renderer: unavailable",
            "VPN: disabled (no signed Network Extension)",
            "API session: " + (accountSession == nil ? "signed out" : "signed in"),
            "Server data: " + (snapshot == nil ? "unavailable" : "panel response loaded")
        ].joined(separator: "\n")
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(message, forType: .string)
        sender.title = "Diagnostics copied"
    }
}
