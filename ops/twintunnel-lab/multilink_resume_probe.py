#!/usr/bin/env python3
"""Isolated multi-link TCP integrity probe. Sends only to loopback Rakhsh lab forward."""
import concurrent.futures
import json
import socket
import statistics
import threading
import time

COUNT = 8
BLOCKS = 95
barrier = threading.Barrier(COUNT + 1)

def exactly(s, length):
    out = bytearray()
    while len(out) < length:
        buf = s.recv(length-len(out))
        if not buf:
            raise RuntimeError("unexpected EOF")
        out.extend(buf)
    return bytes(out)

def worker(idx):
    started = time.monotonic()
    blocks = 0
    rtts = []
    try:
        with socket.create_connection(("127.0.0.1", 37941), timeout=10) as s:
            s.settimeout(12)
            barrier.wait(timeout=10)
            for n in range(BLOCKS):
                payload = (f"TT-MULTILINK-{idx:02d}-{n:04d}:".encode() + bytes([65+idx])*2048)
                ts = time.monotonic()
                s.sendall(payload)
                returned = exactly(s,len(payload))
                if returned != payload:
                    raise RuntimeError(f"echo mismatch at block {n}")
                blocks += 1
                rtts.append(round((time.monotonic()-ts)*1000,2))
                time.sleep(0.02)
        return {"stream":idx,"ok":True,"blocks":blocks,"p95_ms":round(sorted(rtts)[int(.95*(len(rtts)-1))],1),"max_ms":round(max(rtts),1),"duration_s":round(time.monotonic()-started,2)}
    except Exception as e:
        return {"stream":idx,"ok":False,"blocks":blocks,"error":f"{type(e).__name__}: {str(e)[:160]}"}

def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=COUNT) as ex:
        future = [ex.submit(worker,i) for i in range(COUNT)]
        try:
            barrier.wait(timeout=10)
            print("STREAMS_ESTABLISHED",COUNT,flush=True)
        except threading.BrokenBarrierError:
            print("STREAM_SETUP_FAILED",flush=True)
        rows = [f.result(timeout=60) for f in future]
    print("RESULTS",json.dumps({"all_ok":all(x["ok"] and x["blocks"]==BLOCKS for x in rows),
      "expected_blocks":COUNT*BLOCKS,"completed_blocks":sum(x["blocks"] for x in rows),
      "failed_streams":sum(not x["ok"] for x in rows),
      "streams":rows},ensure_ascii=False),flush=True)
    raise SystemExit(0 if all(x["ok"] and x["blocks"]==BLOCKS for x in rows) else 2)

if __name__ == "__main__":
    main()