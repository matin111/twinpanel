"""Official, SHA256-verified GitHub Release downloads on restricted new Exits.

github.com/.../releases/download returns HTTP 504 on Finland while the
official api.github.com asset endpoint returns HTTP 200 for the SAME exact
pinned package. Only allowlisted upstream repositories, exact release tags,
and metadata SHA256 digests may be fetched. The caller additionally verifies
its fixed known-good package SHA256 before executing anything.
"""
from __future__ import annotations

import base64
import shlex

_REMOTE_ASSET_FETCH = r'''
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ALLOW = {
    ("enfein", "mieru"),
    ("trusttunnel", "trusttunnel"),
    ("sudoku-ascii", "sudoku"),
}
MAX_BYTES = 70 * 1024 * 1024
HEADERS = {
    "User-Agent": "TwinPanel-Verified-GitHub-Asset",
    "X-GitHub-Api-Version": "2022-11-28",
}
if len(sys.argv) != 3:
    raise SystemExit("GITHUB_ASSET_INVALID_ARGS")

source, destination = sys.argv[1:]
parsed = urllib.parse.urlsplit(source)
match = re.fullmatch(
    r"/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)/releases/download/"
    r"(v[0-9]+(?:[.][0-9]+){2})/([A-Za-z0-9_.-]+)",
    parsed.path,
)
if (
    parsed.scheme != "https" or parsed.netloc.lower() != "github.com"
    or parsed.query or parsed.fragment or not match
    or (match.group(1).lower(),match.group(2).lower()) not in ALLOW
):
    raise SystemExit("GITHUB_ASSET_UNTRUSTED_RELEASE_URL")
owner, repo, tag, filename = match.groups()


def request(url, accept="application/vnd.github+json"):
    return urllib.request.Request(
        url,
        headers={**HEADERS, "Accept": accept},
    )


metadata_url = (
    "https://api.github.com/repos/"
    + owner + "/" + repo + "/releases/tags/" + tag
)
with urllib.request.urlopen(request(metadata_url),timeout=28) as response:
    metadata = json.load(response)
assets = [
    item for item in metadata.get("assets",[]) if isinstance(item,dict)
    and item.get("name") == filename
]
if len(assets)!=1 or str(metadata.get("tag_name") or "")!=tag:
    raise SystemExit("GITHUB_ASSET_TAG_OR_NAME_MISMATCH")
asset = assets[0]
expected_size=asset.get("size")
ident=asset.get("id")
digest=str(asset.get("digest") or "")
if (
    not isinstance(ident,int) or ident<=0
    or not isinstance(expected_size,int) or not 1024<expected_size<=MAX_BYTES
    or not re.fullmatch("sha256:[a-fA-F0-9]{64}",digest)
):
    raise SystemExit("GITHUB_ASSET_DIGEST_INVALID")

url = "https://api.github.com/repos/"+owner+"/"+repo+"/releases/assets/"+str(ident)
target = Path(destination)
if not target.is_absolute() or not str(target).startswith("/tmp/"):
    raise SystemExit("GITHUB_ASSET_OUTPUT_PATH_UNSAFE")
partial = target.with_name(target.name + ".verified.partial")
size = 0
sha = hashlib.sha256()
try:
    with urllib.request.urlopen(
        request(url, "application/octet-stream"), timeout=45,
    ) as response, partial.open("wb") as handle:
        os.chmod(partial,0o600)
        while True:
            chunk=response.read(1024*1024)
            if not chunk:break
            size += len(chunk)
            if size > MAX_BYTES:
                raise RuntimeError("GITHUB_ASSET_TOO_LARGE")
            sha.update(chunk)
            handle.write(chunk)
        handle.flush()
        os.fsync(handle.fileno())
    if size != expected_size or sha.hexdigest() != digest[7:].lower():
        raise RuntimeError("GITHUB_ASSET_SHA256_MISMATCH")
    os.replace(partial,target)
finally:
    partial.unlink(missing_ok=True)
print("GITHUB_OFFICIAL_ASSET_VERIFIED",owner+"/"+repo,tag)
'''


def official_github_asset_fetch_command(url_shell: str, output_shell: str) -> str:
    """Return a single remote shell pipeline; args are trusted installer vars."""
    if url_shell not in {'"$url"', '"$asset_url"'} or output_shell != '"$tmp"':
        raise ValueError("unsupported release asset shell bindings")
    try:
        compile(_REMOTE_ASSET_FETCH, "<github-verified-asset-fetch>", "exec")
    except SyntaxError as exc:
        raise RuntimeError("GITHUB_VERIFIED_ASSET_HELPER_SYNTAX_INVALID") from exc
    payload=base64.b64encode(_REMOTE_ASSET_FETCH.encode()).decode("ascii")
    return (
        "printf '%s' " + shlex.quote(payload)
        + " | base64 -d | python3 - " + url_shell + " " + output_shell
    )
