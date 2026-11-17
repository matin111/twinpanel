#!/usr/bin/env python3
"""Offline, no-network regression tests of authenticated UDP multi-user mux."""
import collections
import importlib.util
from pathlib import Path
import unittest

script=Path(__file__).resolve().parents[1]/"udp_multiuser_mux.py"
spec=importlib.util.spec_from_file_location("tt_udp_mux_module",script)
mux=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mux)

class FrameTests(unittest.TestCase):
    def setUp(self):
        self.c=mux.Codec(b"K"*32)
    def test_authenticated_roundtrip(self):
        data=self.c.encode(1,1,123,7,b"wg-probe")
        self.assertEqual(self.c.decode(data),(1,1,123,7,b"wg-probe"))
    def test_wrong_tag(self):
        data=self.c.encode(2,2,12,10,b"test")
        self.assertIsNone(self.c.decode(data[:-1]+bytes([data[-1]^1])))
    def test_path_tampering(self):
        data=bytearray(self.c.encode(2,2,12,10,b"test"))
        data[9]=1
        self.assertIsNone(self.c.decode(bytes(data)))
    def test_wrong_key(self):
        data=self.c.encode(1,2,55,100,b"x")
        self.assertIsNone(mux.Codec(b"Z"*32).decode(data))
    def test_oversize(self):
        with self.assertRaises(ValueError):
            self.c.encode(1,1,100,2,b"a"*(mux.MAX_PAYLOAD+1))
    def test_service_isolation(self):
        a=self.c.decode(self.c.encode(1,1,7,2,b"A"))
        b=self.c.decode(self.c.encode(2,1,8,2,b"B"))
        self.assertNotEqual(a[0],b[0])
    def test_duplicate_rejected(self):
        r=mux.ReplayWindow()
        self.assertTrue(r.accept(1))
        self.assertFalse(r.accept(1))
    def test_out_of_order_once(self):
        r=mux.ReplayWindow()
        self.assertTrue(r.accept(100))
        self.assertTrue(r.accept(99))
        self.assertFalse(r.accept(99))
    def test_stale_replay_rejected(self):
        r=mux.ReplayWindow()
        self.assertTrue(r.accept(5000))
        self.assertFalse(r.accept(4000))
    def test_max_sessions(self):
        self.assertEqual(mux.MAX_FLOWS,64)
    def test_binary_payload(self):
        payload=bytes(range(256))*4
        self.assertEqual(self.c.decode(self.c.encode(1,2,5,3,payload))[-1],payload)
    def test_authenticated_flow_id_consistency(self):
        m=mux.Mux.__new__(mux.Mux)
        m.flows={}
        m.stats=collections.Counter()
        f=m._new_flow(1,flow_id=0x112233)
        self.assertIs(f,m.flows[0x112233])
        self.assertEqual(f.flow_id,0x112233)
        self.assertIsNone(m._new_flow(1,flow_id=0x112233))
    def test_distinct_user_sessions(self):
        m=mux.Mux.__new__(mux.Mux)
        m.flows={}
        m.stats=collections.Counter()
        f1=m._new_flow(1,client=("217.179.6.142",1234))
        f2=m._new_flow(1,client=("217.179.6.142",5678))
        self.assertNotEqual(f1.flow_id,f2.flow_id)
        self.assertNotEqual(f1.client,f2.client)

if __name__=="__main__":
    unittest.main()