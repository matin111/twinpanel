"""Offline tests of restricted third-country UDP relay; no network sockets."""
import collections
import importlib.util
from pathlib import Path
import struct
import time
import unittest
from types import SimpleNamespace

source=Path(__file__).resolve().parents[1]/"udp_turkey_transit_relay.py"
spec=importlib.util.spec_from_file_location("third_country_relay",source)
relaymod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(relaymod)

class Output:
    def __init__(self):
        self.sent=[]
    def sendto(self,data,addr):
        self.sent.append((data,addr))
        return len(data)

def valid_frame(fid=776,service=1,path=3):
    return relaymod.FRAME.pack(relaymod.MAGIC,service,path,fid,9)+b"payload"+b"x"*16

class RelayPolicyTests(unittest.TestCase):
    def test_canary_frame_contract(self):
        self.assertEqual(relaymod.flow_key(b"TTLB1"+b"A"*12),("canary",0))
        self.assertIsNone(relaymod.flow_key(b"TTLB1"+b"A"*3))
    def test_authenticated_mux_shape_requires_carrier_3(self):
        self.assertEqual(relaymod.flow_key(valid_frame()),("mux",776))
        self.assertIsNone(relaymod.flow_key(valid_frame(path=2)))
        self.assertIsNone(relaymod.flow_key(valid_frame(fid=0)))
        self.assertIsNone(relaymod.flow_key(valid_frame(service=7)))
    def test_turkey_allowlist_and_fixed_france_peer(self):
        m=relaymod.Relay.__new__(relaymod.Relay)
        m.args=SimpleNamespace(mode="turkey",france_ip="217.179.6.142",
          france_port=38832,allowed_client_ip="94.183.231.158")
        m.state={}
        m.stats=collections.Counter()
        m.public=Output()
        p=valid_frame()
        m.process("public",p,("1.1.1.1",47119))
        self.assertFalse(m.public.sent)
        self.assertEqual(m.stats["origin_rejected"],1)
        m.process("public",p,("94.183.231.158",49120))
        self.assertEqual(m.public.sent,[ (p,("217.179.6.142",38832)) ])
        self.assertEqual(len(m.state),1)
        m.process("public",p,("217.179.6.142",38832))
        self.assertEqual(m.public.sent[-1],(p,("94.183.231.158",49120)))
        self.assertEqual(m.stats["returned"],1)
    def test_unknown_flow_response_never_reflected(self):
        m=relaymod.Relay.__new__(relaymod.Relay)
        m.args=SimpleNamespace(mode="turkey",france_ip="217.179.6.142",
          france_port=38832,allowed_client_ip="94.183.231.158")
        m.state={}
        m.stats=collections.Counter()
        m.public=Output()
        m.process("public",valid_frame(),("217.179.6.142",38832))
        self.assertEqual(m.stats["orphan_reply"],1)
        self.assertFalse(m.public.sent)
    def test_france_forwards_only_turkey_to_fixed_loopback(self):
        m=relaymod.Relay.__new__(relaymod.Relay)
        m.args=SimpleNamespace(mode="france",turkey_ip="167.104.219.168",
           turkey_port=38831,local_target_port=37922)
        m.stats=collections.Counter()
        m.public=Output()
        m.local=Output()
        data=valid_frame()
        m.process("public",data,("94.183.231.158",38831))
        self.assertFalse(m.local.sent)
        m.process("public",data,("167.104.219.168",38831))
        self.assertEqual(m.local.sent[-1],(data,("127.0.0.1",37922)))
        m.process("local",data,("127.0.0.1",9999))
        self.assertFalse(m.public.sent)
        m.process("local",data,("127.0.0.1",37922))
        self.assertEqual(m.public.sent[-1],(data,("167.104.219.168",38831)))
if __name__=="__main__":
    unittest.main()
