# Spoof Tunnel third-party core

TwinPanel packages the upstream `spoof-tunnel` Linux amd64 core as an unmodified, pinned third-party runtime dependency for the `spoof_wg` transport candidate.

- Upstream: https://github.com/ParsaKSH/spoof-tunnel
- Upstream source commit: `ba29f0c8e22da5a905a74a8137e01a22f0443e60`
- Upstream release: `v3.1.0-beta.0`
- Upstream asset: `spoof-linux-amd64`
- Expected SHA256: `4ba5597568607e864fb6d5ba4f13bac91a50456da5696d99463d6375ce2a3697`
- License: Apache License 2.0 (see `LICENSE` in this directory)

The TwinPanel publisher downloads that exact release asset, verifies the pinned SHA256, renames it to `backend/artifacts/spoof-tunnel-linux-x86_64`, and embeds it in the immutable TwinPanel prebuilt release. Production nodes receive the verified copy from the TwinPanel release and do not download the core from upstream.

TwinPanel does not enable XDP in V202. The first production implementation uses the upstream raw-socket path and wraps a private WireGuard /30 so existing TwinPanel L3 health, policy routing, NAT and throughput qualification remain authoritative.
