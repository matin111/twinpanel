#!/usr/bin/env python3
"""Continuous authenticated-mux carrier failover probe from Iran lab host only.
Not a customer VPN test. 15-second flow survives external lab carrier outages.
"""
import argparse
import json
import secrets
import selectors
import socket
import struct
import time

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--bind-ip",default="94.183.231.158")
    p.add_argument("--target-ip",default="94.183.231.158")
    p.add_argument("--count",type=int,default=320)
    p.add_argument("--interval",type=float,default=.045)
    a=p.parse_args()
    if not 80<=a.count<=800 or not .01<=a.interval<=.2:
        p.error("bounded lab experiment only")
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.bind((a.bind_ip,0))
    s.setblocking(False)
    prefix=b"TT-THIRD-PATH-V1:"+secrets.token_bytes(10)
    selector=selectors.DefaultSelector()
    selector.register(s,selectors.EVENT_READ)
    received={}
    sent={}
    bad=0
    start=time.monotonic()
    print("THREE_PATH_PROBE_READY count="+str(a.count),flush=True)
    try:
        next_due=start
        index=0
        while index<a.count or time.monotonic()-start<a.count*a.interval+3:
            now=time.monotonic()
            while index<a.count and now>=next_due:
                seq=index
                payload=prefix+struct.pack("!I",seq)+b"Q"*140
                s.sendto(payload,(a.target_ip,37981))
                sent[seq]=time.monotonic()
                index+=1
                next_due=start+index*a.interval
                now=time.monotonic()
            for key,_ in selector.select(.008):
                while True:
                    try:data,source=s.recvfrom(1500)
                    except BlockingIOError:break
                    if source[0]!=a.target_ip or not data.startswith(prefix) or len(data)!=len(prefix)+4+140 or data[-140:]!=b"Q"*140:
                        bad+=1
                        continue
                    seq=struct.unpack("!I",data[len(prefix):len(prefix)+4])[0]
                    if seq in sent and seq not in received:
                        received[seq]=time.monotonic()
            if index==a.count and time.monotonic()-start>a.count*a.interval+3:break
        missing=sorted(set(sent)-set(received))
        latencies=sorted((received[n]-sent[n])*1000 for n in received)
        result={"sent":len(sent),"received":len(received),
                "missing":missing[:35],"unexpected":bad,
                "p95_ms":round(latencies[int(.95*(len(latencies)-1))],2) if latencies else None,
                "duration_s":round(time.monotonic()-start,2)}
        print("THREE_PATH_RESULT "+json.dumps(result,separators=(",",":")),flush=True)
        return 0 if result["received"]==result["sent"] and not bad else 2
    finally:
        selector.close()
        s.close()
if __name__=="__main__":
    raise SystemExit(main())
