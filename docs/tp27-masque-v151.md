# TP27 MASQUE V151

TP27 MASQUE is an independent SmartAuto L3 carrier based on RFC 9484 CONNECT-IP over HTTP/3 / QUIC datagrams.

## Runtime contract

- Candidate: `tp27_masque`
- Carrier family: `tp27-masque-connect-ip-h3`
- TUN pool: `10.255.0.0/16` with deterministic per-tunnel `/30`
- Inner MTU: `1280`
- UDP listener candidates: `28400+slot`, `29400+slot`, `30400+slot`
- TLS: 1.3, self-signed per-Exit certificate with SHA-256 leaf pinning on Iran
- Authentication: per-install random bearer token, root-only on both nodes
- Dependency: none on TP27 Fast, FoU, Backhaul, or TP27 Direct TCP

## Selection policy

MASQUE is never forced merely because it is installed. It must pass the existing SmartAuto peer, TCP egress, UDP egress, packet-loss, latency, stability and throughput qualification. On a degraded Iran UDP path it can fail qualification or be quarantined while `tp27_tcp_direct` remains the independent non-UDP fallback.

## Release integrity

The MASQUE binary is built in the verified release workflow from exact Go module versions. The binary is placed under `backend/artifacts/` only during release packaging together with a SHA-256 sidecar. Nodes receive that packaged artifact; they do not download Go modules or binaries during transport installation.

## Production acceptance

A release is not considered accepted until a real Iran/Exit pair proves:

1. both MASQUE systemd units are active;
2. the `tp27m<ID>` interface exists at MTU 1280 on both nodes;
3. bidirectional peer ping succeeds;
4. TCP and UDP internet egress through the MASQUE source address succeed;
5. SmartAuto records a real throughput benchmark;
6. active-lane promotion happens only when MASQUE scores better than the current qualified lane;
7. stopping/blocking the MASQUE UDP path does not break TP27 Fast or TP27 Direct TCP and SmartAuto can fall back.
