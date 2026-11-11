"""Install the fail-closed Windows VPN method channel in generated Flutter runner.

Native connectivity is NOT enabled by this bridge. The native layer reports
no supported protocols until independently verified tunnel engines are added.
This patch is idempotent and fails when the Flutter template has changed.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "windows" / "runner" / "flutter_window.h"
SOURCE = ROOT / "windows" / "runner" / "flutter_window.cpp"
NATIVE = ROOT / "native" / "windows" / "twinconnect_wireguard.h"
INSTALLED = ROOT / "windows" / "runner" / "twinconnect_wireguard.h"
SINGBOX_GUARD = ROOT / "native" / "windows" / "twinconnect_singbox_guard.h"
SINGBOX_INSTALLED = ROOT / "windows" / "runner" / "twinconnect_singbox_guard.h"
TUN_INSPECT = ROOT / "native" / "windows" / "twinconnect_tun_inspect.h"
TUN_INSTALLED = ROOT / "windows" / "runner" / "twinconnect_tun_inspect.h"

HEADER_MARKER = "  std::unique_ptr<flutter::MethodChannel<flutter::EncodableValue>> vpn_channel_;"
CPP_MARKER = "  // TwinConnect: fail-closed Windows native capability handshake."


def insert_once(text: str, anchor: str, replacement: str) -> str:
    if text.count(anchor) != 1:
        raise RuntimeError(f"Unexpected Windows runner template: {anchor!r}")
    return text.replace(anchor, replacement, 1)


def install() -> None:
    if not HEADER.is_file() or not SOURCE.is_file() or not NATIVE.is_file():
        raise RuntimeError("Generate the Windows Flutter runner before installing native bridge.")

    shutil.copyfile(NATIVE, INSTALLED)
    if not SINGBOX_GUARD.is_file():
        raise RuntimeError("Missing sing-box process guard header")
    shutil.copyfile(SINGBOX_GUARD, SINGBOX_INSTALLED)
    if not TUN_INSPECT.is_file():
        raise RuntimeError('Missing Windows TUN inspection header')
    shutil.copyfile(TUN_INSPECT, TUN_INSTALLED)

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
            '#include <flutter/standard_method_codec.h>\n'
            '#include "twinconnect_wireguard.h"\n'
            '#include "twinconnect_singbox_guard.h"\n'
            '#include "twinconnect_tun_inspect.h"',
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
        if (call.method_name() == "guardSingBoxProcess") {
          const auto* args = std::get_if<flutter::EncodableMap>(
              call.arguments());
          if (!args) {
            result->Error("INVALID_PROCESS_REQUEST");
            return;
          }
          const auto it = args->find(flutter::EncodableValue("pid"));
          if (it == args->end()) {
            result->Error("INVALID_PROCESS_ID");
            return;
          }
          int64_t pid = 0;
          if (const auto* v = std::get_if<int32_t>(&it->second)) {
            pid = *v;
          } else if (const auto* v64 = std::get_if<int64_t>(&it->second)) {
            pid = *v64;
          } else {
            result->Error("INVALID_PROCESS_ID");
            return;
          }
          if (!twinconnect_singbox_guard::Guard(pid)) {
            result->Error("SINGBOX_PROCESS_GUARD_FAILED");
            return;
          }
          result->Success(flutter::EncodableValue(true));
        } else if (call.method_name() == "inspectSingBoxTun") {
          result->Success(twinconnect_tun_inspect::Inspect());
        } else if (call.method_name() == "getCapabilities") {
          result->Success(twinconnect_wireguard::Capabilities());
        } else if (call.method_name() == "getProtocolCapabilities") {
          result->Success(twinconnect_wireguard::ProtocolCapabilities());
        } else if (call.method_name() == "getTunnelStatus") {
          result->Success(twinconnect_wireguard::Status());
        } else if (call.method_name() == "startTunnel") {
          const auto* args = std::get_if<flutter::EncodableMap>(
              call.arguments());
          if (!args) {
            result->Error("INVALID_REQUEST");
            return;
          }
          const auto findString = [&](const char* key) -> const std::string* {
            const auto it = args->find(flutter::EncodableValue(key));
            if (it == args->end()) return nullptr;
            return std::get_if<std::string>(&it->second);
          };
          const auto* protocol = findString("protocol");
          const auto* raw = findString("config");
          if (!protocol || *protocol != "wireguard" || !raw) {
            result->Error("INVALID_PROTOCOL");
            return;
          }
          const auto policyIt =
              args->find(flutter::EncodableValue("policy"));
          const auto* policy = policyIt == args->end()
              ? nullptr
              : std::get_if<flutter::EncodableMap>(&policyIt->second);
          if (!policy) {
            result->Error("INVALID_POLICY");
            return;
          }
          const auto policyString = [&](const char* key) -> std::string {
            const auto it = policy->find(flutter::EncodableValue(key));
            if (it == policy->end()) return "";
            const auto* value = std::get_if<std::string>(&it->second);
            return value ? *value : "";
          };
          const auto policyFalse = [&](const char* key) -> bool {
            const auto it = policy->find(flutter::EncodableValue(key));
            if (it == policy->end()) return false;
            const auto* value = std::get_if<bool>(&it->second);
            return value != nullptr && !*value;
          };
          if (policyString("routingMode") != "fullTunnel" ||
              policyString("dnsMode") != "protected" ||
              policyString("ipv6Mode") != "tunnelOrBlock" ||
              !policyFalse("killSwitchRequested") ||
              !policyFalse("allowLan") ||
              !policyFalse("autoReconnect") ||
              !policyFalse("autoConnect")) {
            result->Error("UNSUPPORTED_VPN_POLICY");
            return;
          }
          if (!twinconnect_wireguard::IsAdmin()) {
            result->Error("WINDOWS_ADMIN_REQUIRED");
            return;
          }
          if (!twinconnect_wireguard::ValidConfig(
                  twinconnect_wireguard::ProtectedFullTunnelConfig(*raw))) {
            result->Error("WIREGUARD_CONFIG_UNSAFE");
            return;
          }
          if (twinconnect_wireguard::ServiceExists()) {
            result->Error("TUNNEL_ALREADY_RUNNING");
            return;
          }
          if (!twinconnect_wireguard::Start(*raw)) {
            result->Error("WIREGUARD_START_FAILED");
            return;
          }
          result->Success(twinconnect_wireguard::Status());
        } else if (call.method_name() == "stopTunnel") {
          if (!twinconnect_wireguard::Stop()) {
            result->Error("WIREGUARD_STOP_FAILED");
            return;
          }
          result->Success(twinconnect_wireguard::Status());
        } else {
          result->NotImplemented();
        }
      });
"""
        cpp = insert_once(
            cpp, "  RegisterPlugins(flutter_controller_->engine());",
            "  RegisterPlugins(flutter_controller_->engine());\n\n" + injection,
        )

    # Request elevation through the MSVC linker-generated manifest. Do not
    # insert trustInfo directly into runner.exe.manifest: the linker also
    # generates a UAC manifest, and mt.exe can fail merging both.
    runner_cmake = ROOT / "windows" / "runner" / "CMakeLists.txt"
    if not runner_cmake.is_file():
        raise RuntimeError("Missing generated Windows runner CMakeLists.txt")
    cmake = runner_cmake.read_text(encoding="utf-8-sig")
    uac_line = "target_link_options(${BINARY_NAME} PRIVATE \"/MANIFESTUAC:level='requireAdministrator' uiAccess='false'\")"
    if uac_line not in cmake:
        cmake += "\n# TwinConnect native VPN needs elevation for service management.\n" + uac_line + "\n"
    # MIB_IF_TABLE2/GetIfTable2/IP Helper v2 are available since Vista.
    # The Flutter runner may inherit an older SDK target from templates.
    windows_target = 'target_compile_definitions(${BINARY_NAME} PRIVATE WINVER=0x0A00 _WIN32_WINNT=0x0A00 NTDDI_VERSION=0x0A000000)'
    if windows_target not in cmake:
        cmake += "\n# Enable Win10 IP Helper v2 routing inspection.\n" + windows_target + "\n"
    runner_cmake.write_text(cmake, encoding="utf-8")

    HEADER.write_text(header, encoding="utf-8")
    SOURCE.write_text(cpp, encoding="utf-8")


if __name__ == "__main__":
    install()
    print("Installed fail-closed TwinConnect Windows native capability channel.")
