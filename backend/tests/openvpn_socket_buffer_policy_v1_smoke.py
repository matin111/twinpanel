from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
provision = (ROOT / "app" / "routers" / "provision.py").read_text()
headroom = (ROOT / "app" / "openvpn_fork_headroom_v101.py").read_text()

openvpn_section = provision.split("async def install_openvpn", 1)[1]
template = openvpn_section.split("config = f'''", 1)[1].split("'''", 1)[0]
assert "rcvbuf 4194304" in template
assert "sndbuf 4194304" in template
assert "net.core.rmem_max" in provision
assert "net.core.wmem_max" in provision
assert "99-twinpanel-openvpn-buffer.conf" in provision
assert 'test "$RMAX" -ge 16777216 || RMAX=16777216' in provision
assert 'test "$WMAX" -ge 16777216 || WMAX=16777216' in provision

# The existing hook reconciler must preserve unrelated OpenVPN directives.
assert 'awk -v hook="$HOOK"' in headroom
assert '{{ print }}' in headroom
assert 'install -o root -g root -m 0644 "$CFG_TMP" "$CONFIG"' in headroom

print("OPENVPN_SOCKET_BUFFER_POLICY_V1_OK")
