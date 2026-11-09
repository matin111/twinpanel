"""Regression: SOCKS5 uses the same username/password as Cisco.

Does not require live credentials or network access.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.routers.modern_account_delivery_v1 import _singbox_secret
from app.singbox_subscription_accounts import SingBoxAccountSecret,client_item
from app.central_singbox_collision_policy_v1 import resolve_node_login_collisions
from app.modern_protocol_tunnel_binding_v251 import _rewrite_modern_item


class FakeDelivery:
    @staticmethod
    def _dec(value):
        return value


def run():
    sub=SimpleNamespace(
        id=9991,account_username="panel-account-9991",
        account_password_encrypted="12345678"
    )
    new_cred=SimpleNamespace(secret_encrypted=None)
    secret=_singbox_secret(FakeDelivery,new_cred,"socks5",sub)
    assert secret.protocol=="socks5"
    assert secret.username=="panel-account-9991"
    assert secret.password=="12345678"
    print("SOCKS5_CANONICAL_LOGIN_PASS")

    legacy=dict(protocol="socks5",username="tp-sub-9991",
                password="legacy-long-token")
    original=_singbox_secret(
        FakeDelivery,SimpleNamespace(secret_encrypted=legacy),"socks5",sub
    )
    assert original.username=="tp-sub-9991"
    assert original.password=="legacy-long-token"
    print("SOCKS5_LEGACY_NO_FORCED_ROTATION_PASS")

    node=SimpleNamespace(id=88,name="sample-exit",
                         public_ip="192.0.2.8",public_domain=None)
    inbound={"listen_port":10808}
    item=client_item(node,secret,inbound)
    delivered=_rewrite_modern_item(item,"socks5","192.0.2.7",38088)
    assert delivered["port"]==38088
    assert delivered["outbound"]["server_port"]==38088
    assert delivered["outbound"]["username"]=="panel-account-9991"
    assert delivered["outbound"]["password"]=="12345678"
    doc=json.loads(delivered["config"])
    socks=next(x for x in doc["outbounds"] if x["type"]=="socks")
    assert socks["server"]=="192.0.2.7" and socks["server_port"]==38088
    assert socks["username"]=="panel-account-9991" and socks["password"]=="12345678"
    print("SOCKS5_TUNNEL_CONFIG_AND_CREDENTIAL_PASS")

    a=SingBoxAccountSecret(protocol="socks5",username="duplicate",
                          password="11111111")
    b=SingBoxAccountSecret(protocol="socks5",username="duplicate",
                          password="22222222")
    changed, aliases=resolve_node_login_collisions(
        [(101,"socks5",a),(102,"socks5",b)],
        [(101,"socks5","duplicate"),(102,"socks5","duplicate")],
    )
    assert aliases==2 and len({x[2].username for x in changed})==2
    assert {x[2].password for x in changed}=={"11111111","22222222"}
    print("SOCKS5_COLLISION_SAFE_ALIAS_PASS")


if __name__=="__main__":
    run()
