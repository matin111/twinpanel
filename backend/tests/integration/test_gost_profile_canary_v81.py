from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "app" / "transport_candidates" / "gost.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _assigned_tuple(name: str) -> tuple[str, ...]:
    for node in TREE.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name) or node.target.id != name:
            continue
        if not isinstance(node.value, ast.Tuple):
            raise AssertionError(f"{name} must be a tuple")
        values: list[str] = []
        for item in node.value.elts:
            if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                raise AssertionError(f"{name} must contain only string constants")
            values.append(item.value)
        return tuple(values)
    raise AssertionError(f"missing assignment: {name}")


def main() -> None:
    profiles = _assigned_tuple("PROFILE_ORDER")
    assert profiles == ("relay+wss", "relay+tls"), profiles

    required = (
        "TWINPANEL_GOST_PROFILE_CANARY_V81",
        "for profile in PROFILE_ORDER:",
        "await _reset_profile_runtime(ci, ce, rt)",
        "await _install_profile_services(",
        "health = await probe(",
        '"selected_profile": profile',
        '"profile_canary": "v81"',
        '"profile_attempts": attempts',
        "gost_all_profiles_failed",
        "-L={profile}://:{port}?bind=true",
        "-F={profile}://{exit_public_ip}:{port}?secure=false",
    )
    for token in required:
        assert token in SOURCE, f"missing GOST V81 contract token: {token}"

    # Candidate eligibility must remain fail-closed: an online DB mark can only
    # occur after the common bidirectional L3/TCP/UDP canary is invoked.
    probe_pos = SOURCE.index("health = await probe(")
    online_pos = SOURCE.index('status="online"', probe_pos)
    return_pos = SOURCE.index('"ok": True', online_pos)
    assert probe_pos < online_pos < return_pos

    # The second profile is a retry inside the candidate installer, not a new
    # logical transport. SmartAuto still sees one gost_tun candidate and only
    # receives it after a profile has passed the common probe.
    assert 'name = "gost_tun"' in SOURCE
    assert SOURCE.count('name = "gost_tun"') == 1

    print("GOST_PROFILE_CANARY_V81_CONTRACT_OK")


if __name__ == "__main__":
    main()
