// TwinConnect experimental Windows WFP guard service.
// Built only in isolated CI. NOT packaged or enabled for production.
// Privileged pipe access restricted to LocalSystem + Administrators.
// The separately available "recover" command removes only owned WFP filters.
// All arm paths require explicit VM-only confirmation, never automatic startup.
#define TWINCONNECT_GUARD_NO_MAIN
#include "twinconnect_global_guard_experimental.cpp"
#include <sddl.h>
#include <vector>
#pragma comment(lib, "Advapi32.lib")

namespace {
const wchar_t* kName = L"TwinConnectGlobalGuard";
const wchar_t* kPipe = L"\\\\.\\pipe\\TwinConnectGlobalGuardV1";
const wchar_t* kAccept = L"I_ACCEPT_OFFLINE_RECOVERY";
SERVICE_STATUS_HANDLE gHandle = nullptr;
SERVICE_STATUS gStatus = {};
HANDLE gStop = nullptr;

void Update(DWORD status, DWORD exitCode = NO_ERROR) {
  if (!gHandle) return;
  gStatus.dwServiceType = SERVICE_WIN32_OWN_PROCESS;
  gStatus.dwCurrentState = status;
  gStatus.dwControlsAccepted =
      status == SERVICE_RUNNING ? SERVICE_ACCEPT_STOP : 0;
  gStatus.dwWin32ExitCode = exitCode;
  SetServiceStatus(gHandle, &gStatus);
}

void WINAPI Control(DWORD code) {
  if (code != SERVICE_CONTROL_STOP || !gStop) return;
  Update(SERVICE_STOP_PENDING);
  SetEvent(gStop);
  // Break ConnectNamedPipe without waiting for client input.
  HANDLE wake = CreateFileW(kPipe, GENERIC_READ | GENERIC_WRITE,
                            0, nullptr, OPEN_EXISTING, 0, nullptr);
  if (wake != INVALID_HANDLE_VALUE) CloseHandle(wake);
}

bool ValidateRequest(const std::wstring& alias, const std::wstring& host,
                     const std::wstring& path, UINT64* luid, UINT32* endpoint) {
  if (alias != L"TwinConnectSB" && alias != L"TwinConnect") return false;
  NET_LUID tunnel = {};
  if (ConvertInterfaceAliasToLuid(alias.c_str(), &tunnel) != NO_ERROR ||
      tunnel.Value == 0) return false;
  IN_ADDR ip = {};
  if (InetPtonW(AF_INET, host.c_str(), &ip) != 1) return false;
  UINT32 addr = ntohl(ip.S_un.S_addr);
  if (!addr || addr == 0xFFFFFFFF || (addr >> 24) == 127 ||
      (addr >> 24) >= 224) return false;
  // A preliminary path check is NOT executable signature validation.
  const std::wstring dir = L"C:\\Program Files\\";
  const std::wstring dir86 = L"C:\\Program Files (x86)\\";
  bool inside = (path.size() > dir.size() &&
      _wcsnicmp(path.c_str(), dir.c_str(), dir.size()) == 0) ||
      (path.size() > dir86.size() &&
      _wcsnicmp(path.c_str(), dir86.c_str(), dir86.size()) == 0);
  DWORD attributes = GetFileAttributesW(path.c_str());
  if (!inside || attributes == INVALID_FILE_ATTRIBUTES ||
      (attributes & FILE_ATTRIBUTE_DIRECTORY)) return false;
  *luid = tunnel.Value;
  *endpoint = addr;
  return true;
}

std::wstring HandleRequest(const std::wstring& request) {
  Engine engine;
  if (Open(engine) != ERROR_SUCCESS) return L"ERR WFP_ENGINE_UNAVAILABLE";
  if (request == L"status") {
    bool v4 = Exists(engine.handle, kBlockV4);
    bool v6 = Exists(engine.handle, kBlockV6);
    bool app = Exists(engine.handle, kPermitV4);
    return std::wstring(L"OK ") + (v4 ? L"1" : L"0") + L" " +
           (v6 ? L"1" : L"0") + L" " + (app ? L"1" : L"0");
  }
  if (request == std::wstring(L"disarm ") + kAccept) {
    DWORD code = TransactionalDisarm(engine.handle);
    return code == ERROR_SUCCESS ? L"OK DISARMED" : L"ERR WFP_DISARM_FAILED";
  }
  const std::wstring prefix = L"arm ";
  if (request.rfind(prefix, 0) != 0) return L"ERR UNKNOWN_COMMAND";
  // Strict token count; paths may include spaces, so use tab as separator.
  // "arm <alias>\t<ip>\t<path>\tI_ACCEPT_OFFLINE_RECOVERY"
  const auto tab1 = request.find(L'\t', prefix.size());
  const auto tab2 = request.find(L'\t', tab1 == std::wstring::npos ? 0 : tab1 + 1);
  const auto tab3 = request.find(L'\t', tab2 == std::wstring::npos ? 0 : tab2 + 1);
  if (tab1 == std::wstring::npos || tab2 == std::wstring::npos ||
      tab3 == std::wstring::npos ||
      request.substr(tab3 + 1) != kAccept) return L"ERR BAD_REQUEST";
  std::wstring alias = request.substr(prefix.size(), tab1 - prefix.size());
  std::wstring host = request.substr(tab1 + 1, tab2 - tab1 - 1);
  std::wstring path = request.substr(tab2 + 1, tab3 - tab2 - 1);
  UINT64 luid = 0;
  UINT32 endpoint = 0;
  if (!ValidateRequest(alias, host, path, &luid, &endpoint))
    return L"ERR UNVERIFIED_TUNNEL_OR_TRANSPORT";
  DWORD code = TransactionalArm(engine.handle, luid, endpoint, path);
  return code == ERROR_SUCCESS ? L"OK ARMED_EXPERIMENTAL" :
                                 L"ERR WFP_ARM_FAILED";
}

void WINAPI ServiceMain(DWORD, LPWSTR*) {
  gHandle = RegisterServiceCtrlHandlerW(kName, Control);
  if (!gHandle) return;
  Update(SERVICE_START_PENDING);
  gStop = CreateEventW(nullptr, TRUE, FALSE, nullptr);
  if (!gStop) { Update(SERVICE_STOPPED, ERROR_NOT_ENOUGH_MEMORY); return; }

  PSECURITY_DESCRIPTOR descriptor = nullptr;
  // Strict DACL: only LocalSystem and local Administrators can call pipe.
  if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(
          L"D:P(A;;GA;;;SY)(A;;GA;;;BA)", SDDL_REVISION_1,
          &descriptor, nullptr)) {
    CloseHandle(gStop);
    Update(SERVICE_STOPPED, ERROR_ACCESS_DENIED);
    return;
  }
  SECURITY_ATTRIBUTES security = {sizeof(SECURITY_ATTRIBUTES), descriptor, FALSE};
  Update(SERVICE_RUNNING);
  while (WaitForSingleObject(gStop, 0) != WAIT_OBJECT_0) {
    HANDLE pipe = CreateNamedPipeW(
        kPipe, PIPE_ACCESS_DUPLEX, PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE |
        PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS, 1, 4096, 4096, 1000, &security);
    if (pipe == INVALID_HANDLE_VALUE) break;
    bool connected = ConnectNamedPipe(pipe, nullptr) != 0 ||
                     GetLastError() == ERROR_PIPE_CONNECTED;
    if (connected && WaitForSingleObject(gStop, 0) != WAIT_OBJECT_0) {
      wchar_t data[2048] = {};
      DWORD bytes = 0;
      if (ReadFile(pipe, data, sizeof(data) - sizeof(wchar_t), &bytes, nullptr) &&
          bytes > 0 && (bytes % sizeof(wchar_t) == 0)) {
        std::wstring request(data, bytes / sizeof(wchar_t));
        std::wstring response = HandleRequest(request);
        DWORD out = 0;
        WriteFile(pipe, response.c_str(),
                  static_cast<DWORD>((response.size() + 1) * sizeof(wchar_t)),
                  &out, nullptr);
        FlushFileBuffers(pipe);
      }
    }
    DisconnectNamedPipe(pipe);
    CloseHandle(pipe);
  }
  LocalFree(descriptor);
  CloseHandle(gStop);
  Update(SERVICE_STOPPED);
}

