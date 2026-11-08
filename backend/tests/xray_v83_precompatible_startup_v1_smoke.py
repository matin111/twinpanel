"""Xray pre-compatible CLI parser must not crash API startup."""
from unittest.mock import patch
from app import xray_modern_runtime
from app import xray_reality_cli_compat_v83 as compat


def main():
    current = xray_modern_runtime._state_generator_script
    probe = current("")
    assert compat._OLD_NORMALIZER in probe
    assert '"password(publickey)"' in probe

    old = compat._runtime_applied
    old_source = compat._original_state_generator_script
    try:
        compat._runtime_applied = False
        compat._original_state_generator_script = None
        compat.apply_xray_reality_cli_compat_v83()
        assert compat._runtime_applied is True
        assert xray_modern_runtime._state_generator_script is current
        print("XRAY_V83_PRECOMPATIBLE_API_STARTUP=PASS")
    finally:
        compat._runtime_applied = old
        compat._original_state_generator_script = old_source
        xray_modern_runtime._state_generator_script = current


if __name__ == "__main__":
    main()
