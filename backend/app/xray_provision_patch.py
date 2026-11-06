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
    """Use one safe, no-restart mutation contract for every account worker.

    This wrapper is retained because the legacy import-hook executes in
    reseller bot processes as well as the API. Never rewrite only inbound[0]
    or invoke a global Xray restart for a new customer.
    """
    from .xray_hot_client_sync_v1 import hot_client_sync_script

    return hot_client_sync_script(client_id, email)


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
            raw = await module.cmd(
                conn,
                "printf '%s' " + shlex.quote(encoded) + " | base64 -d | python3",
            )
            result = module.json.loads(raw.strip().splitlines()[-1])
            if int(result.get("updated_inbounds") or 0) < 3:
                raise RuntimeError("legacy VLESS hot sync did not cover all inbounds")
            if result.get("changed") and not result.get("hot_applied"):
                raise RuntimeError("legacy VLESS credentials not hot-applied")

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
