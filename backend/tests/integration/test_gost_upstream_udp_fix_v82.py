from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "app" / "transport_candidates" / "gost.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _assigned_string(name: str) -> str:
    for node in TREE.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
                    raise AssertionError(f"{name} must be a string constant")
                return node.value.value
    raise AssertionError(f"missing assignment: {name}")


def main() -> None:
    assert _assigned_string("VERSION") == "3.3.1-nightly.20261017"
    assert _assigned_string("UPSTREAM_ISSUE") == "go-gost/gost#911"
    assert (
        _assigned_string("UPSTREAM_FIX_COMMIT")
        == "bc137fbd832276f2a8631c7320df3e3adaa1ddf0"
    )
    assert (
        _assigned_string("UPSTREAM_E2E_COMMIT")
        == "d7656ef3deafec6bf97107b20a332b938153fd54"
    )
    assert _assigned_string("UPSTREAM_X_VERSION") == "v0.19.5"

    required = (
        "TWINPANEL_GOST_UPSTREAM_UDP_FRAME_FIX_V82",
        "gost_checksum_missing",
        "gost_checksum_mismatch",
        '"profile_canary": "v81"',
        '"upstream_binary_fix": "v82"',
        '"upstream_issue": UPSTREAM_ISSUE',
        '"upstream_fix_commit": UPSTREAM_FIX_COMMIT',
        '"upstream_e2e_commit": UPSTREAM_E2E_COMMIT',
        '"upstream_x_version": UPSTREAM_X_VERSION',
        "for profile in PROFILE_ORDER:",
        "health = await probe(",
        'status="online"',
        "gost_all_profiles_failed",
    )
    for token in required:
        assert token in SOURCE, f"missing GOST V82 contract token: {token}"

    # The upstream-fixed binary remains fail-closed. Candidate online status can
    # only be written after the common real data-plane probe has returned.
    probe_pos = SOURCE.index("health = await probe(")
    online_pos = SOURCE.index('status="online"', probe_pos)
    assert probe_pos < online_pos

    # We deliberately pin an exact official prerelease instead of tracking a
    # moving nightly alias. This keeps the downloaded artifact reproducible.
    version = _assigned_string("VERSION")
    assert "nightly.20261017" in version
    assert "latest" not in version.lower()

    print("GOST_UPSTREAM_UDP_FIX_V82_CONTRACT_OK")


if __name__ == "__main__":
    main()
