#!/usr/bin/env python3
"""France-only multiuser UDP probe -> Iran public -> Rakhsh GRE+UDP -> France.
Out-of-order responses are counted by validated session+sequence, not discarded.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import secrets
import socket
import time

TARGETS={1:("94.183.231.158",37981),2:("94.183.231.158",37982)}

def client(service,index,count,interval,bind_ip):
    session=secrets.token_hex(6).encode("ascii")
    prefix=b"TT-MUX-CLIENT:"+bytes([service,index])+session
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.bind((bind_ip,0))
    s.settimeout(.06)
    received={}
    timings={}
    sent_at={}
    unexpected=0
    started=time.monotonic()
    def consume():
        nonlocal unexpected
        while True:
            try:back,src=s.recvfrom(1500)
            except socket.timeout:return
            if src[0]!="94.183.231.158" or len(back)!=len(prefix)+4+196 or not back.startswith(prefix):
                unexpected+=1
                continue
            num=int.from_bytes(back[len(prefix):len(prefix)+4],"big")
            if num<0 or num>=count or back!=prefix+num.to_bytes(4,"big")+b"P"*196:
                unexpected+=1
                continue
            if num not in received:
                received[num]=time.monotonic()
                timings[num]=round((received[num]-sent_at[num])*1000,2) if num in sent_at else None
    try:
        for seq in range(count):
            payload=prefix+seq.to_bytes(4,"big")+b"P"*196
            sent_at[seq]=time.monotonic()
            s.sendto(payload,TARGETS[service])
            consume()
            time.sleep(interval)
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            consume()
    finally:s.close()
    vals=sorted(v for v in timings.values() if v is not None)
    return {"service":service,"client":index,"sent":count,"received":len(received),
            "missing":sorted(set(range(count))-set(received)),
            "unexpected":unexpected,
            "duration_s":round(time.monotonic()-started,2),
            "p95_echo_ms":vals[int(.95*(len(vals)-1))] if vals else None}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--clients-per-service",type=int,default=3)
    p.add_argument("--count",type=int,default=40)
    p.add_argument("--interval",type=float,default=.04)
    p.add_argument("--bind-ip",default="217.179.6.142",choices=("217.179.6.142","94.183.231.158"))
    a=p.parse_args()
    if not 1<=a.clients_per_service<=32 or not 3<=a.count<=200:
        p.error("bounded test only")
    pairs=[(svc,i) for svc in (1,2) for i in range(a.clients_per_service)]
    with ThreadPoolExecutor(max_workers=len(pairs)) as pool:
        rows=list(pool.map(lambda si:client(si[0],si[1],a.count,a.interval,a.bind_ip),pairs))
    result={"clients":len(rows),"sent":sum(x["sent"] for x in rows),
            "received":sum(x["received"] for x in rows),"rows":rows}
    print("MULTIUSER_TEST_RESULT",json.dumps(result,separators=(",",":")),flush=True)
    raise SystemExit(0 if result["received"]>=int(result["sent"]*.95) else 2)
if __name__=="__main__":main()