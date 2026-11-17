#!/usr/bin/env python3
"""Offline, no-network regression tests of authenticated UDP multi-user mux."""
import collections
import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace

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
    def test_third_authenticated_path_roundtrip(self):
        payload=b"third-turkey-carrier"
        frame=self.c.encode(1,3,778,44,payload)
        self.assertEqual(self.c.decode(frame),(1,3,778,44,payload))
        tampered=bytearray(frame)
        tampered[9]=2
        self.assertIsNone(self.c.decode(bytes(tampered)))

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
        self.assertEqual(mux.MAX_FLOWS,512)
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

class ReceiveBatchTests(unittest.TestCase):
    def setUp(self):
        self.m=mux.Mux.__new__(mux.Mux)
        self.m.stats=collections.Counter()
        self.received=[]
        self.m._entry_client=lambda service,data,addr:self.received.append((service,data,addr))

    def simulate(self,count):
        class Sock:
            def __init__(self,n):
                self.n=n
                self.pos=0
            def recvfrom(self,size):
                if self.pos>=self.n:
                    raise BlockingIOError()
                self.pos+=1
                return b"payload",("127.0.0.1",20000+self.pos)
        key=SimpleNamespace(data=("client",1),fileobj=Sock(count))
        return self.m._drain_ready_socket(key)

    def test_read_all_available_packets(self):
        self.assertEqual(self.simulate(10),10)
        self.assertEqual(len(self.received),10)
        self.assertEqual(self.m.stats["full_recv_batches"],0)

    def test_bounded_batch_preserves_other_sockets(self):
        self.assertEqual(self.simulate(150),mux.MAX_RECV_BATCH)
        self.assertEqual(len(self.received),mux.MAX_RECV_BATCH)
        self.assertEqual(self.m.stats["full_recv_batches"],1)


class AckRetryTests(unittest.TestCase):
    def setUp(self):
        self.m=mux.Mux.__new__(mux.Mux)
        self.m.codec=mux.Codec(b"K"*32)
        self.m.stats=collections.Counter()
        self.m.flows={}
        self.m.pending_packets=0
        self.m.pending_bytes=0

    def test_ack_header_authenticated(self):
        encoded=self.m.codec.encode(1|mux.ACK_FLAG,2,44,17,mux.ACK_PAYLOAD)
        self.assertEqual(self.m.codec.decode(encoded),
                         (129,2,44,17,mux.ACK_PAYLOAD))
        self.assertIsNone(self.m.codec.decode(encoded[:-1]+bytes([encoded[-1]^7])))

    def test_ack_clears_only_outstanding_reply(self):
        flow=mux.Flow(44,1)
        self.assertTrue(self.m._queue_pending(flow,"down",17,b"reply",10.0))
        self.m.flows[44]=flow
        encoded=self.m.codec.encode(129,1,44,17,mux.ACK_PAYLOAD)
        self.m._exit_transport(encoded,("127.0.0.1",50505))
        self.assertFalse(flow.pending_down)
        self.assertEqual(self.m.stats["acks_received"],1)

    def test_wrong_service_ack_rejected(self):
        flow=mux.Flow(44,1)
        flow.pending_down[17]=(b"reply",10.0,1)
        self.m.flows[44]=flow
        encoded=self.m.codec.encode(130,1,44,17,mux.ACK_PAYLOAD)
        self.m._exit_transport(encoded,("127.0.0.1",50505))
        self.assertIn(17,flow.pending_down)
        self.assertEqual(self.m.stats["invalid_ack"],1)

    def test_retry_is_bounded(self):
        self.m.args=SimpleNamespace(role="exit")
        class Sink:
            def __init__(self):self.sent=[]
            def sendto(self,frame,target):
                self.sent.append((frame,target))
                return len(frame)
        sink=Sink()
        self.m.listeners={0:sink}
        flow=mux.Flow(44,1)
        flow.paths={1:(("127.0.0.1",40001),100.0),
                    2:(("127.0.0.1",40002),100.0)}
        self.assertTrue(self.m._queue_pending(flow,"down",10,b"reply",100.0))
        self.m.flows[44]=flow
        self.m._retry_pending(100.10)
        self.assertEqual(len(sink.sent),0)
        self.m._retry_pending(100.26)
        self.assertEqual(len(sink.sent),2)
        self.m._retry_pending(100.55)
        self.assertEqual(len(sink.sent),4)
        self.m._retry_pending(100.85)
        self.assertEqual(len(sink.sent),4)
        self.assertEqual(self.m.stats["down_unacked"],1)
        self.assertFalse(flow.pending_down)

    def test_stale_packet_is_never_acknowledged(self):
        class Sink:
            def __init__(self):self.sent=[]
            def sendto(self,frame,target):
                self.sent.append((frame,target))
                return len(frame)
            def send(self,frame):
                self.sent.append(frame)
                return len(frame)
        client=Sink()
        a=Sink()
        b=Sink()
        self.m.listeners={1:client}
        self.m.backends={1:a,2:b}
        flow=mux.Flow(44,1,("127.0.0.1",12345))
        flow.recv_window.accept(1000)
        self.m.flows[44]=flow
        stale=self.m.codec.encode(1,1,44,1,b"old reply")
        self.m._entry_reply(1,stale)
        self.assertEqual(self.m.stats["stale_down"],1)
        self.assertEqual(len(a.sent),0)
        self.assertEqual(len(client.sent),0)

    def test_failed_local_reply_remains_retryable_and_unacked(self):
        class FailThenSend:
            def __init__(self):
                self.calls=0
                self.delivered=[]
            def sendto(self,data,addr):
                self.calls+=1
                if self.calls==1:
                    raise OSError("temporary UDP client socket failure")
                self.delivered.append((data,addr))
                return len(data)
        class AckRecorder:
            def __init__(self):self.sent=[]
            def send(self,data):self.sent.append(data);return len(data)
        local=FailThenSend()
        first=AckRecorder()
        second=AckRecorder()
        self.m.listeners={1:local}
        self.m.backends={1:first,2:second}
        f=mux.Flow(700,1,("127.0.0.1",34567))
        self.m.flows[700]=f
        packet=self.m.codec.encode(1,1,700,55,b"reply")
        self.m._entry_reply(1,packet)
        self.assertEqual(self.m.stats["client_send_error"],1)
        self.assertFalse(f.recv_window.was_delivered(55))
        self.assertFalse(first.sent)
        self.assertFalse(second.sent)
        self.m._entry_reply(1,packet)
        self.assertTrue(f.recv_window.was_delivered(55))
        self.assertEqual(len(local.delivered),1)
        self.assertEqual(len(first.sent),1)
        self.assertEqual(len(second.sent),1)
        self.m._entry_reply(1,packet)
        self.assertEqual(len(local.delivered),1)

    def test_delivered_reply_acknowledged_and_deduplicated(self):
        class Sink:
            def __init__(self):self.sent=[]
            def sendto(self,frame,target):
                self.sent.append((frame,target))
                return len(frame)
            def send(self,frame):
                self.sent.append(frame)
                return len(frame)
        client=Sink()
        a=Sink()
        b=Sink()
        self.m.listeners={1:client}
        self.m.backends={1:a,2:b}
        flow=mux.Flow(44,1,("127.0.0.1",12345))
        self.m.flows[44]=flow
        p=self.m.codec.encode(1,1,44,17,b"reply")
        self.m._entry_reply(1,p)
        self.assertEqual(len(client.sent),1)
        self.assertEqual(len(a.sent),1)
        self.assertEqual(len(b.sent),1)
        self.assertEqual(self.m.codec.decode(a.sent[0]),(129,1,44,17,mux.ACK_PAYLOAD))
        self.m._entry_reply(1,p)
        self.assertEqual(len(client.sent),1)


class BidirectionalReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.m=mux.Mux.__new__(mux.Mux)
        self.m.codec=mux.Codec(b"K"*32)
        self.m.stats=collections.Counter()
        self.m.flows={}
        self.m.pending_packets=0
        self.m.pending_bytes=0
        class SocketRecorder:
            def __init__(self):self.sent=[]
            def send(self,data):
                self.sent.append(data)
                return len(data)
            def sendto(self,data,addr):
                self.sent.append((data,addr))
                return len(data)
        self.SocketRecorder=SocketRecorder

    def test_upstream_ack_removes_pending_only_for_matching_service(self):
        f=mux.Flow(444,1,("127.0.0.1",45678))
        self.assertTrue(self.m._queue_pending(f,"up",31,b"payload",100.0))
        self.m.flows[444]=f
        encoded=self.m.codec.encode(129,1,444,31,mux.ACK_PAYLOAD)
        self.m._entry_reply(1,encoded)
        self.assertFalse(f.pending_up)
        self.assertEqual(self.m.stats["up_acks_received"],1)

    def test_wrong_service_upstream_ack_rejected(self):
        f=mux.Flow(444,1)
        f.pending_up[31]=(b"payload",100.0,1)
        self.m.flows[444]=f
        encoded=self.m.codec.encode(130,1,444,31,mux.ACK_PAYLOAD)
        self.m._entry_reply(1,encoded)
        self.assertIn(31,f.pending_up)
        self.assertEqual(self.m.stats["invalid_up_ack"],1)

    def test_upstream_retries_are_bounded(self):
        self.m.args=SimpleNamespace(role="entry")
        first=self.SocketRecorder()
        second=self.SocketRecorder()
        self.m.backends={1:first,2:second}
        f=mux.Flow(777,2)
        self.assertTrue(self.m._queue_pending(f,"up",19,b"upstream",100.0))
        self.m.flows[777]=f
        self.m._retry_pending(100.10)
        self.assertFalse(first.sent)
        self.m._retry_pending(100.26)
        self.assertEqual(len(first.sent),1)
        self.assertEqual(len(second.sent),1)
        self.m._retry_pending(100.54)
        self.assertEqual(len(first.sent),2)
        self.m._retry_pending(100.85)
        self.assertFalse(f.pending_up)
        self.assertEqual(self.m.stats["up_unacked"],1)

    def test_exit_acks_only_after_local_send_success(self):
        sink=self.SocketRecorder()
        exit_socket=self.SocketRecorder()
        f=mux.Flow(555,1)
        f.socket=exit_socket
        self.m.flows[555]=f
        self.m.listeners={0:sink}
        data=self.m.codec.encode(1,1,555,4,b"udp-data")
        self.m._exit_transport(data,("127.0.0.1",45678))
        self.assertEqual(len(exit_socket.sent),1)
        self.assertEqual(self.m.stats["server_packets"],1)
        self.assertEqual(len(sink.sent),1)
        self.assertEqual(self.m.codec.decode(sink.sent[0][0]),
                         (129,1,555,4,mux.ACK_PAYLOAD))
        self.m._exit_transport(data,("127.0.0.1",45678))
        self.assertEqual(self.m.stats["duplicates_up"],1)
        self.assertEqual(len(exit_socket.sent),1)

    def test_failed_local_send_is_not_acked(self):
        class Fail:
            def send(self,data):raise OSError("test failure")
        sink=self.SocketRecorder()
        f=mux.Flow(555,1)
        f.socket=Fail()
        self.m.flows[555]=f
        self.m.listeners={0:sink}
        frame=self.m.codec.encode(1,1,555,8,b"udp-data")
        self.m._exit_transport(frame,("127.0.0.1",45678))
        self.assertEqual(self.m.stats["server_send_error"],1)
        self.assertFalse(f.recv_window.was_delivered(8))
        self.assertEqual(len(sink.sent),0)


