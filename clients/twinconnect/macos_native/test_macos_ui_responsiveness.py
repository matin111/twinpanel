"""Static regression checks for responsive native macOS dashboard."""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parent /
          "TwinConnectMacOSNativeDashboard.swift")


class NativeUIResponsivenessTests(unittest.TestCase):
    def test_no_automatic_ping_burst_during_panel_refresh(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("self.pingNodes(targets)", source)
        self.assertIn("func pingAllServers(", source)

    def test_ping_updates_coalesced_before_full_rebuild(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("private func schedulePingRedraw()", source)
        self.assertIn("self.schedulePingRedraw()", source)
        self.assertIn("guard !pingRedrawScheduled else { return }", source)
        self.assertIn("deadline: .now() + 0.3", source)

    def test_cloud_lightweight_render_budget(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('TWINCONNECT_MAC_LIGHTWEIGHT_UI', source)
        self.assertIn('blur.alphaValue = TwinNativeRenderBudget.lightweight ? 0 : 0.14', source)
        self.assertIn('if TwinNativeRenderBudget.lightweight { blur.state = .inactive }', source)
        self.assertIn('if TwinNativeRenderBudget.lightweight { return }', source)
        self.assertIn('box.layer?.shadowOpacity = TwinNativeRenderBudget.lightweight ? 0 :', source)
        self.assertIn('guard !TwinNativeRenderBudget.lightweight,', source)

    def test_ping_process_runs_off_main_thread(self):
        source = (SOURCE.parent / "TwinConnectMacOSNativeDirectory.swift"
                  ).read_text(encoding="utf-8")
        self.assertIn("DispatchQueue.global(qos: .utility).async", source)
        self.assertIn("DispatchQueue.main.async { completion(result) }", source)


if __name__ == "__main__":
    unittest.main()
