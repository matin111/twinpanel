# Xray REALITY CLI provisioning regression (V83)

## Production evidence

On the real TwinPanel controller, reseller order approval reached account provisioning and failed on protocol `v2ray` for node `TwinPanel Local Core` with:

```text
RuntimeError: REALITY key generation/derivation failed
```

This proves the reseller approval route itself was reached; the failure happened later in Xray account provisioning.

## Root cause

`xray_modern_runtime._state_generator_script()` parses `xray x25519` output in order to persist the REALITY private key and client-side public/password value.

The parser historically accepted these labels after normalization:

- `Private key`
- `PrivateKey`
- `Public key`
- `Password`

Current upstream Xray prints:

```text
PrivateKey: ...
Password (PublicKey): ...
Hash32: ...
```

The old TwinPanel normalizer removed spaces and underscores only. Therefore `Password (PublicKey)` became `password(publickey)`, which did not match `password`, `publickey`, or `public`. `xray x25519` exited successfully, the private key was parsed, the public/password value was dropped, and the generated script raised the generic REALITY generation/derivation error.

`TwinPanel Local Core` is intentionally registered as an Exit (`local://core`) and participates in managed protocol delivery, so excluding it would hide the parser defect rather than repair it. The same parser is used for remote Exit nodes and could fail there with the same Xray CLI generation.

## Fix

V83 adds a fail-closed compatibility layer around the existing Modern Xray state generator:

- normalize CLI labels to alphanumeric characters only;
- accept `passwordpublickey` in addition to legacy `password`, `publickey`, and `public`;
- preserve all state persistence, ports, profile policy, rollback, UUID and node-selection behavior;
- refuse to activate if the expected base parser contract has drifted.

## Regression protection

The executable regression runs the exact generated state script with temporary fake Xray binaries and validates all known upstream output generations:

1. `Private key` + `Public key`
2. `PrivateKey` + `Password`
3. `PrivateKey` + `Password (PublicKey)`
4. existing-private-key derivation through the `x25519 -i` path

The test executes the generated Python state script and verifies the persisted state JSON; it is not a source-string-only assertion.
