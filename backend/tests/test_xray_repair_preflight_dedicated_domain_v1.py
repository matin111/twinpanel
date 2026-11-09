"""Regression: the legacy pre-repair pass must never rewrite a TLS Xray Exit.

This tests the central panel's installer routing only (no SSH or node edits).
"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app import xray_modern_repair_runtime as repair
from app.models import NodeType
from app.routers import provision


class DedicatedXrayRepairRouting(unittest.IsolatedAsyncioTestCase):
    def node(self,domain="v2fin.in88.sbs"):
        return SimpleNamespace(
            id=22,node_type=NodeType.EXIT,xray_domain=domain,
        )

    async def test_dedicated_node_preflight_does_not_inspect_or_mutate_xray(self):
        with (
            patch.object(provision,"existing_ok",new=AsyncMock()) as old_check,
            patch.object(repair,"_listener_line",new=AsyncMock()) as listener,
            patch.object(repair,"_ensure_modern_xray",new=AsyncMock()) as old_build,
        ):
            changed=await repair._reconcile_existing_legacy_xray(
                object(),SimpleNamespace(install_v2ray=True,xray_port=8443),
                self.node(),
            )
        self.assertFalse(changed)
        old_check.assert_not_awaited()
        listener.assert_not_awaited()
        old_build.assert_not_awaited()

    async def test_dedicated_node_allows_canonical_provision_installer(self):
        canonical=AsyncMock(return_value=(
            {"v2ray":{"ok":True}},[],{},
        ))
        with (
            patch.object(repair,"_original_provision_protocols",new=canonical),
            patch.object(repair,"_ensure_modern_xray",new=AsyncMock()) as old_build,
            patch.object(provision,"existing_ok",new=AsyncMock()) as check,
        ):
            result=await repair._provision_protocols_with_xray_reconcile(
                object(),SimpleNamespace(install_v2ray=True,xray_port=8443),
                object(),self.node(),repair=True,
            )
        self.assertEqual(result[0]["v2ray"],{"ok":True})
        canonical.assert_awaited_once()
        old_build.assert_not_awaited()
        check.assert_not_awaited()

    async def test_domainless_legacy_repair_remains_compatible(self):
        xray_ready=AsyncMock(return_value=True)
        with (
            patch.object(provision,"existing_ok",new=AsyncMock(return_value=False)),
            patch.object(repair,"_listener_line",new=AsyncMock(return_value="xray")),
            patch.object(repair,"_ensure_modern_xray",new=xray_ready),
        ):
            changed=await repair._reconcile_existing_legacy_xray(
                object(),SimpleNamespace(install_v2ray=True,xray_port=8443),
                self.node(domain=""),
            )
        self.assertTrue(changed)
        xray_ready.assert_awaited_once()

    async def test_non_exit_never_triggers_xray(self):
        with patch.object(repair,"_ensure_modern_xray",new=AsyncMock()) as old:
            result=await repair._reconcile_existing_legacy_xray(
                object(),SimpleNamespace(install_v2ray=True,xray_port=8443),
                SimpleNamespace(node_type=NodeType.IRAN,xray_domain=None),
            )
        self.assertFalse(result)
        old.assert_not_awaited()


if __name__=="__main__":
    unittest.main()
