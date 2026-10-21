from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "components" / "protocol-command-center.tsx"


def require(block: str, needle: str) -> None:
    if needle not in block:
        raise SystemExit(f"missing bulk sync UI contract: {needle}")


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("const modernSyncAll=async()=>{")
    end = source.index("const modernHealth=async", start)
    bulk = source[start:end]

    require(bulk, "node.protocols.filter(row=>row.installable")
    require(bulk, "const protocols=rows.map(row=>row.protocol)")
    require(bulk, "const ports=Object.fromEntries")
    require(bulk, "const profiles=Object.fromEntries")
    require(bulk, "modernRequest<ModernInstallResult>")
    require(bulk, "/v1/settings/vpn/modern-protocols/${node.id}/install")
    require(bulk, "JSON.stringify({protocols,ports,profiles})")
    require(bulk, "result.failed_protocols")
    require(bulk, "result.protocols?.[row.protocol]?.ok===false")
    require(bulk, "await load(true)")
    require(bulk, "setError(message)")

    require(source, 'onClick={()=>void modernSyncAll()}')
    require(source, '"همگام‌سازی همه پروتکل‌های مدرن"')
    require(source, '"Sync all modern protocols"')

    print("MODERN_PROTOCOL_BULK_SYNC_UI_SMOKE=PASS")


if __name__ == "__main__":
    main()
