from __future__ import annotations

import base64
import shlex
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "backend" / "app" / "standalone_subscription_accounts.py"


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    try:
        apply_section = source.split("async def _apply_amneziawg", 1)[1].split(
            "async def _remove_amneziawg", 1
        )[0]
    except IndexError:
        fail("AMNEZIAWG_APPLY_SECTION_NOT_FOUND")

    if "awk -F'='" in apply_section:
        fail("UNSAFE_AWG_EQUALS_FIELD_SPLIT_STILL_PRESENT")

    sed_expression = (
        "s/^[[:space:]]*PrivateKey[[:space:]]*=[[:space:]]*//p"
    )
    if sed_expression not in apply_section:
        fail("SAFE_AWG_PRIVATE_KEY_EXTRACTION_NOT_FOUND")

    private_key = base64.b64encode(bytes(range(32))).decode("ascii")
    if len(private_key) != 44 or not private_key.endswith("="):
        fail("TEST_FIXTURE_IS_NOT_PADDED_WIREGUARD_KEY")

    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "tpawg0.conf"
        config.write_text(
            "[Interface]\n"
            "Address = 10.254.0.1/16\n"
            f"PrivateKey = {private_key}\n"
            "ListenPort = 51820\n",
            encoding="utf-8",
        )

        command = (
            "sed -nE "
            + shlex.quote(sed_expression)
            + " "
            + shlex.quote(str(config))
            + " | head -n1"
        )
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        if result.returncode != 0:
            fail("SAFE_AWG_PRIVATE_KEY_EXTRACTION_COMMAND_FAILED")

        extracted = result.stdout.strip()
        if extracted != private_key:
            fail(
                "AWG_PRIVATE_KEY_PADDING_NOT_PRESERVED:"
                f" expected_len={len(private_key)} got_len={len(extracted)}"
            )

        try:
            decoded = base64.b64decode(extracted, validate=True)
        except Exception as exc:
            fail(f"EXTRACTED_AWG_PRIVATE_KEY_INVALID_BASE64:{exc}")

        if len(decoded) != 32:
            fail(f"EXTRACTED_AWG_PRIVATE_KEY_WRONG_BYTES:{len(decoded)}")

    print("AMNEZIAWG_KEY_PADDING_V217_SMOKE=PASS")
    print("PADDED_KEY_LENGTH=44")
    print("DECODED_KEY_BYTES=32")
    print("UNSAFE_EQUALS_SPLIT=ABSENT")


if __name__ == "__main__":
    main()
