#pragma once
// TwinConnect-owned Cisco/OpenConnect runtime. Never controls arbitrary
// OpenConnect processes or accepts an external executable outside our bundle.
// A console process group lets CTRL_BREAK reach OpenConnect so vpnc-script
// can restore Windows routes and DNS on disconnect.
#include <windows.h>
#include <iphlpapi.h>
#include <netioapi.h>
#pragma comment(lib, "Iphlpapi.lib")
#include <string>
#include <cstdint>
#include <algorithm>
#include <cctype>
#include <cwctype>
#include <vector>

namespace twinconnect_openconnect {

// Only the route chosen for the VPN's own verified egress is measured.
// Capturing the pre-VPN route prevents presenting Wi-Fi/system traffic as VPN.
// Explicitly bind statistics to OpenConnect's tunnel adapter rather than
// a public-IP route; split routes and existing default routes may not change.
inline bool Running();
struct TrafficTotals { uint64_t received; uint64_t sent; };

inline bool CiscoAdapterDescription(const char* text) {
  if (!text || !*text) return false;
  std::string name(text);
  std::transform(name.begin(), name.end(), name.begin(),
      [](unsigned char ch) { return static_cast<char>(tolower(ch)); });
  return name.find("tap-windows") != std::string::npos ||
         name.find("openconnect") != std::string::npos ||
         name.find("vpn client adapter") != std::string::npos ||
         name.find("ovpn-dco") != std::string::npos ||
         name.find("openvpn") != std::string::npos;
}

inline bool ReadTunnelAdapterTraffic(TrafficTotals* totals) {
  if (!totals) return false;
  // The legacy IP Helper interface table works with Flutter's existing
  // Windows SDK target without forcing project-wide WINVER changes.
  ULONG bytesNeeded = 0;
  DWORD rc = GetIfTable(nullptr, &bytesNeeded, FALSE);
  if (rc != ERROR_INSUFFICIENT_BUFFER || bytesNeeded == 0 ||
      bytesNeeded > 1048576) return false;
  std::vector<BYTE> buffer(bytesNeeded);
  auto* table = reinterpret_cast<MIB_IFTABLE*>(buffer.data());
  rc = GetIfTable(table, &bytesNeeded, FALSE);
  if (rc != NO_ERROR) return false;
  DWORD bestIndex = 0;
  GetBestInterface(0x01010101u, &bestIndex);
  const MIB_IFROW* selected = nullptr;
  bool ambiguous = false;
  for (DWORD i = 0; i < table->dwNumEntries; ++i) {
    const auto& row = table->table[i];
    if (row.dwOperStatus != IF_OPER_STATUS_OPERATIONAL ||
        row.dwIndex == 0 || row.dwDescrLen == 0 ||
        row.dwDescrLen > MAXLEN_IFDESCR) continue;
    std::string description(reinterpret_cast<const char*>(row.bDescr),
                            row.dwDescrLen);
    if (!CiscoAdapterDescription(description.c_str())) continue;
    if (!selected || bestIndex == row.dwIndex) {
      ambiguous = selected && selected->dwIndex != row.dwIndex &&
                  bestIndex != row.dwIndex;
      selected = &row;
    } else if (bestIndex != selected->dwIndex) {
      ambiguous = true;
    }
  }
  if (!selected || ambiguous) return false;
  // IP Helper's legacy row uses 32-bit octets. Accumulate modulo deltas
  // into 64 bits; reset suspicious jumps instead of showing huge false use.
  static DWORD lastIndex = 0, lastRx = 0, lastTx = 0;
  static uint64_t totalRx = 0, totalTx = 0;
  const DWORD currentRx = selected->dwInOctets;
  const DWORD currentTx = selected->dwOutOctets;
  if (selected->dwIndex != lastIndex) {
    lastIndex = selected->dwIndex;
    lastRx = currentRx;
    lastTx = currentTx;
    totalRx = 0;
    totalTx = 0;
  } else {
    const DWORD deltaRx = currentRx - lastRx;
    const DWORD deltaTx = currentTx - lastTx;
    totalRx = deltaRx <= 0x7FFFFFFFu ? totalRx + deltaRx : 0;
    totalTx = deltaTx <= 0x7FFFFFFFu ? totalTx + deltaTx : 0;
    lastRx = currentRx;
    lastTx = currentTx;
  }
  totals->received = totalRx;
  totals->sent = totalTx;
  return true;
}
inline bool ReadTraffic(TrafficTotals* totals) {
  return Running() && ReadTunnelAdapterTraffic(totals);
}

inline HANDLE& Child() { static HANDLE process = nullptr; return process; }
inline DWORD& Pid() { static DWORD pid = 0; return pid; }
inline bool& ConsoleReady() { static bool ready = false; return ready; }
inline HANDLE& Reader() { static HANDLE reader = nullptr; return reader; }
// No raw OpenConnect output is ever persisted or returned to Dart.
// Only these coarse classifications can cross the native boundary.
inline volatile LONG& Failure() { static volatile LONG category = 0; return category; }
enum FailureCode : LONG {
  kUnknown = 0, kCertificate = 1, kAuthentication = 2,
  kRouteScript = 3, kAdapter = 4, kGateway = 5, kDependency = 6,
  kPostAuthExit = 7
};
inline volatile LONG& Authenticated() { static volatile LONG seen = 0; return seen; }
inline void Classify(const std::string& data) {
  std::string lower(data);
  std::transform(lower.begin(), lower.end(), lower.begin(),
      [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
  auto has = [&](const char* needle) {
    return lower.find(needle) != std::string::npos;
  };
  if (has("authentication completed") || has("authenticated successfully") ||
      has("got connect response") || has("cookie obtained")) {
    InterlockedExchange(&Authenticated(), 1);
  }
  LONG reason = kUnknown;
  if (has("certificate verify failed") || has("server certificate verify failed") ||
      has("untrusted certificate") || has("certificate validation failed") ||
      has("server certificate is invalid") || has("certificate has changed")) {
    reason = kCertificate;
  } else if (has("authentication failed") || has("login failed") ||
             has("invalid password") || has("password incorrect") ||
             has("failed to obtain cookie") || has("authentication error")) {
    reason = kAuthentication;
  } else if (has("failed to spawn script") || has("script returned error") ||
             has("script did not complete") || has("script failed") ||
             has("cscript") || has("vpnc-script") && has("error")) {
    reason = kRouteScript;
  } else if (has("failed to open tun") || has("tap-windows") ||
             has("tun device") && has("failed") ||
             has("could not open tun")) {
    reason = kAdapter;
  } else if (has("connection refused") || has("could not connect") ||
             has("failed to connect") || has("name resolution failed") ||
             has("network is unreachable")) {
    reason = kGateway;
  }
  if (reason != kUnknown) InterlockedExchange(&Failure(), reason);
}
inline DWORD WINAPI ConsumeErrors(LPVOID context) {
  HANDLE pipe = static_cast<HANDLE>(context);
  char buffer[2048];
  std::string trailing;
  DWORD read = 0;
  while (ReadFile(pipe, buffer, sizeof(buffer), &read, nullptr) && read) {
    // A short rolling window handles messages split across pipe reads.
    // It exists only inside this worker and is never logged or sent to Flutter.
    const std::string joined = trailing + std::string(buffer, read);
    Classify(joined);
    trailing = joined.substr(joined.size() > 160 ? joined.size() - 160 : 0);
  }
  CloseHandle(pipe);
  return 0;
}
inline const char* FailureName() {
  switch (InterlockedCompareExchange(&Failure(), 0, 0)) {
    case kCertificate: return "CISCO_CERTIFICATE_UNTRUSTED";
    case kAuthentication: return "CISCO_AUTHENTICATION_FAILED";
    case kRouteScript: return "CISCO_ROUTE_SCRIPT_FAILED";
    case kAdapter: return "CISCO_TAP_ADAPTER_FAILED";
    case kGateway: return "CISCO_GATEWAY_UNREACHABLE";
    case kDependency: return "CISCO_ENGINE_DEPENDENCY_FAILED";
    default: return InterlockedCompareExchange(&Authenticated(), 0, 0)
        ? "CISCO_POST_AUTH_TUNNEL_FAILED" : "CISCO_PROCESS_EXITED";
  }
}

inline std::wstring FromUtf8(const std::string& utf8) {
  if (utf8.empty()) return {};
  const int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS,
      utf8.data(), static_cast<int>(utf8.size()), nullptr, 0);
  if (count <= 0) return {};
  std::wstring value(count, L'\0');
  if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, utf8.data(),
      static_cast<int>(utf8.size()), value.data(), count) != count) return {};
  return value;
}

