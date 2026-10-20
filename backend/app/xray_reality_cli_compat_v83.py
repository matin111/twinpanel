from __future__ import annotations

from collections.abc import Callable

from . import xray_modern_runtime


# TWINPANEL_XRAY_REALITY_CLI_COMPAT_V83
#
# Xray changed the x25519 CLI label used for the REALITY public value over
# time:
#
#   old:     Public key: ...
#   newer:   Password: ...
#   current: Password (PublicKey): ...
#
# Modern Runtime V2 normalized only spaces/underscores and accepted
# "password" or "publickey". The current label therefore became
# "password(publickey)" and was silently ignored even though `xray x25519`
# exited successfully. Provisioning then raised:
#
#   RuntimeError: REALITY key generation/derivation failed
#
# Keep the existing state generator, persistence, rollback, ports and profile
# policy unchanged. This compatibility layer only makes its embedded parser
# punctuation-insensitive and recognizes the combined current label. The
# replacement is fail-closed: if the expected V2 parser contract changes, API
# startup raises instead of silently applying an incomplete patch.

_OLD_NORMALIZER = (
    'key = key.strip().lower().replace(" ", "").replace("_", "")'
)
_NEW_NORMALIZER = (
    'key = "".join(ch for ch in key.strip().lower() if ch.isalnum())'
)

_OLD_PUBLIC_KEYS = (
    'elif key in {"password", "publickey", "public"}:'
)
_NEW_PUBLIC_KEYS = (
    'elif key in {"password", "passwordpublickey", "publickey", "public"}:'
)

_runtime_applied = False
_original_state_generator_script: Callable[[str], str] | None = None


def _replace_once(script: str, old: str, new: str, label: str) -> str:
    count = script.count(old)
    if count != 1:
        raise RuntimeError(
            "V83 cannot apply Xray REALITY CLI compatibility: "
            f"{label} occurrence count={count}"
        )
    return script.replace(old, new, 1)


def _state_generator_script_v83(domain: str) -> str:
    if _original_state_generator_script is None:
        raise RuntimeError("V83 original Xray state generator is unavailable")

    script = _original_state_generator_script(domain)

    # Idempotency for callers which retain/generated an already-compatible
    # script during reload-style test setups.
    if _NEW_NORMALIZER in script and _NEW_PUBLIC_KEYS in script:
        return script

    script = _replace_once(
        script,
        _OLD_NORMALIZER,
        _NEW_NORMALIZER,
        "key normalizer",
    )
    script = _replace_once(
        script,
        _OLD_PUBLIC_KEYS,
        _NEW_PUBLIC_KEYS,
        "public-key label set",
    )

    return script


def apply_xray_reality_cli_compat_v83() -> None:
    global _runtime_applied
    global _original_state_generator_script

    if _runtime_applied:
        return

    current = xray_modern_runtime._state_generator_script

    # Validate the exact contract before replacing anything. This turns a
    # future base-runtime drift into an explicit startup failure rather than a
    # recurring provisioning regression.
    probe = current("")
    if _OLD_NORMALIZER not in probe or _OLD_PUBLIC_KEYS not in probe:
        raise RuntimeError(
            "V83 cannot locate the expected Modern Xray x25519 parser contract"
        )

    _original_state_generator_script = current
    xray_modern_runtime._state_generator_script = _state_generator_script_v83
    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_REALITY_CLI_COMPAT_V83_ACTIVE "
        "old_public_key=1 password=1 password_public_key=1 "
        "state_persistence_unchanged=1 profile_policy_unchanged=1",
        flush=True,
    )
