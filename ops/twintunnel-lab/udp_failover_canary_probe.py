#!/usr/bin/env python3
"""Canary client for loopback stable UDP frontend; only lab echo endpoint."""
import json
import os
import socket
import time

COUNT=int(os.environ.get('TT_CANARY_COUNT','120'))
if not 10 <= COUNT <= 500: raise SystemExit('TT_CANARY_COUNT out of range')
SENT=0
RECEIVED=set()
LAST_RECV=0.0
sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
sock.bind(("127.0.0.1",0))
sock.settimeout(0.18)
start=time.monotonic()
for n in range(COUNT):
    data=b"TTLB1TT-UDP-CANARY:"+n.to_bytes(4,"big")+(b"Z"*224)
    try:sock.sendto(data,("127.0.0.1",int(os.environ.get("TT_CANARY_PORT","37961"))));SENT+=1
    except OSError:pass
    try:
        packet,_=sock.recvfrom(2000)
        if packet.startswith(b"TTLB1TT-UDP-CANARY:") and len(packet)==247:
            number=int.from_bytes(packet[19:23],"big")
            if 0<=number<COUNT:
                RECEIVED.add(number)
                LAST_RECV=time.monotonic()-start
    except socket.timeout:pass
    if n % 20 == 0:
        print("PROBE_PROGRESS",json.dumps({"sent":SENT,"unique_echo":len(RECEIVED),"elapsed":round(time.monotonic()-start,1)}),flush=True)
    time.sleep(0.08)
# receive any late echoes
until=time.monotonic()+1
while time.monotonic()<until:
    sock.settimeout(0.15)
    try:
        packet,_=sock.recvfrom(2000)
        if packet.startswith(b"TT-UDP-CANARY:") and len(packet)==242:
            num=int.from_bytes(packet[14:18],"big")
            if 0<=num<COUNT:RECEIVED.add(num)
    except socket.timeout:pass
print("PROBE_RESULT",json.dumps({"sent":SENT,"received_unique":len(RECEIVED),
    "missing":sorted(set(range(COUNT))-RECEIVED),
    "loss_pct":round(100*(SENT-len(RECEIVED))/max(SENT,1),2),
    "duration_s":round(time.monotonic()-start,2),
    "last_echo_s":round(LAST_RECV,2)}),flush=True)