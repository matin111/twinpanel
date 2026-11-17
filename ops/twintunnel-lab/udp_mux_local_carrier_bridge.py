#!/usr/bin/env python3
"""Local-only two-path UDP bridge for same-host MUX capacity tests."""
import argparse
import selectors
import signal
import socket
import time

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--path1-port",type=int,default=38921)
    p.add_argument("--path2-port",type=int,default=38933)
    p.add_argument("--exit-port",type=int,default=38922)
    p.add_argument("--duration",type=int,default=90)
    a=p.parse_args()
    if not 1<=a.duration<=180:
        p.error("duration must be 1..180")
    sel=selectors.DefaultSelector()
    sockets={}
    last_client={}
    exit_addr=("127.0.0.1",a.exit_port)
    for path,port in ((1,a.path1_port),(2,a.path2_port)):
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        s.bind(("127.0.0.1",port))
        s.setblocking(False)
        sockets[path]=s
        last_client[path]=None
        sel.register(s,selectors.EVENT_READ,path)
    stop=[False]
    signal.signal(signal.SIGTERM,lambda *_:stop.__setitem__(0,True))
    signal.signal(signal.SIGINT,lambda *_:stop.__setitem__(0,True))
    stats={"forwarded":0,"returned":0,"errors":0}
    print("TT_LOCAL_CARRIER_BRIDGE_READY",flush=True)
    started=time.monotonic()
    try:
        while not stop[0] and time.monotonic()-started<a.duration:
            for key,_ in sel.select(.05):
                path=key.data
                sock=key.fileobj
                for _ in range(96):
                    try:data,source=sock.recvfrom(1600)
                    except BlockingIOError:break
                    try:
                        if source==exit_addr:
                            target=last_client[path]
                            if target is not None:
                                sock.sendto(data,target)
                                stats["returned"]+=1
                        else:
                            last_client[path]=source
                            sock.sendto(data,exit_addr)
                            stats["forwarded"]+=1
                    except OSError:
                        stats["errors"]+=1
    finally:
        print("TT_LOCAL_CARRIER_BRIDGE_FINAL "+str(stats),flush=True)
        for sock in sockets.values():sock.close()
        sel.close()
if __name__=="__main__":main()
