// TwinConnect experimental Windows WFP guard service.
// Built only in isolated CI. NOT packaged or enabled for production.
// Privileged pipe access restricted to LocalSystem + Administrators.
// The separately available "recover" command removes only owned WFP filters.
// All arm paths require explicit VM-only confirmation, never automatic startup.
#define TWINCONNECT_GUARD_NO_MAIN
#include "twinconnect_global_guard_experimental.cpp"
#include <sddl.h>
#include <taskschd.h>
#include <oleauto.h>
#include <vector>
#pragma comment(lib, "Advapi32.lib")
#pragma comment(lib, "Ole32.lib")
#pragma comment(lib, "Oleaut32.lib")
#pragma comment(lib, "Taskschd.lib")

namespace {
#if defined(TWINCONNECT_GUARD_DIAGNOSTIC_ONLY)
const wchar_t* kName = L"TwinConnectGuardDiagnostic";
const wchar_t* kPipe = L"\\\\.\\pipe\\TwinConnectGuardDiagnosticV1";
#else
const wchar_t* kName = L"TwinConnectGlobalGuard";
const wchar_t* kPipe = L"\\\\.\\pipe\\TwinConnectGlobalGuardV1";
#endif
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
  // Never trust an alias alone. A local administrator or a network driver
  // might rename a physical Ethernet/Wi-Fi NIC to "TwinConnect". Binding
  // system-wide WFP blocks to such a NIC could bypass the intended protection.
  MIB_IF_ROW2 adapter = {};
  adapter.InterfaceLuid = tunnel;
  if (GetIfEntry2(&adapter) != NO_ERROR ||
      adapter.OperStatus != IfOperStatusUp ||
      adapter.InterfaceAndOperStatusFlags.HardwareInterface ||
      adapter.Type == IF_TYPE_SOFTWARE_LOOPBACK ||
      adapter.Type == IF_TYPE_PPP ||
      adapter.Type == IF_TYPE_IEEE80211) return false;
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

// VM-only safety gate: the privileged service must refuse persistent WFP
// rules until a real, independent SYSTEM recovery task is already scheduled.
// An app-level timer cannot recover when Flutter or the guard service crashes.
bool RecoveryTaskReady() {
  const HRESULT initialized = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
  if (FAILED(initialized)) return false;
  ITaskService* scheduler = nullptr;
  ITaskFolder* folder = nullptr;
  IRegisteredTask* task = nullptr;
  ITaskDefinition* definition = nullptr;
  ITaskSettings* settings = nullptr;
  IPrincipal* principal = nullptr;
  IActionCollection* actions = nullptr;
  IAction* action = nullptr;
  IExecAction* executable = nullptr;
  BSTR name = nullptr, user = nullptr, path = nullptr, arguments = nullptr;
  bool valid = false;
  do {
    HRESULT hr = CoCreateInstance(CLSID_TaskScheduler, nullptr,
        CLSCTX_INPROC_SERVER, IID_ITaskService,
        reinterpret_cast<void**>(&scheduler));
    if (FAILED(hr) || scheduler == nullptr) break;
    VARIANT empty = {};
    VariantInit(&empty);
    hr = scheduler->Connect(empty, empty, empty, empty);
    if (FAILED(hr)) break;
    name = SysAllocString(L"\\");
    if (!name) break;
    hr = scheduler->GetFolder(name, &folder);
    SysFreeString(name);
    name = nullptr;
    if (FAILED(hr) || !folder) break;
    name = SysAllocString(L"TwinConnectWfpEmergencyRestore");
    if (!name) break;
    hr = folder->GetTask(name, &task);
    SysFreeString(name);
    name = nullptr;
    if (FAILED(hr) || !task) break;
    VARIANT_BOOL enabled = VARIANT_FALSE;
    TASK_STATE state = TASK_STATE_UNKNOWN;
    DATE next = 0;
    if (FAILED(task->get_Enabled(&enabled)) || enabled != VARIANT_TRUE ||
        FAILED(task->get_State(&state)) ||
        (state != TASK_STATE_READY && state != TASK_STATE_RUNNING) ||
        FAILED(task->get_NextRunTime(&next)) || next <= 0) break;
    SYSTEMTIME due = {}, now = {};
    FILETIME dueFt = {}, nowFt = {};
    if (!VariantTimeToSystemTime(next, &due) ||
        !SystemTimeToFileTime(&due, &dueFt)) break;
    // Task Scheduler next-run DATE uses local wall-clock time. Compare it
    // against local time, not UTC; otherwise the safety gate fails in most
    // time zones or accepts a task at the wrong real-world deadline.
    GetLocalTime(&now);
    if (!SystemTimeToFileTime(&now, &nowFt)) break;
    ULARGE_INTEGER when = {}, current = {};
    when.LowPart = dueFt.dwLowDateTime;
    when.HighPart = dueFt.dwHighDateTime;
    current.LowPart = nowFt.dwLowDateTime;
    current.HighPart = nowFt.dwHighDateTime;
    // The recovery deadline must be imminent, not tomorrow or next month.
    if (when.QuadPart <= current.QuadPart ||
        when.QuadPart - current.QuadPart > 10ULL * 60ULL * 10000000ULL) break;
    // Task Scheduler's StartWhenAvailable means the offline restore will
    // still run after reboot if the machine missed its original deadline.
    VARIANT_BOOL startWhenAvailable = VARIANT_FALSE;
    if (FAILED(task->get_Definition(&definition)) || !definition ||
        FAILED(definition->get_Settings(&settings)) || !settings ||
        FAILED(settings->get_StartWhenAvailable(&startWhenAvailable)) ||
        startWhenAvailable != VARIANT_TRUE ||
        FAILED(definition->get_Principal(&principal)) || !principal ||
        FAILED(principal->get_UserId(&user)) || !user) break;
    if (_wcsicmp(user, L"SYSTEM") != 0 &&
        _wcsicmp(user, L"S-1-5-18") != 0 &&
        _wcsicmp(user, L"NT AUTHORITY\\SYSTEM") != 0) break;
    if (FAILED(definition->get_Actions(&actions)) || !actions) break;
    long count = 0;
    if (FAILED(actions->get_Count(&count)) || count != 1) break;
    if (FAILED(actions->get_Item(1, &action)) || !action ||
        FAILED(action->QueryInterface(IID_IExecAction,
            reinterpret_cast<void**>(&executable))) || !executable ||
        FAILED(executable->get_Path(&path)) || !path ||
        FAILED(executable->get_Arguments(&arguments)) || !arguments) break;
    wchar_t self[MAX_PATH] = {};
    DWORD length = GetModuleFileNameW(nullptr, self, MAX_PATH);
    valid = length > 0 && length < MAX_PATH &&
        _wcsicmp(path, self) == 0 &&
        wcscmp(arguments, L"recover I_ACCEPT_OFFLINE_RECOVERY") == 0;
  } while (false);
  if (arguments) SysFreeString(arguments);
  if (path) SysFreeString(path);
  if (user) SysFreeString(user);
  if (name) SysFreeString(name);
  if (executable) executable->Release();
  if (action) action->Release();
  if (actions) actions->Release();
  if (principal) principal->Release();
  if (settings) settings->Release();
  if (definition) definition->Release();
  if (task) task->Release();
  if (folder) folder->Release();
  if (scheduler) scheduler->Release();
  CoUninitialize();
  return valid;
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
#if defined(TWINCONNECT_GUARD_DIAGNOSTIC_ONLY)
  // Diagnostic build does not permit disarm or arm commands.
  return L"ERR DIAGNOSTIC_NO_FIREWALL_CHANGES";
#endif
  if (request == std::wstring(L"disarm ") + kAccept) {
    DWORD code = TransactionalDisarm(engine.handle);
    return code == ERROR_SUCCESS ? L"OK DISARMED" : L"ERR WFP_DISARM_FAILED";
  }
#if defined(TWINCONNECT_GUARD_DIAGNOSTIC_ONLY)
  // Internal installer test build: no request can add persistent WFP rules.
  // The installed service verifies SCM/UAC/IPC lifecycle only.
  return L"ERR DIAGNOSTIC_BUILD_BLOCKING_DISABLED";
#endif
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
  // No persistent WFP lock without an independent SYSTEM recovery task.
  if (!RecoveryTaskReady()) return L"ERR RECOVERY_TASK_NOT_VERIFIED";
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


bool RunningAsAdministrator() {
  BOOL admin = FALSE;
  PSID group = nullptr;
  SID_IDENTIFIER_AUTHORITY authority = SECURITY_NT_AUTHORITY;
  if (!AllocateAndInitializeSid(&authority, 2, SECURITY_BUILTIN_DOMAIN_RID,
          DOMAIN_ALIAS_RID_ADMINS, 0, 0, 0, 0, 0, 0, &group)) return false;
  BOOL valid = CheckTokenMembership(nullptr, group, &admin);
  FreeSid(group);
  return valid && admin;
}

bool ProtectedBinaryPath(std::wstring* executablePath) {
  wchar_t filename[32768] = {};
  DWORD len = GetModuleFileNameW(nullptr, filename, 32768);
  if (!len || len >= 32768) return false;
  *executablePath = filename;
  const std::wstring trusted = L"C:\\Program Files\\";
  const std::wstring trusted86 = L"C:\\Program Files (x86)\\";
  return (executablePath->size() > trusted.size() &&
          _wcsnicmp(executablePath->c_str(), trusted.c_str(),
                    trusted.size()) == 0) ||
         (executablePath->size() > trusted86.size() &&
          _wcsnicmp(executablePath->c_str(), trusted86.c_str(),
                    trusted86.size()) == 0);
}

int InstallVmOnlyService() {
  if (!RunningAsAdministrator()) return 1;
  std::wstring path;
  if (!ProtectedBinaryPath(&path)) {
    fwprintf(stderr, L"Install under protected Program Files first.\n");
    return 1;
  }
  // Service stays demand-start and never arms filters automatically.
  SC_HANDLE scm = OpenSCManagerW(nullptr, nullptr, SC_MANAGER_CREATE_SERVICE);
  if (!scm) return 1;
  std::wstring command = L"\"" + path + L"\" service";
  SC_HANDLE service = CreateServiceW(
      scm, kName, L"TwinConnect WFP Guard (EXPERIMENTAL VM ONLY)",
      SERVICE_CHANGE_CONFIG | SERVICE_START | SERVICE_QUERY_STATUS,
      SERVICE_WIN32_OWN_PROCESS, SERVICE_DEMAND_START,
      SERVICE_ERROR_NORMAL, command.c_str(), nullptr, nullptr, nullptr,
      L"LocalSystem", nullptr);
  DWORD error = service ? ERROR_SUCCESS : GetLastError();
  if (service) CloseServiceHandle(service);
  CloseServiceHandle(scm);
  if (error != ERROR_SUCCESS) {
    fwprintf(stderr, L"CreateService failed: %lu\n", error);
    return 1;
  }
  wprintf(L"Service registered but NOT started or armed.\n");
  return 0;
}

int UninstallVmOnlyService() {
  if (!RunningAsAdministrator()) return 1;
  Engine engine;
  if (Open(engine) != ERROR_SUCCESS) return 1;
  // Restore connectivity BEFORE stopping or deleting anything.
  if (TransactionalDisarm(engine.handle) != ERROR_SUCCESS) {
    fwprintf(stderr, L"Recovery failed; refusing to uninstall service.\n");
    return 1;
  }
  SC_HANDLE scm = OpenSCManagerW(nullptr, nullptr, SC_MANAGER_CONNECT);
  if (!scm) return 1;
  SC_HANDLE service = OpenServiceW(
      scm, kName, SERVICE_STOP | SERVICE_QUERY_STATUS | DELETE);
  if (!service) { CloseServiceHandle(scm); return 1; }
  SERVICE_STATUS status = {};
  ControlService(service, SERVICE_CONTROL_STOP, &status);
  BOOL deleted = DeleteService(service);
  CloseServiceHandle(service);
  CloseServiceHandle(scm);
  return deleted ? 0 : 1;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
  // Works even if the service is crashed or absent. Return 0 ONLY when
  // no TwinConnect-owned persistent WFP rules remain, including malformed
  // ones that fail structural verification.
  if (argc == 2 && _wcsicmp(argv[1], L"offline-status") == 0) {
    Engine engine;
    if (Open(engine) != ERROR_SUCCESS) return 2;
    const bool v4 = OwnedFilterPresent(engine.handle, kBlockV4);
    const bool v6 = OwnedFilterPresent(engine.handle, kBlockV6);
    const bool permit = OwnedFilterPresent(engine.handle, kPermitV4);
    wprintf(L"OWNED_RULES_PRESENT %d %d %d\n",
            v4 ? 1 : 0, v6 ? 1 : 0, permit ? 1 : 0);
    return v4 || v6 || permit ? 1 : 0;
  }
  // VM-only install/uninstall require admin and a protected executable path.
  if (argc == 3 && _wcsicmp(argv[1], L"install-vm") == 0 &&
      wcscmp(argv[2], kAccept) == 0)
    return InstallVmOnlyService();
  if (argc == 3 && _wcsicmp(argv[1], L"uninstall-vm") == 0 &&
      wcscmp(argv[2], kAccept) == 0)
    return UninstallVmOnlyService();
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
#if !defined(TWINCONNECT_GUARD_DIAGNOSTIC_ONLY)
  if (argc == 3 && _wcsicmp(argv[1], L"recover") == 0 &&
      wcscmp(argv[2], kAccept) == 0) {
    Engine engine;
    if (Open(engine) != ERROR_SUCCESS) return 1;
    DWORD status = TransactionalDisarm(engine.handle);
    wprintf(status == ERROR_SUCCESS ? L"OWNED_RULES_REMOVED\n" :
            L"RECOVERY_FAILED\n");
    return status == ERROR_SUCCESS ? 0 : 1;
  }
#endif
  wprintf(L"VM-only Windows service prototype: service | status | "
          L"arm | disarm | recover.\n"
          L"Not a production release. Requires an independent recovery test.\n");
  return 2;
}
