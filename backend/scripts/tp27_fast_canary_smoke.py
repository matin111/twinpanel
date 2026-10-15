from __future__ import annotations

import os
import subprocess
import tempfile

from app.transport_candidates import gre


def _check_helper(mode: str, fou_port: int | None) -> None:
    text = gre._helper_text(
        interface="tpgr5",
        local_public="192.0.2.10",
        remote_public="198.51.100.20",
        local_addr="10.248.0.21/30",
        peer_ip="10.248.0.22",
        gre_key=123456,
        mode=mode,
        fou_port=fou_port,
        role="iran",
        mtu=1400,
    )

    # Safety / ownership guarantees.
    assert "iptables -F" not in text
    assert "net.ipv4.conf.all.rp_filter" not in text
    assert 'ip link del "$IFACE"' in text
    assert 'txqueuelen "$TXQLEN"' in text
    assert 'ip addr flush dev "$IFACE" scope global' in text

    # TP27 Core parity: dedicated INPUT/OUTPUT/FORWARD hooks rather than only
    # an inbound listener rule.
    assert "ensure_chain_hook INPUT" in text
    assert "ensure_chain_hook OUTPUT" in text
    assert "ensure_chain_hook FORWARD" in text
    assert 'ensure_rule "$CHAIN_IN" -i "$IFACE" -j ACCEPT' in text
    assert 'ensure_rule "$CHAIN_OUT" -o "$IFACE" -j ACCEPT' in text
    assert 'ensure_rule "$CHAIN_FWD" -i "$IFACE" -j ACCEPT' in text
    assert 'ensure_rule "$CHAIN_FWD" -o "$IFACE" -j ACCEPT' in text

    # Same kernel data-plane family as tp27-core.
    assert "TP27_CORE_READY" in text
    assert 'ip tunnel add "$IFACE" mode gre' in text
    assert "encap fou" in text
    assert "ip fou add port" in text

    # TP27 Core keepalive treats RX progress as health even if ICMP is
    # transiently filtered.
    assert "/statistics/rx_bytes" in text
    assert 'PING_OK=0' in text
    assert '"$RX_NOW" -gt "$LAST_RX"' in text

    expected_mode = f"MODE={mode}"
    assert expected_mode in text

    if mode == "gre-fou":
        assert f"FOU_PORT={int(fou_port or 0)}" in text
        assert '--sport "$FOU_PORT" --dport "$FOU_PORT"' in text
    else:
        assert "FOU_PORT=0" in text
        assert '-p 47 -s "$REMOTE_PUBLIC/32" -d "$LOCAL_PUBLIC/32"' in text

    fd, path = tempfile.mkstemp(prefix="tp27-core-parity-", suffix=".sh")
    try:
        os.write(fd, text.encode())
        os.close(fd)
        subprocess.run(["bash", "-n", path], check=True)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def main() -> None:
    assert gre.DEFAULT_MTU == 1400
    assert gre.TXQUEUELEN == 1000
    assert gre.KEEPALIVE_INTERVAL == 5
    assert gre.KEEPALIVE_FAILURES == 4
    assert gre.FOU_PORT_CANDIDATES == (443, 8443, 2053, 2083, 10443)

    key1 = gre._gre_key(5, "193.39.9.222", "198.105.115.180")
    key2 = gre._gre_key(5, "193.39.9.222", "198.105.115.180")
    assert key1 == key2
    assert 1 <= key1 <= 0xFFFFFFFF

    _check_helper("gre", None)
    _check_helper("gre-fou", 8443)

    print("TP27_CORE_PARITY_SMOKE_OK")


if __name__ == "__main__":
    main()