inline std::wstring Quote(const std::wstring& arg) {
  // Windows CreateProcess quoting; command is passed directly, no shell.
  std::wstring out = L"\"";
  unsigned backslashes = 0;
  for (const auto ch : arg) {
    if (ch == L'\\') { ++backslashes; continue; }
    if (ch == L'"') {
      out.append(backslashes * 2 + 1, L'\\');
      out += L'"';
    } else {
      out.append(backslashes, L'\\');
      out += ch;
    }
    backslashes = 0;
  }
  out.append(backslashes * 2, L'\\');
  out += L'"';
  return out;
}

inline std::wstring AppFolder() {
  wchar_t filename[32768] = {};
  const auto len = GetModuleFileNameW(nullptr, filename, 32768);
  if (!len || len >= 32768) return {};
  std::wstring path(filename, len);
  auto slash = path.find_last_of(L"\\/");
  if (slash == std::wstring::npos) return {};
  path.resize(slash + 1);
  return path;
}

inline bool TrustedFile(const std::wstring& path, const wchar_t* name) {
  const auto root = AppFolder();
  if (root.empty() || path.empty() || path.size() >= 32000) return false;
  wchar_t expanded[32768] = {};
  auto n = GetFullPathNameW(path.c_str(), 32768, expanded, nullptr);
  if (!n || n >= 32768) return false;
  std::wstring full(expanded, n);
  std::wstring prefix = root + L"engines\\openconnect\\";
  if (full.size() <= prefix.size() || _wcsnicmp(full.c_str(),
      prefix.c_str(), prefix.size()) != 0) return false;
  auto slash = full.find_last_of(L"\\/");
  if (slash == std::wstring::npos ||
      _wcsicmp(full.c_str() + slash + 1, name) != 0) return false;
  HANDLE file = CreateFileW(full.c_str(), FILE_READ_ATTRIBUTES,
      FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
      nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (file == INVALID_HANDLE_VALUE) return false;
  wchar_t resolved[32768] = {};
  const auto length = GetFinalPathNameByHandleW(file, resolved, 32768,
      FILE_NAME_NORMALIZED);
  CloseHandle(file);
  if (!length || length >= 32768) return false;
  std::wstring real(resolved, length);
  // The resolved file must still reside beneath the installed app tree.
  const std::wstring resolvedPrefix = L"\\\\?\\" + prefix;
  return real.size() > resolvedPrefix.size() &&
      _wcsnicmp(real.c_str(), resolvedPrefix.c_str(),
               resolvedPrefix.size()) == 0;
}

inline bool SafeField(const std::string& field, size_t maxLen) {
  if (field.empty() || field.size() > maxLen) return false;
  return std::none_of(field.begin(), field.end(), [](unsigned char c) {
    return c == 0 || c == '\n' || c == '\r' || c < 0x20 || c == 0x7f;
  });
}

inline bool Running() {
  auto& process = Child();
  if (!process) return false;
  if (WaitForSingleObject(process, 0) == WAIT_TIMEOUT) return true;
  DWORD exitCode = 0;
  if (GetExitCodeProcess(process, &exitCode) &&
      (exitCode == 0xC0000135u || // STATUS_DLL_NOT_FOUND
       exitCode == 0xC000007Bu || // STATUS_INVALID_IMAGE_FORMAT
       exitCode == 0xC0000142u)) { // STATUS_DLL_INIT_FAILED
    InterlockedExchange(&Failure(), kDependency);
  }
  CloseHandle(process);
  process = nullptr;
  Pid() = 0;
  if (Reader()) {
    WaitForSingleObject(Reader(), 1500);
    CloseHandle(Reader());
    Reader() = nullptr;
  }
  return false;
}

inline bool Start(const std::string& executableUtf8,
    const std::string& scriptUtf8, const std::string& host,
    const std::string& user, const std::string& password,
    const std::string& servercert) {
  if (Running() || !SafeField(host, 260) || !SafeField(user, 256) ||
      !SafeField(password, 4096) || (!servercert.empty() &&
      !SafeField(servercert, 100))) return false;
  for (const auto c : host) {
    if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
          (c >= '0' && c <= '9') || c == '-' || c == '.' || c == ':')) {
      return false;
    }
  }
  const auto executable = FromUtf8(executableUtf8);
  const auto script = FromUtf8(scriptUtf8);
  if (!TrustedFile(executable, L"openconnect.exe")) return false;
  if (!TrustedFile(script, L"vpnc-script-win.js") &&
      !TrustedFile(script, L"vpnc-script.js")) return false;

  if (!ConsoleReady()) {
    if (!AllocConsole() && !GetConsoleWindow()) return false;
    SetConsoleCtrlHandler(nullptr, TRUE);  // Do not interrupt Flutter itself.
    if (HWND console = GetConsoleWindow()) ShowWindow(console, SW_HIDE);
    ConsoleReady() = true;
  }

  SECURITY_ATTRIBUTES sa = {sizeof(sa), nullptr, TRUE};
  HANDLE inputRead = nullptr, inputWrite = nullptr;
  if (!CreatePipe(&inputRead, &inputWrite, &sa, 0)) return false;
  if (!SetHandleInformation(inputWrite, HANDLE_FLAG_INHERIT, 0)) {
    CloseHandle(inputRead); CloseHandle(inputWrite);
    return false;
  }
  HANDLE errorRead = nullptr, errorWrite = nullptr;
  if (!CreatePipe(&errorRead, &errorWrite, &sa, 0) ||
      !SetHandleInformation(errorRead, HANDLE_FLAG_INHERIT, 0)) {
    if (errorRead) CloseHandle(errorRead);
    if (errorWrite) CloseHandle(errorWrite);
    CloseHandle(inputRead); CloseHandle(inputWrite);
    return false;
  }
  InterlockedExchange(&Failure(), kUnknown);
  InterlockedExchange(&Authenticated(), 0);

  std::wstring command = Quote(executable) +
      L" --protocol=anyconnect --non-inter --passwd-on-stdin --no-proxy" +
      L" --user=" + Quote(FromUtf8(user)) +
      L" --script=" + Quote(script) +
      (servercert.empty() ? L"" :
        L" --servercert=" + Quote(FromUtf8(servercert))) +
      L" " + Quote(FromUtf8(host));
  std::wstring mutableCommand = command;
  STARTUPINFOW startup = {};
  startup.cb = sizeof(startup);
  startup.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
  startup.wShowWindow = SW_HIDE;
  startup.hStdInput = inputRead;
  // Merge stdout and stderr into the private classifier pipe: upstream
  // OpenConnect emits lifecycle diagnostics to either stream.
  startup.hStdOutput = errorWrite;
  startup.hStdError = errorWrite;
  PROCESS_INFORMATION pi = {};
  const bool created = CreateProcessW(executable.c_str(),
      mutableCommand.data(), nullptr, nullptr, TRUE,
      CREATE_NEW_PROCESS_GROUP,
      nullptr, nullptr, &startup, &pi) != FALSE;
  CloseHandle(inputRead);
  CloseHandle(errorWrite);
  if (!created) {
    CloseHandle(inputWrite);
    CloseHandle(errorRead);
    return false;
  }
  Reader() = CreateThread(nullptr, 0, ConsumeErrors, errorRead, 0, nullptr);
  if (!Reader()) {
    CloseHandle(errorRead);
    CloseHandle(inputWrite);
    GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, pi.dwProcessId);
    WaitForSingleObject(pi.hProcess, 5000);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return false;
  }
  // Credential is delivered through a one-shot stdin pipe, never via argv.
  const std::string secret = password + "\n";
  DWORD written = 0;
  const bool supplied = WriteFile(inputWrite, secret.data(),
      static_cast<DWORD>(secret.size()), &written, nullptr) != FALSE &&
      written == secret.size();
  CloseHandle(inputWrite);
  if (!supplied) {
    // Fail closed: child cannot authenticate. The process is still ours.
    GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, pi.dwProcessId);
    WaitForSingleObject(pi.hProcess, 5000);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    WaitForSingleObject(Reader(), 1500);
    CloseHandle(Reader());
    Reader() = nullptr;
    return false;
  }
  Child() = pi.hProcess;
  Pid() = pi.dwProcessId;
  CloseHandle(pi.hThread);
  return true;
}

inline bool Stop() {
  if (!Running()) return true;
  // OpenConnect should invoke the disconnect vpnc-script upon CTRL_BREAK.
  if (!GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, Pid())) return false;
  if (WaitForSingleObject(Child(), 12000) != WAIT_OBJECT_0) return false;
  CloseHandle(Child());
  Child() = nullptr;
  Pid() = 0;
  if (Reader()) {
    WaitForSingleObject(Reader(), 1500);
    CloseHandle(Reader());
    Reader() = nullptr;
  }
  return true;
}
}  // namespace twinconnect_openconnect
