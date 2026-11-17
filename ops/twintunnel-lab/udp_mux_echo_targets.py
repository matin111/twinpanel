#!/usr/bin/env python3
"""Two-port loopback UDP echo for multi-user failover tests only."""
import argparse
import collections
import selectors
import signal
import socket
import time

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--duration",type=int,default=300)
    args=p.parse_args()
    sel=selectors.DefaultSelector()
    stats=collections.Counter()
    source_ports={37983:set(),37984:set()}
    for port in (37983,37984):
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        s.bind(("127.0.0.1",port))
        s.setblocking(False)
        sel.register(s,selectors.EVENT_READ,port)
    stop=[False]
    signal.signal(signal.SIGTERM,lambda *_: stop.__setitem__(0,True))
    print("TT_MUX_TWO_ECHO_READY",flush=True)
    started=time.monotonic()
    try:
        while not stop[0] and time.monotonic()-started<args.duration:
            for key,_ in sel.select(timeout=0.12):
                port=key.data
                for _ in range(96):
                    try:packet,src=key.fileobj.recvfrom(1600)
                    except BlockingIOError:break
                    source_ports[port].add(src)
                    stats[port]+=1
                    try:key.fileobj.sendto(packet,src)
                    except OSError:stats["send_errors"]+=1
    finally:
        print("TT_MUX_ECHO_FINAL counts="+str(dict(stats))+
              " wg_unique_source_ports="+str(len(source_ports[37983]))+
              " ovpn_unique_source_ports="+str(len(source_ports[37984])),flush=True)
        for key in list(sel.get_map().values()):
            key.fileobj.close()
        sel.close()
if __name__=="__main__": main()