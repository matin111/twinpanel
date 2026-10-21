# TP27 MASQUE V151 CI gates

The V151 PR must keep the existing TwinPanel regression suite green and additionally pass:

- Python compile for transport registry / manager integration;
- Go 1.26 `go vet` for the MASQUE binary;
- linux/amd64 CGO-disabled build;
- exact `connect-ip-go v0.4.0` module requirement;
- dependency checksum generation and read-only rebuild;
- static checks for certificate pinning, bearer authentication, isolated runtime pool and release packaging.

No merge or release is accepted with a red MASQUE or historical TP27 check.
