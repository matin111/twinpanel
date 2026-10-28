from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    routed = read("components/routed-page-client-v2.tsx")
    nodes = read("components/legacy-nodes-runtime-v2.tsx")
    api = read("lib/admin-api.ts")
    runtime = read("backend/app/xray_node_domain_runtime.py")

    # /admin/nodes must continue to use the active Node management runtime.
    assert 'routeKey==="admin/nodes"||routeKey==="admin/network"' in routed
    assert '<LegacyNodesRuntimePage/>' in routed

    # Dedicated Xray domain controls belong to Exit server management.
    assert 'type NodeModal="manage"|"ssh"|"domain"|"xray-domain"|null' in nodes
    assert 'adminApi.xrayDomain(selected.id)' in nodes
    assert 'adminApi.saveXrayDomain(selected.id,xrayDomainDraft.trim())' in nodes
    assert 'adminApi.prepareXrayDomain(selected.id,true)' in nodes
    assert 'selectedRole==="exit"' in nodes
    assert 'xray.example.com' in nodes

    # General node domain and Xray TLS identity must remain distinct.
    assert 'legacyAdminApi.updateNodeDomain(selected.id,domainDraft.trim())' in nodes
    assert '/v1/xray-modern-admin/nodes/${id}/xray-domain' in api
    assert 'TWINPANEL_XRAY_NODE_DOMAIN_RUNTIME_V2' in runtime
    assert 'ADD COLUMN IF NOT EXISTS xray_domain' in runtime
    assert 'or xray_modern_admin._clean_domain(' in runtime
    assert 'getattr(node, "public_domain", None)' in runtime

    print("node xray domain v300: ok")


if __name__ == "__main__":
    main()
