from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_mother_identity_is_not_bound_to_mutable_name() -> None:
    source = _source("backend/app/routers/mother_access.py")
    local_core = _source("backend/app/local_core_runtime.py")

    assert 'Node.agent_url == "local://core"' in source
    assert 'Node.agent_url == LOCAL_AGENT_URL' in local_core
    assert 'Node.name == "TwinPanel Local Core"' not in source


def test_mother_name_and_public_domain_are_editable() -> None:
    source = _source("backend/app/routers/mother_access.py")

    assert "mother_name: str | None = None" in source
    assert "public_domain: str | None = None" in source
    assert "mother.name = name" in source
    assert "mother.public_domain = _normalize_public_domain(payload.public_domain) or None" in source
    assert '"mother_public_domain"' in source
    assert '"mother_public_ip"' in source


def test_mother_admin_ui_exposes_name_and_domain_fields() -> None:
    source = _source("components/mother-access-runtime-v2.tsx")
    api = _source("lib/admin-parity-api.ts")

    assert "نام سرور مادر" in source
    assert "دامنه عمومی" in source
    assert "mother_public_domain" in source
    assert "mother_name" in source
    assert "mother_name?:string" in api
    assert "public_domain?:string" in api
