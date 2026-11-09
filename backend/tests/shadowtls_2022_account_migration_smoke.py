"""Regression: live account add/revoke and client switch only on opt-in modern listener."""
from __future__ import annotations

import base64
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import secrets
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from app import singbox_subscription_accounts as accounts
from app.services.shadowtls_2022_identity_v1 import (
    NEW_INNER_TAG, NEW_OUTER_TAG,
    stage_parallel_identity_inbounds, user_inner_key,
)


def execute(script: str) -> None:
    output = io.StringIO()
    with redirect_stdout(output):
        try:
            exec(compile(script, "<isolated-node-mutation>", "exec"), {})
        except SystemExit as exc:
            if exc.code not in (0, None):
                raise
    if output.getvalue().strip().endswith("account_unchanged=1"):
        return


def test():
    outer_pass = secrets.token_urlsafe(32)
    server_key = base64.b64encode(secrets.token_bytes(16)).decode()
    private_seed = base64.b64encode(secrets.token_bytes(32)).decode()
    legacy_config = {
        "inbounds": [
            {"type": "shadowtls", "tag": "twinpanel-shadowtls-in",
             "version": 3, "listen": "0.0.0.0", "listen_port": 8448,
             "users": [{"name": "tp-sub-17", "password": outer_pass}],
             "handshake": {"server": "www.microsoft.com", "server_port": 443},
             "detour": "twinpanel-shadowtls-inner"},
            {"type": "shadowsocks", "tag": "twinpanel-shadowtls-inner",
             "listen": "127.0.0.1", "method": "aes-256-gcm",
             "password": secrets.token_urlsafe(32)},
        ],
        "outbounds": [{"type": "direct", "tag": "direct"}],
    }
    staged = stage_parallel_identity_inbounds(
        legacy_config, listen_port=18448, server_key=server_key, derivation_secret=private_seed
    )
    with tempfile.TemporaryDirectory(prefix="tp-shadowtls-sync-") as td:
        config = Path(td) / "config.json"
        state = Path(td) / "state.json"
        config.write_text(json.dumps(staged))
        state.write_text(json.dumps({
            "shadowtls": {"inner_password": legacy_config["inbounds"][1]["password"]},
            "shadowtls_identity2022": {
                "delivery_enabled": True, "advertised_port": 18448,
                "derivation_secret": private_seed
            },
        }))
        with (
            patch.object(accounts, "CONFIG_PATH", str(config)),
            patch.object(accounts, "STATE_PATH", str(state)),
        ):
            # A fresh customer is mirrored into both outer user lists and
            # the uniquely keyed 2022 inner, in one config update.
            password_b = secrets.token_urlsafe(32)
            updated = accounts._mutation_script(
                "shadowtls", "tp-sub-18",
                {"name": "tp-sub-18", "password": password_b},
            )
            execute(updated)
            Path(str(config) + ".account-new").replace(config)
            document = json.loads(config.read_text())
            legacy_outer = next(x for x in document["inbounds"] if x["tag"] == "twinpanel-shadowtls-in")
            modern_outer = next(x for x in document["inbounds"] if x["tag"] == NEW_OUTER_TAG)
            modern_inner = next(x for x in document["inbounds"] if x["tag"] == NEW_INNER_TAG)
            assert modern_outer["users"] == legacy_outer["users"]
            assert modern_inner["users"] == [
                {"name": "tp-sub-17", "password": user_inner_key("tp-sub-17", outer_pass, private_seed)},
                {"name": "tp-sub-18", "password": user_inner_key("tp-sub-18", password_b, private_seed)},
            ]
            assert document["inbounds"][1] == legacy_config["inbounds"][1]
            inbound_script = accounts._snapshot_script("shadowtls")
            output = io.StringIO()
            with redirect_stdout(output):
                exec(inbound_script, {})
            inbound = json.loads(output.getvalue().splitlines()[-1])
            assert inbound["_twinpanel_shadowtls_identity_inner"]["port"] == 18448
            node = SimpleNamespace(
                id=6, name="canary", public_ip="127.0.0.1", public_domain=None,
            )
            item = accounts.client_item(
                node, accounts.SingBoxAccountSecret(
                    protocol="shadowtls",username="tp-sub-18",password=password_b
                ), inbound, server="127.0.0.1",
            )
            generated=json.loads(item["config"])
            assert item["port"] == 18448
            assert generated["outbounds"][0]["method"] == "2022-blake3-aes-128-gcm"
            assert generated["outbounds"][0]["password"] == (
                server_key+":"+user_inner_key("tp-sub-18",password_b,private_seed)
            )
            # Turning off opt-in must serve original AES-GCM credentials,
            # without changing the installed modern listener.
            data=json.loads(state.read_text())
            data["shadowtls_identity2022"]["delivery_enabled"]=False
            state.write_text(json.dumps(data))
            output=io.StringIO()
            with redirect_stdout(output): exec(inbound_script, {})
            legacy_inbound=json.loads(output.getvalue().splitlines()[-1])
            legacy_item=accounts.client_item(
                node,accounts.SingBoxAccountSecret(
                    protocol="shadowtls",username="tp-sub-18",password=password_b
                ),legacy_inbound,server="127.0.0.1",
            )
            legacy_out=json.loads(legacy_item["config"])
            assert legacy_item["port"] == 8448
            assert legacy_out["outbounds"][0]["method"] == "aes-256-gcm"
            # Revocation removes only the target member from both auth maps.
            execute(accounts._mutation_script("shadowtls", "tp-sub-18", None))
            Path(str(config) + ".account-new").replace(config)
            after=json.loads(config.read_text())
            for tag in ("twinpanel-shadowtls-in", NEW_OUTER_TAG, NEW_INNER_TAG):
                entry=next(x for x in after["inbounds"] if x["tag"] == tag)
                assert not any(x.get("name") == "tp-sub-18" for x in entry.get("users", []))
            # Existing active legacy customer and modern key are untouched.
            legacy_after=next(x for x in after["inbounds"] if x["tag"] == "twinpanel-shadowtls-in")
            assert any(x.get("name") == "tp-sub-17" and x.get("password") == outer_pass
                       for x in legacy_after["users"])
            print("SHADOWTLS_PARALLEL_ADD_REVOKE_DELIVERY_GATE_PASS")


if __name__ == "__main__":
    test()
