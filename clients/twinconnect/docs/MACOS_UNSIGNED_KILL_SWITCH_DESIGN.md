# Unsigned macOS Kill Switch: phase 1

The signed Network Extension path already configures includeAllNetworks and
On Demand. The unsigned native path uses separate root-owned engines and
cannot claim that protection. This policy compiler is the common PF basis
for the unsigned path, not an enabled firewall or leak-tested Kill Switch.

## Policy
- Closed mode: only loopback; all other IPv4/IPv6 blocked.
- Active mode: exact attested utun/ppp interface, exact outer root-owned
  TCP/UDP transport IP/port, interface-bound transport states, no general
  uplink/LAN/DNS exemption. Existing state tables must be checked first.
- L2TP/IPsec may require an additional ESP/NAT-T policy; do not infer full
  support from the PPP rules. TCP-only SOCKS engines also require DNS tests.

## Required runtime work before UI activation
- Root-owned controller, independent recovery/watchdog, transactional PF
  anchor ownership and enable reference. Never reload the main PF rules,
  flush global state, disable someone else's PF, or rely on a GUI timer.
- Attest each active worker, its real tunnel interface, outer endpoints and
  port from privileged runtime data, not from UI/user-supplied arbitrary
  exemptions. Validate existing PF rules/state and prevent interface reuse.
- Close policy before route teardown; reconnect under a controlled exception
  policy. Profile refresh/bootstrapping must not silently bypass the lock.
- Verify effective packet blocking, existing connections, IPv6 and DNS,
  abrupt engine death, app exit, network changes and independent recovery.
- On remote VPS, never activate until a separately authorized OOB recovery
  plan and management continuity policy are tested. A management exemption
  must be explicit; it cannot be called a zero-exemption leak test.
- UI state must reflect effective kernel rules, not only user defaults.

Phase 1 runs Apple's PF syntax checker with -n only. No root firewall
configuration is changed by this code or its tests.
