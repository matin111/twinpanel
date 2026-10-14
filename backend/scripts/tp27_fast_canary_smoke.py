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

    assert "iptables -F" not in text
    assert "net.ipv4.conf.all.rp_filter" not in text
    assert 'ip link del "$IFACE"' in text
    assert 'txqueuelen "$TXQLEN"' in text
    assert "TP27_FAST_READY" in text

    if mode == "gre-fou":
        assert "encap fou" in text
        assert "ip fou add port" in text
        assert str(fou_port) in text
    else:
        assert 'ip tunnel add "$IFACE" mode gre' in text
        assert "encap fou" not in text

    fd, path = tempfile.mkstemp(prefix="tp27-fast-", suffix=".sh")
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
    assert gre.FOU_PORT_CANDIDATES == (443, 8443, 2053, 2083, 10443)

    key1 = gre._gre_key(5, "193.39.9.222", "198.105.115.180")
    key2 = gre._gre_key(5, "193.39.9.222", "198.105.115.180")
    assert key1 == key2
    assert 1 <= key1 <= 0xFFFFFFFF

    _check_helper("gre", None)
    _check_helper("gre-fou", 8443)

    print("TP27_FAST_CANARY_SMOKE_OK")


if __name__ == "__main__":
    main()
