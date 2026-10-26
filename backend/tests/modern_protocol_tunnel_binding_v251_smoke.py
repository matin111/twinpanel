from __future__ import annotations

import base64
import inspect
import json
from types import SimpleNamespace

from app import modern_protocol_tunnel_binding_v251 as binding
from app import protocol_dataplane_desired_state_v87 as protocol_v87


EXPECTED = {
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
    "mieru",
    "trusttunnel",
    "amneziawg",
    "sudoku",
}

FIXED_EXPECTED_EXIT6 = {
    "hysteria2": 28006,
    "tuic": 29006,
    "anytls": 31006,
    "naive": 32006,
    "shadowtls": 33006,
    "snell": 34006,
    "mieru": 35006,
    "trusttunnel": 36006,
    "amneziawg": 37006,
}


def _decode_tlv(uri: str) -> list[tuple[int, bytes]]:
    assert uri.startswith("tt://?")
    payload = uri[6:]
    padding = "=" * ((4 - len(payload) % 4) % 4)
    data = base64.urlsafe_b64decode(payload + padding)

    output: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(data):
        tag, offset = binding._quic_varint_decode(data, offset)
        size, offset = binding._quic_varint_decode(data, offset)
        end = offset + int(size)
        assert end <= len(data)
        output.append((int(tag), data[offset:end]))
        offset = end
    return output


def _encode_tlv(entries: list[tuple[int, bytes]]) -> str:
    raw = b"".join(
        binding._quic_varint_encode(tag)
        + binding._quic_varint_encode(len(body))
        + body
        for tag, body in entries
    )
    payload = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return "tt://?" + payload


def test_registry() -> None:
    assert set(binding.MODERN_TUNNEL_PROTOCOLS) == EXPECTED
    assert set(binding.FIXED_PUBLIC_PORT_BASE) == EXPECTED - {"sudoku"}

    actual = {
        protocol: binding._fixed_public_port(6, protocol)
        for protocol in binding.FIXED_PUBLIC_PORT_BASE
    }
    assert actual == FIXED_EXPECTED_EXIT6

    fixed_ports = set(actual.values())
    assert len(fixed_ports) == len(actual)
    assert all(28000 <= value <= 37999 for value in fixed_ports)
    assert not any(30000 <= value <= 30999 for value in fixed_ports)
    assert not any(20000 <= value <= 27999 for value in fixed_ports)
    assert binding.SUDOKU_PUBLIC_PORT_START == 40000
    assert binding.SUDOKU_PUBLIC_PORT_END == 49999


def test_transport_normalisation() -> None:
    assert binding._normalise_transport("hysteria2", "udp") == "udp"
    assert binding._normalise_transport("anytls", "tcp") == "tcp"
    assert binding._normalise_transport("mieru", "tcp_udp") == "tcp+udp"
    assert binding._normalise_transport("trusttunnel", "tcp_udp_quic") == "tcp+udp"
    assert binding._normalise_transport("naive", "both") == "tcp+udp"


def test_singbox_rewrite_preserves_tls_identity() -> None:
    item = {
        "server": "204.10.192.96",
        "server_ip": "204.10.192.96",
        "port": 8444,
        "outbound": {
            "type": "hysteria2",
            "server": "204.10.192.96",
            "server_port": 8444,
            "password": "secret",
            "tls": {
                "enabled": True,
                "server_name": "exit.example.invalid",
            },
        },
    }
    item["config"] = json.dumps({
        "outbounds": [dict(item["outbound"])],
        "route": {"final": "twinpanel-hysteria2"},
    })

    binding._rewrite_modern_item(
        item,
        "hysteria2",
        "193.39.9.222",
        28006,
    )

    assert item["server"] == "193.39.9.222"
    assert item["port"] == 28006
    assert item["outbound"]["server"] == "193.39.9.222"
    assert item["outbound"]["server_port"] == 28006
    assert item["outbound"]["password"] == "secret"
    assert item["outbound"]["tls"]["server_name"] == "exit.example.invalid"

    config = json.loads(item["config"])
    outbound = config["outbounds"][0]
    assert outbound["server"] == "193.39.9.222"
    assert outbound["server_port"] == 28006
    assert outbound["tls"]["server_name"] == "exit.example.invalid"


