"""Static regression checks for safe default palette upgrades.

These tests intentionally avoid a live database. They lock the default palette
and preserve explicit per-owner appearance rows across panel releases.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "central_app_appearance.py"


def _definitions():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {"DEFAULTS", "_LEGACY_DEFAULTS", "_PALETTE_KEYS"}
    functions = {"_legacy_default", "_legacy_brand_pair"}
    selected = [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id in names
                for target in node.targets)
        or isinstance(node, ast.FunctionDef) and node.name in functions
    ]
    env = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), env)
    return env


def test_default_app_colors_are_slate_ocean():
    values = _definitions()["DEFAULTS"]
    assert {key: values[key] for key in (
        "primary_color", "secondary_color", "button_color",
        "background_color", "surface_color",
    )} == {
        "primary_color": "#5CC8B7",
        "secondary_color": "#81BDD4",
        "button_color": "#479E9B",
        "background_color": "#0E1E2B",
        "surface_color": "#193641",
    }


def test_only_untouched_previous_palettes_are_migrated():
    env = _definitions()
    was_default = env["_legacy_default"]
    assert was_default({
        "primary_color": "#7c3aed",
        "secondary_color": "#4f46e5",
        "button_color": "#7c3aed",
        "background_color": "#101018",
        "surface_color": "#20202a",
    })
    assert was_default({
        "primary_color": "#548BA4",
        "secondary_color": "#65B7B2",
        "button_color": "#3F879B",
        "background_color": "#121F2B",
        "surface_color": "#203544",
    })
    assert not was_default({
        "primary_color": "#123456", "secondary_color": "#ABCDEF",
        "button_color": "#123456", "background_color": "#101018",
        "surface_color": "#20202A",
    })
    assert env["_legacy_brand_pair"]("#7C3AED", "#4F46E5")
    assert not env["_legacy_brand_pair"]("#123456", "#654321")


def test_existing_custom_metadata_is_not_erased():
    source = SOURCE.read_text(encoding="utf-8")
    assert "return {**saved, **{key: DEFAULTS[key] for key in _PALETTE_KEYS}}" in source
    assert "if _legacy_default(saved) else saved" in source
    assert "def save_appearance(" in source
    assert "def reset_appearance(" in source
