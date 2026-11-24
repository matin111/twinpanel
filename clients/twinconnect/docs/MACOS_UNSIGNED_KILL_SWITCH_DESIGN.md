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

## Phase 3: lifecycle, durable state and PF adapter

Implemented components:
- Controller: explicit enable, close-before-disconnect, loss/drift handling,
  stale-generation rejection, restart recovery, explicit Reset.
- Root-private journal: exclusive service lock, bounded validated JSON,
  atomic writes, fsync, separate durable ownership of the PF reference.
- PF adapter: closed initial rules, stock PF preflight, syntax normalization,
  dedicated anchor replacement/readback, owned-reference-only removal.
- The native command runner refuses firewall mutation on remote/enrolled
  Termalin hosts. Tests use injected kernels; no actual PF activation.

Remaining acceptance blockers: wire the serialized privileged service and
its independent recovery readiness check; implement pre-connect endpoint
attestation, including OpenVPN, L2TP/ESP, Cisco DTLS and the secondary
TrustTunnel/Sudoku transports; validate PF reference readback format and
effective rule/state/interface behavior under live local-console tests;
then expose the actual verified control in Settings. Do not interpret
rules_readback as proof of leak protection. No release readiness claim.


## Phase 4: live read-only service

The launchd status service is deliberately incapable of enabling PF. It
observes the current kernel PF status and privately attests known engines,
including separate Sudoku and TrustTunnel transport children. It publishes
only a root-owned, bounded, non-secret status file every ten seconds.
The native Settings connection report validates owner, mode and freshness
before displaying it. No activation toggle is presented until live
enforcement and recovery are tested. On the development VPS the service
reports KS_REMOTE_RECOVERY_REQUIRED. No firewall rules are loaded.
