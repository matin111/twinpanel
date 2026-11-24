#!/usr/bin/env python3
"""Install the existing iOS Flutter channel in a generated Runner safely."""
from pathlib import Path
import re
root = Path(__file__).resolve().parents[1]
app = root / "ios/Runner/AppDelegate.swift"
source = app.read_text()
if "final class TwinConnectIOSVpnBridge" in source:
    print("iOS native bridge already installed")
    raise SystemExit(0)
native = "\n".join((root / "ios_native" / f).read_text()
                   for f in ("TwinConnectIOSVpnBridge.swift", "TwinConnectIOSVPNControl.swift"))
native = re.sub(r"^import (Foundation|Flutter|NetworkExtension|Security)\n", "", native, flags=re.M)
modern = re.search(r"GeneratedPluginRegistrant\.register\(with:\s*engineBridge\.pluginRegistry\)", source)
legacy = re.search(r"GeneratedPluginRegistrant\.register\(with:\s*self\)", source)
if modern and not legacy:
    anchor = modern
    registration = """
    if let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "TwinConnectIOSVpnBridge") {
        TwinConnectIOSVpnBridge.register(binaryMessenger: registrar.messenger())
    }
"""
elif legacy and not modern:
    anchor = legacy
    registration = """
    if let controller = window?.rootViewController as? FlutterViewController {
        TwinConnectIOSVpnBridge.register(binaryMessenger: controller.binaryMessenger)
    }
"""
else:
    raise SystemExit("Unsupported Flutter AppDelegate template")
source = source[:anchor.end()] + "\n" + registration + source[anchor.end():]
app.write_text("import Foundation\nimport NetworkExtension\nimport Security\n" + source + "\n" + native)
print("Installed native iOS capability channel (fail-closed)")
