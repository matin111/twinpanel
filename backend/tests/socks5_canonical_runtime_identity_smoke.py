"""Socks5 accounting must accept only observed canonical tp-sub-N identities."""
from unittest.mock import patch
from app.services.singbox_native_accounting_v265 import _observed_devices_by_protocol


class Q:
    def filter(self,*args): return self
    def distinct(self): return self
    def all(self): return []
class DB:
    def query(self,*args): return Q()

def test():
    base=[
        {"device_id":11,"subscription_id":3896,"protocol":"socks5",
         "identity":"customer-login","telemetry_identity":"customer-login"},
        {"device_id":12,"subscription_id":3895,"protocol":"socks5",
         "identity":"other-login","telemetry_identity":"other-login"},
        {"device_id":13,"subscription_id":3894,"protocol":"socks5",
         "identity":"legacy-login","telemetry_identity":"legacy-login"},
    ]
    snapshot={"rows":[
        {"user":"tp-sub-3896","inbound":"twinpanel-socks5-in","inbound_type":"socks"},
        {"user":"legacy-login","inbound":"twinpanel-socks5-in","inbound_type":"socks"},
        {"user":"tp-sub-3895","inbound":"wrong-inbound","inbound_type":"socks"},
    ]}
    with patch("app.services.quota_node_sync.build_node_devices",return_value=base):
        result=_observed_devices_by_protocol(DB(),22,snapshot)["socks5"]
    assert result[0]["telemetry_identity"]=="tp-sub-3896"
    assert result[1]["telemetry_identity"]=="other-login"
    assert result[2]["telemetry_identity"]=="legacy-login"
    assert base[0]["telemetry_identity"]=="customer-login"
    print("SOCKS5_AUTHENTICATED_RUNTIME_IDENTITY_PASS")
if __name__=="__main__": test()
