"""Regression tests for cross-process modern installation serialization."""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.modern_node_install_lock import NodeInstallBusy, exclusive_node_install


def test_same_node_rejects_overlap_without_waiting():
    async def scenario():
        with tempfile.TemporaryDirectory() as temp:
            with patch("app.modern_node_install_lock.LOCK_DIRECTORY", Path(temp)):
                async with exclusive_node_install(12):
                    with pytest.raises(NodeInstallBusy):
                        async with exclusive_node_install(12):
                            pass
                async with exclusive_node_install(12):
                    pass
    asyncio.run(scenario())


def test_different_nodes_are_independent():
    async def scenario():
        with tempfile.TemporaryDirectory() as temp:
            with patch("app.modern_node_install_lock.LOCK_DIRECTORY", Path(temp)):
                async with exclusive_node_install(12):
                    async with exclusive_node_install(13):
                        pass
    asyncio.run(scenario())


def test_lock_released_on_exception():
    async def scenario():
        with tempfile.TemporaryDirectory() as temp:
            with patch("app.modern_node_install_lock.LOCK_DIRECTORY", Path(temp)):
                with pytest.raises(RuntimeError, match="intentional"):
                    async with exclusive_node_install(12):
                        raise RuntimeError("intentional")
                async with exclusive_node_install(12):
                    pass
    asyncio.run(scenario())


def test_invalid_node_id_rejected():
    async def scenario():
        with pytest.raises(ValueError):
            async with exclusive_node_install(0):
                pass
    asyncio.run(scenario())
