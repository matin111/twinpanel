from __future__ import annotations

import re
from pathlib import Path


def _pick(output: str, name: str) -> str:
    match = re.search(
        re.escape(name) + r":\s*([0-9a-fA-F]+)\s*$",
        output,
        re.M,
    )
    if not match:
        raise AssertionError(f"missing {name}")
    return match.group(1)


def main() -> None:
    available = "a1" * 64
    master_private = "b2" * 32
    master_public = "c3" * 32

    # Sudoku v0.5.1 emits keygen values through logx.Infof. Its standard
    # logger prefixes every line with time + level + component, so TwinPanel
    # must search for the exact key label anywhere on the line rather than
    # assuming that the label starts at column zero.
    output = "\n".join(
        [
            f"22:19:31 info [CLI] Available Private Key: {available}",
            f"22:19:31 info [CLI] Master Private Key: {master_private}",
            f"22:19:31 info [CLI] Master Public Key:  {master_public}",
        ]
    )

    assert _pick(output, "Available Private Key") == available
    assert _pick(output, "Master Private Key") == master_private
    assert _pick(output, "Master Public Key") == master_public

    root = Path(__file__).resolve().parents[2]
    runtime = (root / "backend" / "app" / "standalone_protocol_runtime.py").read_text(
        encoding="utf-8"
    )
    fixed = 'm=re.search(re.escape(name)+r":\\\\s*([0-9a-fA-F]+)\\\\s*$", out, re.M)'
    stale = 'm=re.search(r"^"+re.escape(name)+r":\\\\s*([0-9a-fA-F]+)\\\\s*$", out, re.M)'
    assert fixed in runtime
    assert stale not in runtime

    print("SUDOKU_KEYGEN_V051_SMOKE_OK")


if __name__ == "__main__":
    main()
