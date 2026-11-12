"""Production collectors must not spin continuously when a fleet sweep overruns."""
from __future__ import annotations

from pathlib import Path
from unittest import TestCase, main
import ast

BACKEND=Path(__file__).resolve().parents[1]


class AccountingWorkerCooldownTests(TestCase):
    def test_five_collectors_keep_accurate_counters_but_rest_after_overrun(self):
        files=[
            "scripts/twinpanel_mieru_fast_presence_worker.py",
            "scripts/twinpanel_naive_fast_presence_worker.py",
            "scripts/twinpanel_sudoku_fast_presence_worker.py",
            "app/services/modern_quota_runtime_v314.py",
            "app/services/singbox_native_accounting_v265.py",
        ]
        for relative in files:
            with self.subTest(file=relative):
                code=(BACKEND/relative).read_text(encoding="utf-8")
                ast.parse(code)
                self.assertIn("min_rest = 15.0 if result is None",code) if relative.startswith("app/") else self.assertIn(
                    "min_rest = 15.0 if report is None",code)
                self.assertIn("else 5.0",code)
                self.assertIn("await asyncio.sleep(",code)

    def test_trusttunnel_missing_session_prefetch_and_zero_epoch_baseline(self):
        source=(BACKEND/"app/services/modern_quota_runtime_v257.py").read_text()
        self.assertIn('QuotaSession.protocol == "trusttunnel"',source)
        self.assertIn("if proven_bytes == 0:",source)
        self.assertIn("cursor.counter_epoch = epoch",source)
        self.assertIn('"event": False',source)


if __name__=="__main__":
    main()
