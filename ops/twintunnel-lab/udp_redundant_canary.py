#!/usr/bin/env python3
"""TwinTunnel two-carrier UDP REDUNDANCY CANARY (echo only; localhost, one client).

Duplicates only the known sequence-coded TTLB1 lab probe traffic across
Rakhsh GRE + Shabdiz-UDP and forwards the first matching echo.
No VPN users, no production UDP routing, no generic packet deduplication.
"""
import argparse
import selectors
import signal
import socket
import time

LISTEN=("127.0.0.1",37962)
BACKENDS=(("GRE",("127.0.0.1",37921)),("UDP",("127.0.0.1",37933)))
PREFIX=b"TTLB1TT-UDP-CANARY:"


def parse_seq(packet):
    if not packet.startswith(PREFIX) or len(packet) != 247:
        return None
    return int.from_bytes(packet[len(PREFIX):len(PREFIX)+4], "big")

class Canary:
    def __init__(self):
        self.sel=selectors.DefaultSelector()
        self.front=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.front.bind(LISTEN);self.front.setblocking(False)
        self.sel.register(self.front,selectors.EVENT_READ,("client",None))
        self.backends={}
        for name,addr in BACKENDS:
            s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            s.connect(addr);s.setblocking(False);self.backends[name]=s
            self.sel.register(s,selectors.EVENT_READ,("backend",name))
        self.client=None
        self.seen=set()
        self.sent=0
        self.unique=0
        self.duplicates=0
        self.unsupported=0
        self.running=True

    def stop(self,*_):
        self.running=False

    def run(self,seconds):
        print("DUAL_UDP_READY listen=127.0.0.1:37962 data_only_canary=true",flush=True)
        begin=time.monotonic()
        last_report=begin
        try:
            while self.running and time.monotonic()-begin<seconds:
                for key,_ in self.sel.select(timeout=0.1):
                    typ,name=key.data
                    try:packet,peer=key.fileobj.recvfrom(2048)
                    except (BlockingIOError,OSError):continue
                    if typ=="client":
                        if self.client is None:self.client=peer
                        if peer!=self.client or parse_seq(packet) is None:
                            self.unsupported+=1;continue
                        self.sent+=1
                        for backend in self.backends.values():
                            try:backend.send(packet)
                            except OSError:pass
                    else:
                        if not self.client:
                            continue
                        seq=parse_seq(packet)
                        if seq is None:
                            continue
                        if seq in self.seen:
                            self.duplicates+=1
                            continue
                        self.seen.add(seq)
                        self.unique+=1
                        try:self.front.sendto(packet,self.client)
                        except OSError:pass
                now=time.monotonic()
                if now-last_report>=5:
                    print("DUAL_UDP_STATS sent",self.sent,"unique",self.unique,"duplicates",self.duplicates,flush=True)
                    last_report=now
        finally:
            print("DUAL_UDP_FINAL sent",self.sent,"unique",self.unique,"duplicates",self.duplicates,"unsupported",self.unsupported,flush=True)
            self.sel.close();self.front.close()
            for s in self.backends.values():s.close()

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--duration",type=int,default=100)
    a=p.parse_args()
    if not 10<=a.duration<=200:p.error("duration 10..200")
    c=Canary()
    signal.signal(signal.SIGTERM,c.stop)
    signal.signal(signal.SIGINT,c.stop)
    c.run(a.duration)