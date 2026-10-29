from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V35 = ROOT / "backend/app/routers/public_connection_manual_credentials_v35.py"
V34 = ROOT / "backend/app/routers/public_connection_forward_v34.py"
V37 = ROOT / "backend/app/routers/public_connection_final_presentation_v37.py"
V26 = ROOT / "backend/app/routers/public_connection_canonical_mobile_v26.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    v35 = V35.read_text(encoding="utf-8")
    v34 = V34.read_text(encoding="utf-8")
    v37 = V37.read_text(encoding="utf-8")
    v26 = V26.read_text(encoding="utf-8")

    require(
        "TWINPANEL_PUBLIC_CONNECT_MANUAL_CREDENTIALS_V35" in v35,
        "V35 marker missing",
    )
    require(
        "const MANUAL=new Set(['cisco','l2tp']);" in v35,
        "V35 must be scoped only to Cisco/L2TP",
    )
    require(
        "cisco:['username','password']" in v35,
        "Cisco shared credential contract missing",
    )
    require(
        "l2tp:['username','password','secret']" in v35,
        "L2TP shared credential contract missing",
    )

    # Never hoist a credential merely because the label exists. Every server
    # must expose the same non-empty value before it becomes protocol-level UI.
    require("records.some(record=>!record)" in v35, "missing all-server presence gate")
    require("records.every(record=>record.value===first)" in v35, "missing identical-value gate")
    require("data-v35-shared-credential" in v35, "per-server shared credential hide contract missing")
    require("مشترک برای همه سرورها" in v35, "shared credential explanatory label missing")
    require(
        "کپی نام کاربری" in v35 and "کپی رمز عبور" in v35 and "کپی Secret" in v35,
        "explicit manual credential copy actions missing",
    )

    # V35 remains preparatory. V34 still builds protocol actions after it, while
    # V37 is now the final presentation authority and must not mutate credentials.
    v35_call = v26.find("source = refine_public_connection_manual_credentials_v35(source)")
    v34_call = v26.find("source = refine_public_connection_forward_v34(source)")
    v37_return = v26.find("return refine_public_connection_final_presentation_v37(source)")
    require(v35_call >= 0, "V35 is not wired into V26")
    require(v34_call > v35_call, "V34 action builder must execute after V35")
    require(v37_return > v34_call, "V37 final presentation must execute after V34")
    require("TWINPANEL_PUBLIC_CONNECT_FORWARD_V34" in v34, "V34 action authority missing")
    require("TWINPANEL_PUBLIC_CONNECT_FINAL_PRESENTATION_V37" in v37, "V37 final authority missing")

    # No backend/provisioning/accounting mutations belong in these presentation fixes.
    forbidden = (
        "db.add(", "db.delete(", "db.commit(", "iptables", "nft ", "systemctl", "provision", "quota",
    )
    require(all(token not in v35 for token in forbidden), "V35 escaped presentation scope")
    require(all(token not in v37 for token in forbidden), "V37 escaped presentation scope")

    print("PUBLIC_CONNECT_MANUAL_CREDENTIALS_V35_SMOKE=PASS")


if __name__ == "__main__":
    main()