int Client(const std::wstring& text) {
  HANDLE pipe = CreateFileW(kPipe, GENERIC_READ | GENERIC_WRITE, 0,
                            nullptr, OPEN_EXISTING, 0, nullptr);
  if (pipe == INVALID_HANDLE_VALUE) {
    fwprintf(stderr, L"Guard service unavailable (Win32 %lu)\n", GetLastError());
    return 1;
  }
  DWORD written = 0;
  BOOL ok = WriteFile(pipe, text.c_str(),
                      static_cast<DWORD>(text.size() * sizeof(wchar_t)),
                      &written, nullptr);
  wchar_t reply[256] = {};
  DWORD received = 0;
  ok = ok && ReadFile(pipe, reply, sizeof(reply) - sizeof(wchar_t),
                      &received, nullptr);
  CloseHandle(pipe);
  if (!ok || received == 0 || (received % sizeof(wchar_t))) return 1;
  const std::wstring result(reply, received / sizeof(wchar_t));
  wprintf(L"%ls\n", result.c_str());
  return result.rfind(L"OK", 0) == 0 ? 0 : 1;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
  if (argc == 2 && _wcsicmp(argv[1], L"service") == 0) {
    SERVICE_TABLE_ENTRYW entries[] = {
      {const_cast<LPWSTR>(kName), ServiceMain},
      {nullptr, nullptr}
    };
    return StartServiceCtrlDispatcherW(entries) ? 0 : 1;
  }
  if (argc == 2 && _wcsicmp(argv[1], L"status") == 0)
    return Client(L"status");
  if (argc == 3 && _wcsicmp(argv[1], L"disarm") == 0 &&
      wcscmp(argv[2], kAccept) == 0)
    return Client(std::wstring(L"disarm ") + kAccept);
  if (argc == 6 && _wcsicmp(argv[1], L"arm") == 0 &&
      wcscmp(argv[5], kAccept) == 0)
    return Client(std::wstring(L"arm ") + argv[2] + L"\t" + argv[3] +
                  L"\t" + argv[4] + L"\t" + argv[5]);

  // Recovery even if the service is stopped or its pipe no longer works.
  if (argc == 3 && _wcsicmp(argv[1], L"recover") == 0 &&
      wcscmp(argv[2], kAccept) == 0) {
    Engine engine;
    if (Open(engine) != ERROR_SUCCESS) return 1;
    DWORD status = TransactionalDisarm(engine.handle);
    wprintf(status == ERROR_SUCCESS ? L"OWNED_RULES_REMOVED\n" :
            L"RECOVERY_FAILED\n");
    return status == ERROR_SUCCESS ? 0 : 1;
  }
  wprintf(L"VM-only Windows service prototype: service | status | "
          L"arm | disarm | recover.\n"
          L"Not a production release. Requires an independent recovery test.\n");
  return 2;
}
