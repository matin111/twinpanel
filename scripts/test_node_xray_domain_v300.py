from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    routed = read("components/routed-page-client-v2.tsx")
    nodes = read("components/legacy-nodes-runtime-v2.tsx")
    api = read("lib/admin-api.ts")
    runtime = read("backend/app/xray_node_domain_runtime.py")

    # TWINPANEL_NODE_XRAY_DOMAIN_UI_V311_REVALIDATED
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
    assert 'TWINPANEL_XRAY_NODE_DOMAIN_RUNTIME_V3' in runtime
    assert 'ADD COLUMN IF NOT EXISTS xray_domain' in runtime
    assert 'node.xray_domain = domain or None' in runtime
    assert 'getattr(node, "public_domain", None)' in runtime

    # The UI must never route the dedicated field through the generic-domain API.
    assert 'updateNodeDomain(selected.id,xrayDomainDraft' not in nodes
    assert 'saveXrayDomain(selected.id,domainDraft' not in nodes

    print("node xray domain v311 revalidation: ok")


if __name__ == "__main__":
    main()
