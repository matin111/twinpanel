# tp27-masque

Linux-only TP27 MASQUE carrier used by TwinPanel V151.

Build inputs are pinned in `go.mod`. Production releases compile this binary in GitHub Actions with Go 1.26 for linux/amd64 and package the result with a SHA-256 sidecar under `backend/artifacts/`.

Runtime behavior is implemented in `main.go`; install and SmartAuto integration live in `backend/app/transport_candidates/tp27_masque.py`.
