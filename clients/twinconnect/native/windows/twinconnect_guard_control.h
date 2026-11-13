// Experimental admin-only control path for disposable Windows VMs.
// Not a production Kill Switch. The regular app never arms filters.
#pragma once
#include <windows.h>
#include <string>
#include <flutter/encodable_value.h>

namespace twinconnect_guard_control {
inline std::wstring ToWide(const std::string& text) {
  if (text.empty() || text.size() > 1024) return {};
  const int length = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS,
      text.data(), static_cast<int>(text.size()), nullptr, 0);
  if (length <= 0) return {};
  std::wstring value(length, L'\0');
  if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS,
      text.data(), static_cast<int>(text.size()), value.data(), length) != length)
    return {};
  if (value.find(L'\0') != std::wstring::npos ||
      value.find(L'\n') != std::wstring::npos ||
      value.find(L'\r') != std::wstring::npos ||
      value.find(L'\t') != std::wstring::npos) return {};
  return value;
}

inline flutter::EncodableValue Result(bool success, const std::string& reason) {
  return flutter::EncodableValue(flutter::EncodableMap{
    {flutter::EncodableValue("contractVersion"), flutter::EncodableValue(1)},
    {flutter::EncodableValue("success"), flutter::EncodableValue(success)},
    {flutter::EncodableValue("reason"), flutter::EncodableValue(reason)}
  });
}

inline flutter::EncodableValue SendVmOnly(
    const std::string& action, const std::string& alias,
    const std::string& endpoint, const std::string& executable) {
  // Explicit per-process opt-in AND a system policy gate.
  // Failure always keeps the app's Kill Switch toggle disabled.
  wchar_t enabled[8] = {};
  const DWORD n = GetEnvironmentVariableW(
      L"TWINCONNECT_DISPOSABLE_VM", enabled, 8);
  if (n != 1 || enabled[0] != L'1') return Result(false, "VM_ONLY");
  std::wstring request;
  if (action == "status") {
    request = L"status";
  } else if (action == "disarm") {
    request = L"disarm I_ACCEPT_OFFLINE_RECOVERY";
  } else if (action == "arm") {
    const auto wAlias = ToWide(alias);
    const auto wIp = ToWide(endpoint);
    const auto wExe = ToWide(executable);
    if ((wAlias != L"TwinConnectSB" && wAlias != L"TwinConnect") ||
        wIp.empty() || wExe.empty()) return Result(false, "INVALID_PROFILE");
    request = L"arm " + wAlias + L"\t" + wIp + L"\t" + wExe +
              L"\tI_ACCEPT_OFFLINE_RECOVERY";
  } else {
    return Result(false, "INVALID_ACTION");
  }

  HANDLE pipe = CreateFileW(L"\\\\.\\pipe\\TwinConnectGlobalGuardV1",
      GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_EXISTING, 0, nullptr);
  if (pipe == INVALID_HANDLE_VALUE) return Result(false, "SERVICE_UNAVAILABLE");
  DWORD mode = PIPE_READMODE_MESSAGE;
  if (!SetNamedPipeHandleState(pipe, &mode, nullptr, nullptr)) {
    CloseHandle(pipe);
    return Result(false, "IPC_PROTOCOL_ERROR");
  }
  DWORD sent = 0;
  const DWORD size = static_cast<DWORD>(request.size() * sizeof(wchar_t));
  bool ok = WriteFile(pipe, request.data(), size, &sent, nullptr) &&
            sent == size;
  wchar_t reply[160] = {};
  DWORD received = 0;
  if (ok) ok = ReadFile(pipe, reply, sizeof(reply) - sizeof(wchar_t),
                         &received, nullptr);
  CloseHandle(pipe);
  if (!ok || received == 0 || received % sizeof(wchar_t)) {
    return Result(false, "IPC_FAILURE");
  }
  const std::wstring response(reply, received / sizeof(wchar_t));
  if (response.rfind(L"OK ", 0) != 0) return Result(false, "GUARD_REJECTED");
  // Success is an acknowledgement only, NOT proof that system traffic is
  // leak-free. Native status and packet tests remain mandatory.
  return Result(true, "VM_COMMAND_ACKNOWLEDGED");
}
}  // namespace twinconnect_guard_control
