"""Public Connection uses recent measured tunnel RTT and verified logo assets.

No client-side probes or fake ping numbers; no VPN endpoint or config mutations.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import pytest

ROOT=Path(__file__).resolve().parents[1]/"app"/"routers"


def test_real_node_latency_is_read_only_recent_and_scoped():
    hub=(ROOT/"public_connection_hub_v5.py").read_text(encoding="utf-8")
    compile(hub,"hub_v5","exec")
    assert "def _recent_node_latency(db: Session, payload: dict[str, Any]) -> dict[int, int]:" in hub
    assert "TunnelPeerState.node_id.in_(ids)" in hub
    assert "TunnelPeerState.updated_at >= cutoff" in hub
    assert "TunnelPeerState.tunnel_reachable.is_(True)" in hub
    assert "TunnelPeerState.latency_ms.isnot(None)" in hub
    assert "cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=2)" in hub
    assert "0 < int(latency) <= 30000" in hub
    assert "measured_latency = _recent_node_latency(db, safe_payload)" in hub
    assert 'latency_attr = f\' data-latency-ms="{int(latency)}"\'' in hub
    assert "latency_by_node: dict[int, int] | None = None" in hub
    assert "db.commit(" not in hub


def test_ui_displays_real_rtt_only_and_labels_tunnel_not_client_ping():
    ui=(ROOT/"public_connection_reference_desktop_mobile_v67.py").read_text(encoding="utf-8")
    compile(ui,"reference_v67","exec")
    assert "const latency=tab.dataset.latencyMs||views[i]?.dataset.latencyMs||'';" in ui
    assert "if(tab.dataset.latencyMs&&Number.isFinite(rtt)&&rtt>0)" in ui
    assert "badge.textContent=rtt+' ms'" in ui
    assert "تأخیر واقعی مسیر تونل" in ui
    assert "پینگ مستقیم گوشی کاربر" in ui
    assert "https://cdn.simpleicons.org/" in ui
    for protocol in ("openvpn","wireguard","cisco"):
        assert protocol in ui
    assert "img.addEventListener('load',()=>icon.replaceChildren(img))" in ui


def test_javascript_syntax_valid():
    node=shutil.which("node")
    if not node:pytest.skip("Node unavailable")
    ui=(ROOT/"public_connection_reference_desktop_mobile_v67.py").read_text(encoding="utf-8")
    script=ui.split('<script id="twinpanelPublicConnectionReferenceV67">',1)[1].split("</script>",1)[0]
    with tempfile.TemporaryDirectory() as temp:
        f=Path(temp)/"v67.js"
        f.write_text(script,encoding="utf-8")
        subprocess.run([node,"--check",str(f)],check=True,capture_output=True,text=True)