class PendingBudgetTests(unittest.TestCase):
    def setUp(self):
        self.m=mux.Mux.__new__(mux.Mux)
        self.m.stats=collections.Counter()
        self.m.flows={}
        self.m.clients={}
        self.m.pending_packets=0
        self.m.pending_bytes=0

    def test_pending_accounting_and_global_caps(self):
        f=mux.Flow(1,1)
        self.assertTrue(self.m._queue_pending(f,"up",1,b"x"*128,10.0))
        self.assertEqual(self.m.pending_packets,1)
        self.assertEqual(self.m.pending_bytes,128)
        self.assertIsNotNone(self.m._pop_pending(f.pending_up,1))
        self.assertEqual(self.m.pending_packets,0)
        self.assertEqual(self.m.pending_bytes,0)

        self.m.pending_packets=mux.MAX_PENDING_PACKETS
        self.assertFalse(self.m._queue_pending(f,"up",2,b"x",11.0))
        self.assertEqual(self.m.stats["up_pending_overflow"],1)
        self.m.pending_packets=0
        self.m.pending_bytes=mux.MAX_PENDING_BYTES
        self.assertFalse(self.m._queue_pending(f,"down",3,b"x",12.0))
        self.assertEqual(self.m.stats["down_pending_overflow"],1)

    def test_per_flow_pending_cap(self):
        f=mux.Flow(2,1)
        for seq in range(mux.MAX_PENDING_PER_FLOW):
            self.assertTrue(self.m._queue_pending(f,"up",seq,b"x",float(seq)))
        self.assertFalse(self.m._queue_pending(f,"up",999,b"x",100.0))
        self.assertEqual(len(f.pending_up),mux.MAX_PENDING_PER_FLOW)
        self.assertEqual(self.m.pending_packets,mux.MAX_PENDING_PER_FLOW)

    def test_expiry_releases_pending_budget(self):
        f=mux.Flow(3,1)
        self.m.flows[3]=f
        self.assertTrue(self.m._queue_pending(f,"up",1,b"abc",1.0))
        self.assertTrue(self.m._queue_pending(f,"down",2,b"defg",1.0))
        self.assertEqual((self.m.pending_packets,self.m.pending_bytes),(2,7))
        f.updated=0.0
        self.m._expire(mux.TTL+1.0)
        self.assertFalse(self.m.flows)
        self.assertEqual((self.m.pending_packets,self.m.pending_bytes),(0,0))

    def test_512_flow_ceiling_is_enforced(self):
        for index in range(mux.MAX_FLOWS):
            self.assertIsNotNone(self.m._new_flow(1,("127.0.0.1",10000+index)))
        self.assertEqual(len(self.m.flows),512)
        self.assertIsNone(self.m._new_flow(1,("127.0.0.1",20000)))
        self.assertEqual(self.m.stats["flow_limit"],1)


if __name__=="__main__":
    unittest.main()