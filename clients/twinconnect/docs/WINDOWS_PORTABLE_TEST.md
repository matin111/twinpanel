# TwinConnect Windows x64 — Dev UI and experimental WireGuard

There are **two different Windows artifacts**, both built by the same GitHub Actions
workflow. Do not confuse the visual demo with the authenticated client.

## 1. Dev Dashboard (offline visual design)

Artifact: `TwinConnect-Windows-x64-Dev-Dashboard`.

- Four pages, glass UI, animations, server placeholders and 16 protocol labels.
- Fake sample nodes are never routed to native Windows services.
- The connect button is intentionally disabled. No live account or profiles.

## 2. Portable — authenticated WireGuard prototype

Artifact: `TwinConnect-Windows-x64-Portable`.

Requires:
1. Official WireGuard for Windows installed from https://www.wireguard.com/install/.
2. Run TwinConnect Portable as **Administrator** to manage a Windows tunnel service.
3. A configured HTTPS `TWINCONNECT_DIRECTORY_URL` **during build**, a deployed
   app-entitled license/directory registration, a working panel, and a valid
   *separate app* username and password.
4. Your subscription must have an authorized WireGuard protocol profile and
   at least one assigned, online node. **No fixture/demo server is usable.**
5. The selected node must supply exactly one WireGuard `config` with
   matching `node_id`, one peer, DNS, endpoint and either an IPv4 `/0`
   default route or the panel's existing split `0.0.0.0/1, 128.0.0.0/1`
   routes. **Only for the requested protected full-tunnel mode**, the native
   adapter derives local `AllowedIPs = 0.0.0.0/0, ::/0` before encrypting
   the runtime configuration. The original panel profile, keys, address and
   endpoint are never changed. Unknown custom routes are refused.

### Test sequence

1. Extract the entire ZIP before launching. Keep the EXE, DLLs and data files together.
2. Install official WireGuard for Windows from its publisher's website.
3. Start `twinconnect.exe` **as Administrator**.
4. Sign in with the app-specific credentials from the subscription.
5. In the Windows WireGuard card select a server and click **Start WireGuard**.
6. Check **Check status**. **Interface up** only means Windows reports the
   tunnel service running. **Peer handshake verified** means the official
   `wg.exe` utility returned a recent actual peer handshake. These are distinct.
7. Review the real received/sent byte counters (cumulative, not speed).
8. Independently verify public IP, IPv4 and IPv6 routing, DNS and leak behavior
   before treating the connection as production-ready.
9. Click **Stop interface** and confirm the dedicated tunnel service is gone.

### Security architecture

The bridge calls only the locally installed official `wireguard.exe` and
`wg.exe`, never `cmd.exe`, arbitrary process paths, shell scripts, or
downloaded binaries. The sensitive configuration is encrypted with Windows
DPAPI (LocalMachine scope) **before** writing; the encrypted file lives in
`%ProgramData%\\TwinConnect` with a SYSTEM/Administrators-only ACL.
The dedicated service is called `WireGuardTunnel$TwinConnect`.
The bridge never logs the private key or a profile. Disconnect removes the
service and encrypted file. Service status is fetched from Windows SCM and
handshake/traffic from the installed official `wg.exe`.

The desktop process must already be elevated. The app does not silently
install a driver or bypass Windows UAC. If it lacks admin rights or the
official WireGuard client is missing, the connection remains unavailable.
Only one experimental TwinConnect tunnel can be used on a PC at once.

**Important limits:**
- This is an unsigned **experimental** client, not a customer release.
- A service running or recent WireGuard handshake does **not** independently
  verify external internet, correct exit IP, DNS leaks or IPv6 leak prevention.
- Kill Switch and sharing VPN with other devices are not guaranteed; do not
  infer their status from the UI preview.
- Additional protocols, including OpenVPN, Cisco, Hysteria2 and the other
  TwinPanel offerings, require independent audited adapters and testing.
- The signed release, crash recovery, policy audits and deployment checks
  remain future hardening work.

## CI

The Windows Preview workflow generates the native Flutter runner, installs
the reviewed bridge, runs Flutter analyzer/tests, and compiles/archives both
portable variants. **Successful compilation is not proof of real VPN
connectivity**; the above end-to-end Windows test is still required.
