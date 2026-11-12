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
XRAY_GUARD = ROOT / "native" / "windows" / "twinconnect_xray_guard.h"
XRAY_INSTALLED = ROOT / "windows" / "runner" / "twinconnect_xray_guard.h"
SUDOKU_GUARD = ROOT / "native" / "windows" / "twinconnect_sudoku_guard.h"
SUDOKU_INSTALLED = ROOT / "windows" / "runner" / "twinconnect_sudoku_guard.h"
OPENCONNECT_NATIVE = ROOT / "native" / "windows" / "twinconnect_openconnect.h"
OPENCONNECT_INSTALLED = ROOT / "windows" / "runner" / "twinconnect_openconnect.h"
L2TP_NATIVE = ROOT / "native" / "windows" / "twinconnect_l2tp.h"
L2TP_INSTALLED = ROOT / "windows" / "runner" / "twinconnect_l2tp.h"

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
    if not XRAY_GUARD.is_file():
        raise RuntimeError("Missing Xray process guard header")
    shutil.copyfile(XRAY_GUARD, XRAY_INSTALLED)
    if not SUDOKU_GUARD.is_file():
        raise RuntimeError("Missing Sudoku process/config guard header")
    shutil.copyfile(SUDOKU_GUARD, SUDOKU_INSTALLED)
    if not OPENCONNECT_NATIVE.is_file():
        raise RuntimeError("Missing OpenConnect native runtime header")
    shutil.copyfile(OPENCONNECT_NATIVE, OPENCONNECT_INSTALLED)
    if not L2TP_NATIVE.is_file():
        raise RuntimeError("Missing Windows L2TP native RAS implementation")
    shutil.copyfile(L2TP_NATIVE, L2TP_INSTALLED)

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
            '#include "twinconnect_xray_guard.h"\n'
            '#include "twinconnect_sudoku_guard.h"\n'
            '#include "twinconnect_openconnect.h"\n'
            '#include "twinconnect_l2tp.h"',
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
        if (call.method_name() == "windowControl") {
          const auto* args = std::get_if<flutter::EncodableMap>(
              call.arguments());
          if (!args) { result->Error("WINDOW_CONTROL_INVALID"); return; }
          const auto it = args->find(flutter::EncodableValue("action"));
          if (it == args->end()) {
            result->Error("WINDOW_ACTION_REQUIRED"); return;
          }
          const auto* action = std::get_if<std::string>(&it->second);
          const HWND hwnd = ::GetActiveWindow();
          if (!action || !hwnd) {
            result->Error("WINDOW_NOT_AVAILABLE"); return;
          }
          if (*action == "minimize") {
            ::ShowWindow(hwnd, SW_MINIMIZE);
          } else if (*action == "maximize") {
            ::ShowWindow(hwnd, ::IsZoomed(hwnd) ? SW_RESTORE : SW_MAXIMIZE);
          } else if (*action == "close") {
            // This must run normal OnDestroy VPN cleanup, not ExitProcess().
            ::PostMessageW(hwnd, WM_CLOSE, 0, 0);
          } else if (*action == "drag") {
            ::ReleaseCapture();
            ::SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0);
          } else {
            result->Error("WINDOW_ACTION_INVALID"); return;
          }
          result->Success(flutter::EncodableValue(true));
        } else if (call.method_name() == "startL2tp") {
          const auto* args = std::get_if<flutter::EncodableMap>(
              call.arguments());
          if (!args) { result->Error("L2TP_INVALID_REQUEST"); return; }
          const auto field = [&](const char* key) -> std::string {
            const auto it = args->find(flutter::EncodableValue(key));
            if (it == args->end()) return "";
            const auto* value = std::get_if<std::string>(&it->second);
            return value ? *value : "";
          };
          if (!twinconnect_l2tp::Start(
                  field("server"), field("username"),
                  field("password"), field("psk"))) {
            result->Error("L2TP_NATIVE_START_FAILED");
            return;
          }
          result->Success(flutter::EncodableValue(true));
        } else if (call.method_name() == "l2tpStatus") {
          flutter::EncodableMap values;
          values[flutter::EncodableValue("state")] =
              flutter::EncodableValue(twinconnect_l2tp::Status());
          values[flutter::EncodableValue("code")] =
              flutter::EncodableValue(static_cast<int64_t>(
                  twinconnect_l2tp::Error()));
          result->Success(flutter::EncodableValue(values));
        } else if (call.method_name() == "l2tpTraffic") {
          uint64_t rx = 0, tx = 0;
          if (!twinconnect_l2tp::Bytes(&rx, &tx)) {
            result->Success(flutter::EncodableValue());
          } else {
            flutter::EncodableMap values;
            values[flutter::EncodableValue("rxBytes")] =
                flutter::EncodableValue(static_cast<int64_t>(rx));
            values[flutter::EncodableValue("txBytes")] =
                flutter::EncodableValue(static_cast<int64_t>(tx));
            result->Success(flutter::EncodableValue(values));
          }
        } else if (call.method_name() == "stopL2tp") {
          if (!twinconnect_l2tp::Stop()) {
            result->Error("L2TP_DISCONNECT_PENDING");
            return;
          }
          result->Success(flutter::EncodableValue(true));
        } else if (call.method_name() == "resetL2tpFailure") {
          twinconnect_l2tp::ResetError();
          result->Success(flutter::EncodableValue(true));
        } else if (call.method_name() == "startOpenConnect") {
          const auto* args = std::get_if<flutter::EncodableMap>(
              call.arguments());
          if (!args) { result->Error("CISCO_INVALID_REQUEST"); return; }
          const auto field = [&](const char* key) -> std::string {
            const auto it = args->find(flutter::EncodableValue(key));
            if (it == args->end()) return "";
            const auto* value = std::get_if<std::string>(&it->second);
            return value ? *value : "";
          };
          if (!twinconnect_openconnect::Start(
                  field("executable"), field("script"), field("gateway"),
                  field("username"), field("password"), field("servercert"))) {
            result->Error("CISCO_NATIVE_START_FAILED");
            return;
          }
          result->Success(flutter::EncodableValue(true));
        } else if (call.method_name() == "openConnectTraffic") {
          twinconnect_openconnect::TrafficTotals totals = {};
          if (!twinconnect_openconnect::ReadTraffic(&totals)) {
            result->Success(flutter::EncodableValue());
          } else {
            flutter::EncodableMap values;
            values[flutter::EncodableValue("rxBytes")] =
                flutter::EncodableValue(static_cast<int64_t>(totals.received));
            values[flutter::EncodableValue("txBytes")] =
                flutter::EncodableValue(static_cast<int64_t>(totals.sent));
            result->Success(flutter::EncodableValue(values));
          }
        } else if (call.method_name() == "openVpnTraffic") {
          twinconnect_openconnect::TrafficTotals totals = {};
          if (!twinconnect_openconnect::ReadTunnelAdapterTraffic(&totals)) {
            result->Success(flutter::EncodableValue());
          } else {
            flutter::EncodableMap values;
            values[flutter::EncodableValue("rxBytes")] =
                flutter::EncodableValue(static_cast<int64_t>(totals.received));
            values[flutter::EncodableValue("txBytes")] =
                flutter::EncodableValue(static_cast<int64_t>(totals.sent));
            result->Success(flutter::EncodableValue(values));
          }
        } else if (call.method_name() == "openConnectStatus") {
          result->Success(flutter::EncodableValue(
              twinconnect_openconnect::Running()));
        } else if (call.method_name() == "openConnectExitReason") {
          // Reap the child so stderr is fully classified before responding.
          const bool active = twinconnect_openconnect::Running();
          result->Success(flutter::EncodableValue(active
              ? std::string("CISCO_STILL_RUNNING")
              : std::string(twinconnect_openconnect::FailureName())));
        } else if (call.method_name() == "stopOpenConnect") {
          if (!twinconnect_openconnect::Stop()) {
            result->Error("CISCO_GRACEFUL_DISCONNECT_FAILED");
            return;
          }
          result->Success(flutter::EncodableValue(true));
        } else if (call.method_name() == "guardSingBoxProcess") {
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
        } else if (call.method_name() == "guardXrayProcess") {
          const auto* args = std::get_if<flutter::EncodableMap>(
              call.arguments());
          if (!args) { result->Error("INVALID_XRAY_PROCESS_REQUEST"); return; }
          const auto it = args->find(flutter::EncodableValue("pid"));
          if (it == args->end()) {
            result->Error("INVALID_XRAY_PROCESS_ID"); return;
          }
          int64_t pid = 0;
          if (const auto* xray_pid32 = std::get_if<int32_t>(&it->second)) {
            pid = *xray_pid32;
          } else if (const auto* xray_pid64 = std::get_if<int64_t>(&it->second)) {
            pid = *xray_pid64;
          } else {
            result->Error("INVALID_XRAY_PROCESS_ID"); return;
          }
          if (!twinconnect_xray_guard::Guard(pid)) {
            result->Error("XRAY_PROCESS_GUARD_FAILED"); return;
          }
          result->Success(flutter::EncodableValue(true));
        } else if (call.method_name() == "stageSudokuConfig") {
          const auto* args = std::get_if<flutter::EncodableMap>(
              call.arguments());
          if (!args) { result->Error("SUDOKU_CONFIG_REQUEST_INVALID"); return; }
          const auto it = args->find(flutter::EncodableValue("config"));
          const auto* config = it == args->end() ? nullptr :
              std::get_if<std::string>(&it->second);
          if (!config) {
            result->Error("SUDOKU_CONFIG_REQUEST_INVALID"); return;
          }
          std::string path;
          if (!twinconnect_sudoku_guard::StageConfig(*config, &path)) {
            result->Error("SUDOKU_PRIVATE_CONFIG_STAGE_FAILED"); return;
          }
          result->Success(flutter::EncodableValue(path));
        } else if (call.method_name() == "finishSudokuConfig") {
          twinconnect_sudoku_guard::ReleaseConfig();
          result->Success(flutter::EncodableValue(true));
        } else if (call.method_name() == "guardSudokuProcess") {
          const auto* args = std::get_if<flutter::EncodableMap>(
              call.arguments());
          if (!args) { result->Error("SUDOKU_PROCESS_REQUEST_INVALID"); return; }
          const auto it = args->find(flutter::EncodableValue("pid"));
          if (it == args->end()) {
            result->Error("SUDOKU_PROCESS_REQUEST_INVALID"); return;
          }
          int64_t sudoku_pid = 0;
          if (const auto* sudoku_pid32 = std::get_if<int32_t>(&it->second)) {
            sudoku_pid = *sudoku_pid32;
          } else if (const auto* sudoku_pid64 = std::get_if<int64_t>(&it->second)) {
            sudoku_pid = *sudoku_pid64;
          } else {
            result->Error("SUDOKU_PROCESS_REQUEST_INVALID"); return;
          }
          if (!twinconnect_sudoku_guard::Guard(sudoku_pid)) {
            result->Error("SUDOKU_PROCESS_GUARD_FAILED"); return;
          }
          result->Success(flutter::EncodableValue(true));
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

    # Do not leave a Cisco child/process-owned VPN route behind when the user
    # closes the main desktop window while OpenConnect is connected.
    # The native Stop() sends CTRL_BREAK and awaits upstream disconnect script.
    cleanup_anchor = "void FlutterWindow::OnDestroy() {"
    if cleanup_anchor not in cpp:
        raise RuntimeError("Flutter OnDestroy hook changed; Cisco cleanup unsafe")
    cpp = cpp.replace(
        cleanup_anchor,
        cleanup_anchor + "\n  if (twinconnect_openconnect::Running()) {\n"
        "    twinconnect_openconnect::Stop();\n  }",
        1,
    )

    # Hide the native OS caption on every screen, including login. Retain
    # WS_THICKFRAME for resize and standard WM_CLOSE destruction semantics.
    frameless_marker = "  // TwinConnect: frameless Windows shell."
    if frameless_marker not in cpp:
        on_create_marker = "  RegisterPlugins(flutter_controller_->engine());"
        if cpp.count(on_create_marker) != 1:
            raise RuntimeError("Cannot safely locate Flutter window initialization")
        native_shell = """  // TwinConnect: frameless Windows shell.
  // The app renders compact window actions in its existing layout.
  HWND shell = GetHandle();
  if (shell) {
    const LONG_PTR style = ::GetWindowLongPtrW(shell, GWL_STYLE);
    ::SetWindowLongPtrW(shell, GWL_STYLE,
        style & ~(static_cast<LONG_PTR>(WS_CAPTION) |
                  static_cast<LONG_PTR>(WS_SYSMENU)));
    ::SetWindowPos(shell, nullptr, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER |
        SWP_NOACTIVATE | SWP_FRAMECHANGED);
  }
"""
        cpp = cpp.replace(on_create_marker,
            on_create_marker + "\n" + native_shell, 1)

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
    runner_cmake.write_text(cmake, encoding="utf-8")

    HEADER.write_text(header, encoding="utf-8")
    # On normal app exit, disconnect only this process's temporary L2TP RAS
    # connection so its Windows phone-book PSK is not left behind.
    if "twinconnect_l2tp::Stop();" not in cpp:
        import re
        cpp, patched = re.subn(
            r"FlutterWindow::~FlutterWindow\(\)\s*\{\s*\}",
            "FlutterWindow::~FlutterWindow() {\n  twinconnect_l2tp::Stop();\n}",
            cpp, count=1,
        )
        if patched != 1:
            raise RuntimeError("Unexpected Flutter Windows runner destructor; cannot guarantee L2TP cleanup")
    SOURCE.write_text(cpp, encoding="utf-8")


if __name__ == "__main__":
    install()
    print("Installed fail-closed TwinConnect Windows native capability channel.")
