"""Install the fail-closed Windows VPN method channel in generated Flutter runner.

Native connectivity is NOT enabled by this bridge. The native layer reports
no supported protocols until independently verified tunnel engines are added.
This patch is idempotent and fails when the Flutter template has changed.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "windows" / "runner" / "flutter_window.h"
SOURCE = ROOT / "windows" / "runner" / "flutter_window.cpp"

HEADER_MARKER = "  std::unique_ptr<flutter::MethodChannel<flutter::EncodableValue>> vpn_channel_;"
CPP_MARKER = "  // TwinConnect: fail-closed Windows native capability handshake."


def insert_once(text: str, anchor: str, replacement: str) -> str:
    if text.count(anchor) != 1:
        raise RuntimeError(f"Unexpected Windows runner template: {anchor!r}")
    return text.replace(anchor, replacement, 1)


def install() -> None:
    if not HEADER.is_file() or not SOURCE.is_file():
        raise RuntimeError("Generate the Windows Flutter runner before installing native bridge.")

    header = HEADER.read_text(encoding="utf-8-sig")
    cpp = SOURCE.read_text(encoding="utf-8-sig")

    if HEADER_MARKER not in header:
        header = insert_once(
            header, '#include "win32_window.h"',
            '#include <flutter/method_channel.h>\n'
            '#include <flutter/encodable_value.h>\n'
            '#include "win32_window.h"',
        )
        header = insert_once(
            header,
            "  std::unique_ptr<flutter::FlutterViewController> flutter_controller_;",
            "  std::unique_ptr<flutter::FlutterViewController> flutter_controller_;\n"
            + HEADER_MARKER,
        )

    if CPP_MARKER not in cpp:
        cpp = insert_once(
            cpp, '#include "flutter_window.h"',
            '#include "flutter_window.h"\n'
            '#include <flutter/standard_method_codec.h>',
        )
        injection = """  // TwinConnect: fail-closed Windows native capability handshake.
  vpn_channel_ = std::make_unique<
      flutter::MethodChannel<flutter::EncodableValue>>(
      flutter_controller_->engine()->messenger(),
      "com.twinpanel.twinconnect/vpn",
      &flutter::StandardMethodCodec::GetInstance());

  vpn_channel_->SetMethodCallHandler(
      [](const flutter::MethodCall<flutter::EncodableValue>& call,
         std::unique_ptr<flutter::MethodResult<flutter::EncodableValue>> result) {
        using flutter::EncodableValue;
        if (call.method_name() == "getCapabilities") {
          flutter::EncodableMap capabilities = {
              {EncodableValue("contractVersion"), EncodableValue(1)},
              {EncodableValue("engineReady"), EncodableValue(false)},
              {EncodableValue("fullTunnel"), EncodableValue(false)},
              {EncodableValue("killSwitchEnforced"), EncodableValue(false)},
              {EncodableValue("dnsGuard"), EncodableValue(false)},
              {EncodableValue("ipv6Guard"), EncodableValue(false)},
          };
          result->Success(EncodableValue(capabilities));
        } else if (call.method_name() == "getProtocolCapabilities") {
          flutter::EncodableMap response = {
              {EncodableValue("contractVersion"), EncodableValue(1)},
              {EncodableValue("supportedProtocols"),
               EncodableValue(flutter::EncodableList{})},
          };
          result->Success(EncodableValue(response));
        } else {
          result->NotImplemented();
        }
      });
"""
        cpp = insert_once(
            cpp, "  RegisterPlugins(flutter_controller_->engine());",
            "  RegisterPlugins(flutter_controller_->engine());\n\n" + injection,
        )

    HEADER.write_text(header, encoding="utf-8")
    SOURCE.write_text(cpp, encoding="utf-8")


if __name__ == "__main__":
    install()
    print("Installed fail-closed TwinConnect Windows native capability channel.")
