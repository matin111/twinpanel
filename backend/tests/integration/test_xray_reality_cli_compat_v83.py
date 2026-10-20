from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from app import xray_modern_runtime
from app.xray_reality_cli_compat_v83 import (
    apply_xray_reality_cli_compat_v83,
)


# TWINPANEL_XRAY_REALITY_CLI_COMPAT_V83_REGRESSION
#
# This is intentionally an executable generated-script regression, not a
# source-string smoke. It runs the exact state generator used on Exit/local-core
# nodes against fake xray binaries which reproduce historical and current
# upstream x25519 CLI output formats.


def _run_generated_state(
    xray_output: str,
    *,
    existing_state: dict | None = None,
) -> dict:
    with tempfile.TemporaryDirectory(prefix="tp-xray-v83-") as raw_tmp:
        root = Path(raw_tmp)
        fake_xray = root / "xray"
        state_path = root / "twinpanel-modern-state.json"

        fake_xray.write_text(
            "#!/usr/bin/env python3\n"
            f"print({xray_output!r})\n",
            encoding="utf-8",
        )
        os.chmod(fake_xray, 0o755)

        if existing_state is not None:
            state_path.write_text(
                json.dumps(existing_state),
                encoding="utf-8",
            )

        script = xray_modern_runtime._state_generator_script("")

        binary_marker = '"/usr/local/bin/xray"'
        state_marker = '"/usr/local/etc/xray/twinpanel-modern-state.json"'
        assert script.count(binary_marker) == 2, "unexpected xray binary contract"
        assert script.count(state_marker) == 1, "unexpected state path contract"

        script = script.replace(binary_marker, repr(str(fake_xray)))
        script = script.replace(state_marker, repr(str(state_path)))

        result = subprocess.run(
            [sys.executable, "-c", script],
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )

        if result.returncode != 0:
            raise AssertionError(
                "generated Xray state script failed\n"
                f"stdout={result.stdout}\n"
                f"stderr={result.stderr}"
            )

        line = result.stdout.strip().splitlines()[-1]
        payload = json.loads(line)
        persisted = json.loads(state_path.read_text(encoding="utf-8"))
        assert payload == persisted
        return payload


def main() -> None:
    apply_xray_reality_cli_compat_v83()

    cases = [
        (
            "legacy-public-key",
            "Private key: private-old\nPublic key: public-old",
            "private-old",
            "public-old",
        ),
        (
            "password-2025",
            "PrivateKey: private-password\nPassword: public-password\nHash32: ignored",
            "private-password",
            "public-password",
        ),
        (
            "password-publickey-2026",
            "PrivateKey: private-current\nPassword (PublicKey): public-current\nHash32: ignored",
            "private-current",
            "public-current",
        ),
    ]

    for name, output, expected_private, expected_public in cases:
        state = _run_generated_state(output)
        assert state["reality_private_key"] == expected_private, (name, state)
        assert state["reality_password"] == expected_public, (name, state)

    # Existing installations commonly already have a private key. Verify the
    # `xray x25519 -i PRIVATE` derivation path also accepts the current upstream
    # combined label and preserves the existing private key.
    derived = _run_generated_state(
        "Password (PublicKey): derived-current\nHash32: ignored",
        existing_state={"reality_private_key": "persisted-private"},
    )
    assert derived["reality_private_key"] == "persisted-private", derived
    assert derived["reality_password"] == "derived-current", derived

    print(
        "XRAY_REALITY_CLI_COMPAT_V83_EXECUTABLE_REGRESSION_OK "
        "legacy_public_key=1 password=1 password_public_key=1 derivation=1"
    )


if __name__ == "__main__":
    main()
