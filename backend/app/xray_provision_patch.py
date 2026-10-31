from __future__ import annotations

import importlib.abc
import importlib.machinery
import shlex
import sys
from types import ModuleType
from typing import Any


TARGET_MODULE = "app.routers.account_delivery"
PATCH_MARKER = "TWINPANEL_XRAY_PROVISION_SCRIPT_FIX_V1"


def _build_xray_mutation_script(email: str, client_id: str) -> str:
    """Build a syntactically valid Python mutation script for Xray clients.

    The legacy implementation embedded literal ``\\n`` sequences in the
    generated program. Python interpreted those as line-continuation
    characters and failed with SyntaxError before Xray could be restarted.
    Keep this builder small and independently testable so the regression is
    locked down without touching Xray's dataplane design.
    """
    return "\n".join(
        [
            "import json",
            "p='/usr/local/etc/xray/config.json'",
            "with open(p) as f:",
            "    d=json.load(f)",
            "clients=d['inbounds'][0]['settings'].setdefault('clients', [])",
            (
                "clients[:]=[c for c in clients "
                f"if isinstance(c, dict) and c.get('email')!={email!r}]"
            ),
            f"clients.append({{'id': {client_id!r}, 'email': {email!r}}})",
            "with open(p, 'w') as f:",
            "    json.dump(d, f, indent=2)",
            "",
        ]
    )


def _patch_account_delivery(module: ModuleType) -> None:
    if getattr(module, PATCH_MARKER, False):
        return

    async def _fixed_xray(
        db: Any,
        node: Any,
        sub: Any,
        user: Any,
        client_id: str,
    ) -> dict[str, Any]:
        conn = await module.ssh_connect_saved(node, db)
        try:
            email = f"mv-{sub.id}@twinpanel"
            script = _build_xray_mutation_script(email, client_id)

            # Fail closed locally before mutating a remote Xray file.
            compile(script, "<twinpanel-xray-mutation>", "exec")

            encoded = module.base64.b64encode(script.encode()).decode()
            await module.cmd(
                conn,
                (
                    "printf '%s' "
                    + shlex.quote(encoded)
                    + " | base64 -d | python3 && systemctl restart xray"
                ),
            )

            host, port = module._tunnel_access_endpoint(db, node, "v2ray")
            username_part = module._download_filename_part(
                sub.account_username or module._safe_username(sub, user),
                f"user{sub.id}",
            )
            country_part = module._country_download_name(node)
            profile_name = f"{username_part}-{country_part}"
            uri = (
                f"vless://{client_id}@{host}:{port}"
                f"?encryption=none&type=tcp"
                f"#{profile_name}"
            )
            return {
                "node_id": node.id,
                "node": node.name,
                "server": host,
                "server_ip": host,
                "port": port,
                "uuid": client_id,
                "uri": uri,
            }
        finally:
            conn.close()
            await conn.wait_closed()

    _fixed_xray.__name__ = "_xray"
    _fixed_xray.__qualname__ = "_xray"
    module._xray = _fixed_xray
    setattr(module, PATCH_MARKER, True)
    print(
        f"{PATCH_MARKER}_ACTIVE generated_script=real_newlines "
        "preflight_compile=1 preserve_existing_contract=1",
        flush=True,
    )


class _AccountDeliveryPatchLoader(importlib.abc.Loader):
    def __init__(self, original_loader: importlib.abc.Loader, finder: Any):
        self._original_loader = original_loader
        self._finder = finder

    def create_module(self, spec):
        create_module = getattr(self._original_loader, "create_module", None)
        return create_module(spec) if create_module else None

    def exec_module(self, module: ModuleType) -> None:
        self._original_loader.exec_module(module)
        _patch_account_delivery(module)
        try:
            sys.meta_path.remove(self._finder)
        except ValueError:
            pass


class _AccountDeliveryPatchFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):
        if fullname != TARGET_MODULE:
            return None

        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return None

        spec.loader = _AccountDeliveryPatchLoader(spec.loader, self)
        return spec


def install() -> None:
    loaded = sys.modules.get(TARGET_MODULE)
    if loaded is not None:
        _patch_account_delivery(loaded)
        return

    if any(isinstance(item, _AccountDeliveryPatchFinder) for item in sys.meta_path):
        return

    sys.meta_path.insert(0, _AccountDeliveryPatchFinder())
