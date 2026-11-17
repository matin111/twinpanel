#!/usr/bin/env python3
"""Selector-based concurrent UDP flow-capacity probe for the isolated MUX."""
import argparse
import json
import selectors
import socket
import struct
import time

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--clients-per-service",type=int,default=256)
    p.add_argument("--count",type=int,default=20)
    p.add_argument("--interval",type=float,default=.002)
    p.add_argument("--bind-ip",default="127.0.0.1")
    p.add_argument("--target-ip",default="127.0.0.1")
    p.add_argument("--service1-port",type=int,default=37981)
    p.add_argument("--service2-port",type=int,default=37982)
    a=p.parse_args()
    if not 1<=a.clients_per_service<=256 or not 1<=a.count<=100:
        p.error("bounded capacity test only")
    if not 0<=a.interval<=1:
        p.error("interval must be 0..1 seconds")
    sel=selectors.DefaultSelector()
    states=[]
    for service,port in ((1,a.service1_port),(2,a.service2_port)):
        for index in range(a.clients_per_service):
            sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            sock.bind((a.bind_ip,0))
            sock.setblocking(False)
            state={"service":service,"index":index,"sock":sock,"received":0}
            sel.register(sock,selectors.EVENT_READ,state)
            states.append(state)
    sent=0
    received=0
    missing=0
    duplicates=0
    unexpected=0
    latencies=[]
    started=time.monotonic()
    try:
        for sequence in range(a.count):
            pending={}
            now=time.monotonic()
            for state in states:
                payload=(b"TT-CAPACITY-V1"+
                         struct.pack("!HHI",state["service"],state["index"],sequence)+
                         b"Q"*64)
                state["expected"]=payload
                state["sent_at"]=time.monotonic()
                state["got"]=False
                state["sock"].sendto(payload,(a.target_ip, a.service1_port if state["service"]==1 else a.service2_port))
                pending[state["sock"]]=state
                sent+=1
            deadline=time.monotonic()+5.0
            while pending and time.monotonic()<deadline:
                for key,_ in sel.select(.05):
                    state=key.data
                    try:data,source=state["sock"].recvfrom(1500)
                    except BlockingIOError:continue
                    if data==state["expected"] and state["sock"] in pending:
                        state["got"]=True
                        received+=1
                        latencies.append((time.monotonic()-state["sent_at"])*1000)
                        del pending[state["sock"]]
                    elif data==state["expected"]:
                        duplicates+=1
                    else:
                        unexpected+=1
            missing+=len(pending)
            if a.interval:
                time.sleep(a.interval)
        latencies.sort()
        p95=round(latencies[min(len(latencies)-1,int(.95*(len(latencies)-1)))],2) if latencies else None
        result={"flows":len(states),"count_per_flow":a.count,"sent":sent,
                "received":received,"missing":missing,"duplicates":duplicates,
                "unexpected":unexpected,"p95_ms":p95,
                "duration_s":round(time.monotonic()-started,2)}
        print("MUX_CAPACITY_RESULT "+json.dumps(result,separators=(",",":")),flush=True)
        return 0 if received==sent and not duplicates and not unexpected else 2
    finally:
        for state in states:state["sock"].close()
        sel.close()
if __name__=="__main__":
    raise SystemExit(main())