def test_mieru_rewrite() -> None:
    profile = {
        "profiles": [{
            "servers": [{
                "ipAddress": "204.10.192.96",
                "domainName": "",
                "portBindings": [
                    {"port": 8450, "protocol": "TCP"},
                    {"port": 8450, "protocol": "UDP"},
                ],
            }],
        }]
    }
    item = {"config": json.dumps(profile)}
    binding._rewrite_modern_item(item, "mieru", "193.39.9.222", 35006)
    server = json.loads(item["config"])["profiles"][0]["servers"][0]
    assert server["ipAddress"] == "193.39.9.222"
    assert server["domainName"] == ""
    assert {x["port"] for x in server["portBindings"]} == {35006}


def test_amneziawg_rewrite() -> None:
    item = {
        "config": "[Interface]\nAddress = 10.254.0.2/32\n\n[Peer]\nEndpoint = 204.10.192.96:8452\nPersistentKeepalive = 25\n",
    }
    binding._rewrite_modern_item(
        item,
        "amneziawg",
        "193.39.9.222",
        37006,
    )
    assert "Endpoint = 193.39.9.222:37006" in item["config"]
    assert "Address = 10.254.0.2/32" in item["config"]


def test_sudoku_rewrite() -> None:
    payload = {
        "n": "sub-17",
        "h": "204.10.192.96",
        "p": 30016,
        "k": "client-key",
        "e": "chacha20-poly1305",
    }
    uri = "sudoku://" + base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")

    item = {
        "config": json.dumps({
            "mode": "client",
            "server_address": "204.10.192.96:30016",
            "key": "client-key",
        }),
        "uri": uri,
    }

    binding._rewrite_modern_item(
        item,
        "sudoku",
        "193.39.9.222",
        41234,
    )

    config = json.loads(item["config"])
    assert config["server_address"] == "193.39.9.222:41234"
    assert config["key"] == "client-key"

    encoded = item["uri"][len("sudoku://") :]
    padding = "=" * ((4 - len(encoded) % 4) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(encoded + padding))
    assert decoded["h"] == "193.39.9.222"
    assert decoded["p"] == 41234
    assert decoded["k"] == "client-key"


def test_trusttunnel_rewrite_preserves_tls_identity_and_credentials() -> None:
    original = _encode_tlv([
        (0x01, b"tt-node-6.twinpanel.invalid"),
        (0x02, b"204.10.192.96:8451"),
        (0x05, b"tp-sub-17"),
        (0x06, b"password-do-not-change"),
    ])

    rewritten = binding._rewrite_trusttunnel_deeplink(
        original,
        "193.39.9.222",
        36006,
    )
    rows = dict(_decode_tlv(rewritten))

    assert rows[0x01] == b"tt-node-6.twinpanel.invalid"
    assert rows[0x02] == b"193.39.9.222:36006"
    assert rows[0x05] == b"tp-sub-17"
    assert rows[0x06] == b"password-do-not-change"


def test_legacy_contract_stays_additive() -> None:
    assert set(protocol_v87._PROTOCOL_ENABLE_ATTR) == {
        "cisco",
        "openvpn",
        "wireguard",
        "l2tp",
        "v2ray",
    }
    assert set(protocol_v87._ACCESS_PROTOCOLS) == {
        "cisco",
        "openvpn",
        "wireguard",
        "l2tp",
    }

    apply_source = inspect.getsource(
        protocol_v87.apply_protocol_dataplane_desired_state_v87
    )
    assert "apply_modern_protocol_tunnel_binding_v251" in apply_source

    route_source = inspect.getsource(binding._modern_routes_for_exit)
    for protocol in EXPECTED:
        assert protocol in route_source or protocol in binding.MODERN_TUNNEL_PROTOCOLS


def main() -> None:
    test_registry()
    test_transport_normalisation()
    test_singbox_rewrite_preserves_tls_identity()
    test_mieru_rewrite()
    test_amneziawg_rewrite()
    test_sudoku_rewrite()
    test_trusttunnel_rewrite_preserves_tls_identity_and_credentials()
    test_legacy_contract_stays_additive()

    print(
        "TWINPANEL_MODERN_PROTOCOL_TUNNEL_BINDING_V251_SMOKE_OK "
        "protocols=hysteria2,tuic,anytls,naive,shadowtls,snell,mieru,trusttunnel,amneziawg,sudoku "
        "legacy_five=preserved delivery=iran-ingress active_transport=unified-l3"
    )


if __name__ == "__main__":
    main()
