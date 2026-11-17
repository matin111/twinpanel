#!/usr/bin/env python3
"""Isolated TwinTunnel multi-user UDP transport proof of concept.

Two-ended, authenticated envelopes over separate Shabdiz GRE and UDP lab
carriers. Each user is identified by an opaque 64-bit flow ID; a stable
per-user UDP socket at the exit preserves the server-facing source port
across path loss. Duplicate packets are rejected with a replay window.

LAB ONLY: no production integration, no fragmentation, no capacity claims.
"""
import argparse
import collections
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import selectors
import signal
import socket
import struct
import time

MAGIC = b"TTMUXV01"
HEADER = struct.Struct("!8sBBQQ")
TAG_LEN = 16
MAX_PAYLOAD = 1250
MAX_FLOWS = 64
TTL = 120.0
PATH_TTL = 12.0
PATHS = ((1, ("127.0.0.1", 37921)), (2, ("127.0.0.1", 37933)))
SERVICES = {1: 37981, 2: 37982}
REPORT_INTERVAL = 5.0
MAX_RECV_BATCH = 48
KERNEL_UDP_BUFFER = 1024 * 1024
ACK_FLAG = 0x80
ACK_PAYLOAD = b"\x01"
VALID_SERVICE_CODES = (1, 2, 129, 130)
RETRY_INTERVAL = 0.24
MAX_PENDING_PER_FLOW = 256
MAX_RETRIES = 2
ACK_RESEND_INTERVAL = 0.16


class ReplayWindow:
    def __init__(self):
        self.top = -1
        self.bits = 0

    def accept(self, sequence):
        if sequence > self.top:
            shift = sequence - self.top
            self.bits = ((self.bits << shift) | 1) & ((1 << 512) - 1)
            self.top = sequence
            return True
        delta = self.top - sequence
        if delta >= 512 or self.bits & (1 << delta):
            return False
        self.bits |= (1 << delta)
        return True

    def was_delivered(self, sequence):
        if self.top < 0 or sequence > self.top:
            return False
        delta = self.top - sequence
        return delta < 512 and bool(self.bits & (1 << delta))


class Codec:
    def __init__(self, secret):
        if len(secret) != 32:
            raise ValueError("Expected 32-byte private test secret")
        self.secret = secret

    def encode(self, service, path, flow, sequence, payload):
        if service not in VALID_SERVICE_CODES or path not in (1, 2):
            raise ValueError("unsupported service/path")
        if not (0 < len(payload) <= MAX_PAYLOAD):
            raise ValueError("invalid data length")
        head = HEADER.pack(MAGIC, service, path, flow, sequence)
        data = head + payload
        return data + hmac.new(self.secret, data, hashlib.sha256).digest()[:TAG_LEN]

    def decode(self, data):
        if not (HEADER.size + TAG_LEN < len(data) <= HEADER.size + TAG_LEN + MAX_PAYLOAD):
            return None
        body, tag = data[:-TAG_LEN], data[-TAG_LEN:]
        expected = hmac.new(self.secret, body, hashlib.sha256).digest()[:TAG_LEN]
        if not hmac.compare_digest(tag, expected):
            return None
        magic, service, path, flow, seq = HEADER.unpack(body[:HEADER.size])
        if magic != MAGIC or service not in VALID_SERVICE_CODES or path not in (1,2):
            return None
        return service, path, flow, seq, body[HEADER.size:]


class Flow:
    def __init__(self, flow_id, service, client=None):
        self.flow_id = flow_id
        self.service = service
        self.client = client
        self.socket = None
        self.seq_send = 0
        self.recv_window = ReplayWindow()
        self.paths = {}
        self.pending_down = {} # sequence -> (payload, last_sent_at, retries)
        self.recent_acks = {} # sequence -> last acknowledgement timestamp
        self.updated = time.monotonic()

    def next_seq(self):
        seq = self.seq_send
        self.seq_send += 1
        return seq


