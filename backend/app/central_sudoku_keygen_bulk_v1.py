"""One-SSH Sudoku key generation for missing central subscription identities.

The remote executes up to 16 independent local keygens concurrently and
returns private material only over the authenticated SSH channel. The
controller immediately encrypts/commits it before any service is changed.
Existing identities are never generated twice.
"""
from __future__ import annotations
import asyncio
import base64
import json

MAX_KEYS = 3000


def validate_ids(ids):
    if not isinstance(ids,list) or not 1<=len(ids)<=MAX_KEYS:
        raise ValueError("SUDOKU_KEYGEN_INVALID_BATCH")
    if any(type(sid) is not int or sid<=0 for sid in ids) or len(set(ids))!=len(ids):
        raise ValueError("SUDOKU_KEYGEN_INVALID_IDENTITIES")


def remote_source(binary="/usr/local/bin/twinpanel-sudoku"):
    source=r'''import concurrent.futures,json,re,subprocess,sys
from pathlib import Path
BINARY=Path(__BINARY__)
ids=json.load(sys.stdin)
if not isinstance(ids,list) or not 1<=len(ids)<=3000 or any(
    type(sid) is not int or sid<=0 for sid in ids) or len(set(ids))!=len(ids):
    raise SystemExit("KEYGEN_BAD_BATCH")
if BINARY.is_symlink() or not BINARY.is_file():
    raise SystemExit("SUDOKU_BINARY_MISSING")
labels=("Available Private Key","Master Private Key","Master Public Key")
def one(sid):
    p=subprocess.run([str(BINARY),"-keygen"],capture_output=True,
        text=True,timeout=40,check=False)
    if p.returncode:raise RuntimeError("SUDOKU_KEYGEN_FAILED")
    fields={}
    for label in labels:
        found=re.search(re.escape(label)+r":\s*([0-9a-fA-F]+)\s*$",
                        p.stdout,re.M)
        if not found:raise RuntimeError("SUDOKU_KEYGEN_PARSE_FAILED")
        fields[label]=found.group(1)
    return {"subscription_id":sid,"client":fields[labels[0]],
            "master_private":fields[labels[1]],
            "master_public":fields[labels[2]]}
with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
    result=list(pool.map(one,ids))
print(json.dumps({"keys":result},separators=(",",":")))
'''
    return source.replace("__BINARY__",repr(binary))


async def generate_many(conn,ids):
    validate_ids(ids)
    encoded=base64.b64encode(remote_source().encode()).decode("ascii")
    proc=await asyncio.wait_for(conn.create_process(
        "python3 -c \"$(printf '%s' '"+encoded+"' | base64 -d)\""),
        timeout=25,
    )
    proc.stdin.write(json.dumps(ids))
    proc.stdin.write_eof()
    result=await asyncio.wait_for(proc.wait(),timeout=650)
    if result.exit_status:
        raise RuntimeError("SUDOKU_KEYGEN_REMOTE_FAILED")
    try:
        doc=json.loads((result.stdout or "").strip().splitlines()[-1])
        rows=doc["keys"]
    except (ValueError,IndexError,KeyError,TypeError) as exc:
        raise RuntimeError("SUDOKU_KEYGEN_REMOTE_RESULT_INVALID") from exc
    if (not isinstance(rows,list) or
            [row.get("subscription_id") for row in rows]!=ids):
        raise RuntimeError("SUDOKU_KEYGEN_IDENTITY_MISMATCH")
    keys={}
    for row in rows:
        for field in ("client","master_private","master_public"):
            val=row.get(field)
            if not isinstance(val,str) or not 32<=len(val)<=512 or any(
                ch not in "0123456789abcdefABCDEF" for ch in val):
                raise RuntimeError("SUDOKU_KEYGEN_MALFORMED_KEY")
        keys[row["subscription_id"]]=row
    return keys
