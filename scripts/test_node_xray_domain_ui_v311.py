from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    routed = read("components/routed-page-client-v2.tsx")
    nodes = read("components/legacy-nodes-runtime-v2.tsx")
    api = read("lib/admin-api.ts")
    runtime = read("backend/app/xray_node_domain_runtime.py")

    assert 'routeKey==="admin/nodes"||routeKey==="admin/network"' in routed
    assert '<LegacyNodesRuntimePage/>' in routed

    # Separate server identities must both be visible and independently mutable.
    assert 'دامنه عمومی' in nodes
    assert 'دامنه اختصاصی Xray / V2Ray' in nodes
    assert 'type NodeModal="manage"|"ssh"|"domain"|"xray-domain"|null' in nodes
    assert 'legacyAdminApi.updateNodeDomain(selected.id,domainDraft.trim())' in nodes
    assert 'adminApi.xrayDomain(selected.id)' in nodes
    assert 'adminApi.saveXrayDomain(selected.id,xrayDomainDraft.trim())' in nodes
    assert 'adminApi.prepareXrayDomain(selected.id,true)' in nodes
    assert 'selectedRole==="exit"' in nodes

    # The two fields must never cross-write each other's API.
    assert 'updateNodeDomain(selected.id,xrayDomainDraft' not in nodes
    assert 'saveXrayDomain(selected.id,domainDraft' not in nodes

    # Active rc.310 backend contract must remain present.
    assert '/v1/xray-modern-admin/nodes/${id}/xray-domain' in api
    assert 'TWINPANEL_XRAY_NODE_DOMAIN_RUNTIME_V3' in runtime
    assert 'node.xray_domain = domain or None' in runtime
    assert 'getattr(node, "public_domain", None)' in runtime

    print("node xray domain ui v311: ok")


if __name__ == "__main__":
    main()