class Mux:
    def __init__(self, args):
        self.args = args
        secret = bytes.fromhex(Path(args.secret_file).read_text().strip())
        self.codec = Codec(secret)
        self.sel = selectors.DefaultSelector()
        self.flows = {}
        self.clients = {}
        self.backends = {}
        self.listeners = {}
        self.stats = collections.Counter()
        self.running = True
        self.started = time.monotonic()
        if args.role == "entry":
            self._open_entry()
        else:
            self._open_exit()

    def _register(self, sock, typ, ident):
        # Per-process socket buffers, without changing host sysctls.
        if typ != "target":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, KERNEL_UDP_BUFFER)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, KERNEL_UDP_BUFFER)
        sock.setblocking(False)
        self.sel.register(sock, selectors.EVENT_READ, (typ, ident))

    def _open_entry(self):
        for service, port in SERVICES.items():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind((self.args.bind_ip, port))
            self.listeners[service] = s
            self._register(s, "client", service)
        for path, dest in PATHS:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(dest)
            self.backends[path] = s
            self._register(s, "back", path)

    def _open_exit(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 37922))
        self.listeners[0] = s
        self._register(s, "transport", 0)
        self.targets = {1: ("127.0.0.1", self.args.wg_target),
                        2: ("127.0.0.1", self.args.ovpn_target)}

    def _new_flow(self, service, client=None, flow_id=None):
        if len(self.flows) >= MAX_FLOWS:
            self.stats["flow_limit"] += 1
            return None
        if flow_id is None:
            while True:
                flow_id = secrets.randbits(64)
                if flow_id and flow_id not in self.flows:
                    break
        elif not flow_id or flow_id in self.flows:
            self.stats["bad_flow_id"] += 1
            return None
        f = Flow(flow_id, service, client)
        self.flows[flow_id] = f
        self.stats["flows_created"] += 1
        return f

    def _entry_client(self, service, data, source):
        if source[0] != self.args.allow_source:
            self.stats["source_rejected"] += 1
            return
        if not (0 < len(data) <= MAX_PAYLOAD):
            self.stats["invalid_size"] += 1
            return
        key = (service, source)
        f = self.clients.get(key)
        if f is None:
            f = self._new_flow(service, source)
            if f is None:
                return
            self.clients[key] = f
        f.updated = time.monotonic()
        self.stats["client_packets"] += 1
        seq = f.next_seq()
        for path, sock in self.backends.items():
            try:
                sock.send(self.codec.encode(service,path,f.flow_id,seq,data))
                self.stats["up_sent_path_"+str(path)] += 1
            except (OSError,ValueError):
                self.stats["path_send_error"] += 1

    def _entry_reply(self, path, data):
        frame = self.codec.decode(data)
        if frame is None:
            self.stats["auth_rejected"] += 1
            return
        service, frame_path, fid, seq, payload = frame
        if frame_path != path:
            self.stats["path_mismatch"] += 1
            return
        f = self.flows.get(fid)
        if f is None or f.service != service:
            self.stats["orphan_reply"] += 1
            return
        now = time.monotonic()
        if not f.recv_window.accept(seq):
            if f.recv_window.was_delivered(seq):
                self.stats["duplicates_down"] += 1
                self._ack_downstream(f,seq,now)
            else:
                self.stats["stale_down"] += 1
            return
        f.updated = now
        try:
            self.listeners[service].sendto(payload, f.client)
            self.stats["client_replies"] += 1
            self._ack_downstream(f,seq,now)
        except OSError:
            self.stats["client_send_error"] += 1

    def _ack_downstream(self,f,seq,now):
        """Acknowledge a delivered reply over both available authenticated paths."""
        if now-f.recent_acks.get(seq,-100.0)<ACK_RESEND_INTERVAL:
            return
        f.recent_acks[seq]=now
        if len(f.recent_acks)>MAX_PENDING_PER_FLOW*2:
            for old_seq,ts in list(f.recent_acks.items()):
                if now-ts>2.0:
                    del f.recent_acks[old_seq]
            if len(f.recent_acks)>MAX_PENDING_PER_FLOW*2:
                f.recent_acks.clear()
        for path,sock in self.backends.items():
            try:
                sock.send(self.codec.encode(f.service|ACK_FLAG,path,f.flow_id,seq,ACK_PAYLOAD))
                self.stats["ack_sent_path_"+str(path)] += 1
            except OSError:
                self.stats["ack_send_error"] += 1

    def _exit_transport(self, data, source):
        # Preserve the old isolated GRE/UDP echo tests.
        if data.startswith(b"TTLB1") and 17 <= len(data) <= 1400:
            self.listeners[0].sendto(data, source)
            self.stats["echo_compat"] += 1
            return
        frame = self.codec.decode(data)
        if frame is None:
            self.stats["auth_rejected"] += 1
            return
        service, path, fid, seq, payload = frame
        if service & ACK_FLAG:
            base_service = service & ~ACK_FLAG
            f = self.flows.get(fid)
            if f is None or f.service != base_service or payload != ACK_PAYLOAD:
                self.stats["invalid_ack"] += 1
                return
            f.paths[path] = (source,time.monotonic())
            if f.pending_down.pop(seq,None) is not None:
                self.stats["acks_received"] += 1
            else:
                self.stats["duplicate_or_late_ack"] += 1
            return
        f = self.flows.get(fid)
        if f is None:
            f = self._new_flow(service, flow_id=fid)
            if f is None:
                return
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(self.targets[service])
            f.socket = s
            self._register(s, "target", fid)
        if f.service != service:
            self.stats["service_mismatch"] += 1
            return
        now = time.monotonic()
        f.paths[path] = (source, now)
        f.updated = now
        if not f.recv_window.accept(seq):
            self.stats["duplicates_up"] += 1
            return
        try:
            f.socket.send(payload)
            self.stats["server_packets"] += 1
        except OSError:
            self.stats["server_send_error"] += 1

    def _send_downstream(self,f,seq,data,now,is_retry=False):
        n = 0
        for path,(remote,seen) in list(f.paths.items()):
            if now - seen > PATH_TTL:
                continue
            try:
                self.listeners[0].sendto(
                    self.codec.encode(f.service,path,f.flow_id,seq,data),remote)
                self.stats["down_sent_path_"+str(path)] += 1
                n += 1
            except OSError:
                self.stats["return_send_error"] += 1
        if is_retry and n:
            self.stats["retry_rounds"] += 1
        return n

    def _exit_target(self, fid, data):
        f = self.flows.get(fid)
        if f is None:
            return
        if not (0 < len(data) <= MAX_PAYLOAD):
            self.stats["invalid_size"] += 1
            return
        now = time.monotonic()
        f.updated = now
        seq = f.next_seq()
        n = self._send_downstream(f,seq,data,now)
        if n and len(f.pending_down)<MAX_PENDING_PER_FLOW:
            f.pending_down[seq] = (data,now,0)
        elif len(f.pending_down)>=MAX_PENDING_PER_FLOW:
            self.stats["pending_overflow"] += 1

    def _retry_pending(self,now):
        """Retry only unacknowledged downstream packets, bounded by flow/time."""
        if self.args.role!="exit":
            return
        for f in list(self.flows.values()):
            for seq,(payload,last_sent,retries) in list(f.pending_down.items()):
                if now-last_sent < RETRY_INTERVAL:
                    continue
                if retries>=MAX_RETRIES:
                    del f.pending_down[seq]
                    self.stats["down_unacked"] += 1
                    continue
                self._send_downstream(f,seq,payload,now,is_retry=True)
                f.pending_down[seq] = (payload,now,retries+1)

    def _expire(self, now):
        for fid,f in list(self.flows.items()):
            if now - f.updated <= TTL:
                continue
            if f.socket:
                self.sel.unregister(f.socket)
                f.socket.close()
            if f.client:
                self.clients.pop((f.service, f.client),None)
            del self.flows[fid]
            self.stats["expired"] += 1

    def stop(self,*_):
        self.running = False

    def _drain_ready_socket(self, key):
        """Drain a bounded burst from each ready socket while preserving fairness."""
        typ, ident = key.data
        processed = 0
        for _ in range(MAX_RECV_BATCH):
            try:
                data, addr = key.fileobj.recvfrom(1600)
            except BlockingIOError:
                break
            except OSError:
                self.stats["read_error"] += 1
                break
            processed += 1
            if typ=="client":
                self._entry_client(ident,data,addr)
            elif typ=="back":
                self._entry_reply(ident,data)
            elif typ=="transport":
                self._exit_transport(data,addr)
            elif typ=="target":
                self._exit_target(ident,data)
        if processed == MAX_RECV_BATCH:
            self.stats["full_recv_batches"] += 1
        return processed

    def run(self):
        print("TT_MUX_READY role="+self.args.role+" lab_only=true",flush=True)
        last_report=self.started
        try:
            while self.running and time.monotonic()-self.started<self.args.duration:
                for key,_ in self.sel.select(timeout=0.05):
                    self._drain_ready_socket(key)
                now=time.monotonic()
                self._retry_pending(now)
                if now-last_report>=REPORT_INTERVAL:
                    self._expire(now)
                    print("TT_MUX_STATS flows="+str(len(self.flows))+" "+str(dict(self.stats)),flush=True)
                    last_report=now
        finally:
            print("TT_MUX_FINAL flows="+str(len(self.flows))+" "+str(dict(self.stats)),flush=True)
            self.sel.close()
            for f in self.flows.values():
                if f.socket:
                    f.socket.close()
            for s in list(self.listeners.values()) + list(self.backends.values()):
                s.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--role",required=True,choices=("entry","exit"))
    p.add_argument("--secret-file",default="/etc/twintunnel-test/udp-mux-key.hex")
    p.add_argument("--bind-ip",default="94.183.231.158")
    p.add_argument("--allow-source",default="217.179.6.142")
    p.add_argument("--wg-target",type=int,default=37983)
    p.add_argument("--ovpn-target",type=int,default=37984)
    p.add_argument("--duration",type=int,default=300)
    args=p.parse_args()
    if not 10<=args.duration<=900:
        p.error("duration must be 10..900 seconds")
    mux=Mux(args)
    signal.signal(signal.SIGTERM,mux.stop)
    signal.signal(signal.SIGINT,mux.stop)
    mux.run()


if __name__=="__main__":
    main()