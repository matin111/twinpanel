"""Regression coverage for the blog editor's extended text storage.

Run without a database: isolate the template sanitizer to exercise its real
implementation rather than mocking the persistence boundary.
"""
import ast
import math
import re
import unittest
from pathlib import Path
from typing import Any


def load_cleaner():
    path = Path(__file__).resolve().parents[1] / "app/routers/storefront_settings.py"
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    function = next(x for x in module.body if isinstance(x, ast.FunctionDef) and x.name == "_clean_template_value")
    defaults = {"MAX_TEMPLATE_DEPTH": 5, "MAX_TEMPLATE_FIELDS": 256,
                "MAX_TEMPLATE_LIST": 96, "MAX_TEMPLATE_STRING": 5000,
                "MAX_NOVA_BLOG_BODY": 30000}
    drop = object()
    globals_ = {**defaults, "Any": Any, "math": math, "_DROP": drop,
                "OPTION_KEY_RE": re.compile(r"^[A-Za-z0-9_.-]{1,100}$")}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), globals_)
    return globals_["_clean_template_value"]


class NovaBlogStorageTests(unittest.TestCase):
    def test_extended_body_and_regular_settings_remain_bounded(self):
        clean = load_cleaner()
        payload = {"nova_articles": [{"slug": "how-to", "body": "x" * 21000,
                                     "title": "A" * 9000}],
                   "welcome_message": "b" * 9000}
        result = clean(payload)
        self.assertEqual(len(result["nova_articles"][0]["body"]), 21000)
        self.assertEqual(len(result["nova_articles"][0]["title"]), 5000)
        self.assertEqual(len(result["welcome_message"]), 5000)

    def test_article_body_has_finite_upper_limit(self):
        clean = load_cleaner()
        result = clean({"nova_articles": [{"body": "x" * 35000}]})
        self.assertEqual(len(result["nova_articles"][0]["body"]), 30000)

    def test_unrelated_body_field_keeps_old_limit(self):
        clean = load_cleaner()
        result = clean({"message": {"body": "x" * 9000}})
        self.assertEqual(len(result["message"]["body"]), 5000)


if __name__ == "__main__":
    unittest.main()
