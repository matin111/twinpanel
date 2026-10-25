from __future__ import annotations

import base64
import json

from app.singbox_outbound_import import OutboundImportError, parse_outbound_config


def vmess_uri(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return "vmess://" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def test_vless_reality() -> None:
    parsed = parse_outbound_config(
        "vless://11111111-1111-4111-8111-111111111111@edge.example.com:443"
        "?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.example.com"
        "&fp=chrome&pbk=PUBLICKEY&sid=abcd&type=tcp#Germany%20Reality"
    )
    out = parsed.outbound
    assert parsed.source_type == "vless"
    assert parsed.label == "Germany Reality"
    assert out["server"] == "edge.example.com"
    assert out["server_port"] == 443
    assert out["flow"] == "xtls-rprx-vision"
    assert out["tls"]["enabled"] is True
    assert out["tls"]["server_name"] == "www.example.com"
    assert out["tls"]["reality"]["public_key"] == "PUBLICKEY"
    assert out["tls"]["reality"]["short_id"] == "abcd"
    assert out["tls"]["utls"]["fingerprint"] == "chrome"
    assert "transport" not in out


def test_vless_ws_tls() -> None:
    parsed = parse_outbound_config(
        "vless://22222222-2222-4222-8222-222222222222@cdn.example.com:443"
        "?security=tls&sni=origin.example.com&type=ws&host=origin.example.com&path=%2Fws#WS"
    )
    out = parsed.outbound
    assert out["tls"]["server_name"] == "origin.example.com"
    assert out["transport"] == {
        "type": "ws",
        "path": "/ws",
        "headers": {"Host": "origin.example.com"},
    }


def test_vmess_ws_tls() -> None:
    parsed = parse_outbound_config(
        vmess_uri(
            {
                "v": "2",
                "ps": "VMess CDN",
                "add": "vmess.example.com",
                "port": "443",
                "id": "33333333-3333-4333-8333-333333333333",
                "aid": "0",
                "scy": "auto",
                "net": "ws",
                "host": "cdn.example.com",
                "path": "/ray",
                "tls": "tls",
                "sni": "cdn.example.com",
                "fp": "chrome",
            }
        )
    )
    out = parsed.outbound
    assert parsed.source_type == "vmess"
    assert parsed.label == "VMess CDN"
    assert out["security"] == "auto"
    assert out["server_port"] == 443
    assert out["tls"]["server_name"] == "cdn.example.com"
    assert out["transport"]["type"] == "ws"
    assert out["transport"]["path"] == "/ray"
    assert out["transport"]["headers"]["Host"] == "cdn.example.com"


def test_trojan_grpc_tls() -> None:
    parsed = parse_outbound_config(
        "trojan://super-secret@trojan.example.com:443"
        "?security=tls&sni=front.example.com&type=grpc&serviceName=grpc-service#Trojan"
    )
    out = parsed.outbound
    assert parsed.source_type == "trojan"
    assert out["password"] == "super-secret"
    assert out["tls"]["server_name"] == "front.example.com"
    assert out["transport"] == {"type": "grpc", "service_name": "grpc-service"}


def test_shadowsocks_sip002() -> None:
    userinfo = base64.urlsafe_b64encode(b"aes-256-gcm:secret-pass").decode().rstrip("=")
    parsed = parse_outbound_config(
        f"ss://{userinfo}@1.2.3.4:8388?plugin=v2ray-plugin%3Btls%3Bhost%3Dcdn.example.com#SS%20Exit"
    )
    out = parsed.outbound
    assert parsed.source_type == "shadowsocks"
    assert parsed.label == "SS Exit"
    assert out["server"] == "1.2.3.4"
    assert out["server_port"] == 8388
    assert out["method"] == "aes-256-gcm"
    assert out["password"] == "secret-pass"
    assert out["plugin"] == "v2ray-plugin"
    assert out["plugin_opts"] == "tls;host=cdn.example.com"


def test_raw_singbox_outbound_json() -> None:
    parsed = parse_outbound_config(
        json.dumps(
            {
                "type": "vless",
                "tag": "old-name",
                "server": "json.example.com",
                "server_port": 443,
                "uuid": "44444444-4444-4444-8444-444444444444",
                "tls": {"enabled": True, "server_name": "json.example.com"},
            }
        )
    )
    assert parsed.label == "old-name"
    assert parsed.outbound["type"] == "vless"
    assert "tag" not in parsed.outbound


def test_full_singbox_config_requires_one_importable_outbound() -> None:
    parsed = parse_outbound_config(
        json.dumps(
            {
                "outbounds": [
                    {"type": "direct", "tag": "direct"},
                    {
                        "type": "trojan",
                        "tag": "remote",
                        "server": "remote.example.com",
                        "server_port": 443,
                        "password": "secret",
                        "tls": {"enabled": True},
                    },
                ]
            }
        )
    )
    assert parsed.source_type == "trojan"
    assert parsed.label == "remote"


def test_invalid_inputs_fail_closed() -> None:
    for value in (
        "",
        "socks://127.0.0.1:1080",
        "vless://missing-port@example.com",
        '{"type":"wireguard","server":"x","server_port":1}',
    ):
        try:
            parse_outbound_config(value)
        except OutboundImportError:
            pass
        else:
            raise AssertionError(f"expected OutboundImportError for {value!r}")


def main() -> None:
    tests = [
        test_vless_reality,
        test_vless_ws_tls,
        test_vmess_ws_tls,
        test_trojan_grpc_tls,
        test_shadowsocks_sip002,
        test_raw_singbox_outbound_json,
        test_full_singbox_config_requires_one_importable_outbound,
        test_invalid_inputs_fail_closed,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS total={len(tests)}")


if __name__ == "__main__":
    main()
