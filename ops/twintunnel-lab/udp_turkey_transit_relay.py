#!/usr/bin/env python3
"""Bounded, fixed-destination Turkey/France UDP transit relay for TwinTunnel LAB.

Not a generic UDP proxy: IP allowlists, flow-frame validation, fixed peers,
limited state and time, and strictly no production interface/route changes.
The TwinTunnel mux authenticates frames end-to-end; relays do not hold keys.
"""
import argparse
import collections
import selectors
import signal
import socket
import struct
import time

FRAME=struct.Struct("!8sBBQQ")
MAGIC=b"TTMUXV01"
MAX_FRAME=1292
MAX_FLOWS=512
FLOW_TTL=90.0
RECV_BATCH=64

def flow_key(data):
    if data.startswith(b"TTLB1") and 17 <= len(data) <= 1400:
        return ("canary",0)
    if not FRAME.size+16 < len(data) <= MAX_FRAME:
        return None
    magic,service,path,fid,_=FRAME.unpack_from(data)
    if magic!=MAGIC or service not in (1,2,129,130) or path!=3 or not fid:
        return None
    return ("mux",fid)

class Relay:
    def __init__(self,args):
        self.args=args
        self.state={}
        self.stats=collections.Counter()
        self.sel=selectors.DefaultSelector()
        self.stop=False
        self.public=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.public.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1024*1024)
        self.public.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,1024*1024)
        self.public.bind((args.listen_ip,args.listen_port))
        self.public.setblocking(False)
        self.sel.register(self.public,selectors.EVENT_READ,"public")
        self.local=None
        if args.mode=="france":
            self.local=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            self.local.bind(("127.0.0.1",0))
            self.local.setblocking(False)
            self.sel.register(self.local,selectors.EVENT_READ,"local")
        self.started=time.monotonic()

    def process(self,kind,data,addr):
        k=flow_key(data)
        if k is None:
            self.stats["bad_frame"]+=1
            return
        now=time.monotonic()
        a=self.args
        if a.mode=="turkey":
            remote=(a.france_ip,a.france_port)
            if addr==remote:
                item=self.state.get(k)
                if item and now-item[1]<=FLOW_TTL:
                    self.public.sendto(data,item[0])
                    self.stats["returned"]+=1
                else:
                    self.stats["orphan_reply"]+=1
            elif addr[0]==a.allowed_client_ip:
                if k not in self.state and len(self.state)>=MAX_FLOWS:
                    self.stats["capacity_reject"]+=1
                    return
                self.state[k]=(addr,now)
                self.public.sendto(data,remote)
                self.stats["forwarded"]+=1
            else:
                self.stats["origin_rejected"]+=1
        else:
            if kind=="public":
                if addr!=(a.turkey_ip,a.turkey_port):
                    self.stats["origin_rejected"]+=1
                    return
                self.local.sendto(data,("127.0.0.1",a.local_target_port))
                self.stats["local_forwarded"]+=1
            elif kind=="local":
                if addr!=("127.0.0.1",a.local_target_port):
                    self.stats["local_origin_rejected"]+=1
                    return
                self.public.sendto(data,(a.turkey_ip,a.turkey_port))
                self.stats["remote_returned"]+=1

    def run(self):
        print("TT_TRANSIT_READY mode="+self.args.mode,flush=True)
        try:
            while not self.stop and time.monotonic()-self.started<self.args.duration:
                for key,_ in self.sel.select(0.08):
                    for _ in range(RECV_BATCH):
                        try:
                            data,addr=key.fileobj.recvfrom(1600)
                        except BlockingIOError:
                            break
                        except OSError:
                            self.stats["socket_error"]+=1
                            break
                        try:self.process(key.data,data,addr)
                        except OSError:self.stats["send_error"]+=1
                now=time.monotonic()
                if self.args.mode=="turkey":
                    for fid,(_,ts) in list(self.state.items()):
                        if now-ts>FLOW_TTL:self.state.pop(fid,None)
        finally:
            print("TT_TRANSIT_FINAL "+str(dict(self.stats))+" states="+str(len(self.state)),flush=True)
            self.sel.close()
            self.public.close()
            if self.local:self.local.close()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("turkey","france"),required=True)
    p.add_argument("--listen-ip",required=True)
    p.add_argument("--listen-port",type=int,required=True)
    p.add_argument("--duration",type=int,default=90)
    p.add_argument("--allowed-client-ip",default="94.183.231.158")
    p.add_argument("--france-ip",default="217.179.6.142")
    p.add_argument("--france-port",type=int,default=38832)
    p.add_argument("--turkey-ip",default="167.104.219.168")
    p.add_argument("--turkey-port",type=int,default=38831)
    p.add_argument("--local-target-port",type=int,default=37922)
    a=p.parse_args()
    if not 10<=a.duration<=900:p.error("10<=duration<=900 required")
    if not 1024<=a.listen_port<=65535:p.error("invalid port")
    relay=Relay(a)
    signal.signal(signal.SIGTERM,lambda *_:setattr(relay,"stop",True))
    signal.signal(signal.SIGINT,lambda *_:setattr(relay,"stop",True))
    relay.run()
if __name__=="__main__":main()
