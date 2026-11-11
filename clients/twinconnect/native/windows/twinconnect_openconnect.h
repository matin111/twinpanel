#pragma once
// TwinConnect-owned Cisco/OpenConnect runtime. Never controls arbitrary
// OpenConnect processes or accepts an external executable outside our bundle.
// A console process group lets CTRL_BREAK reach OpenConnect so vpnc-script
// can restore Windows routes and DNS on disconnect.
#include <windows.h>
#include <string>
#include <cstdint>
#include <algorithm>

namespace twinconnect_openconnect {

inline HANDLE& Child() { static HANDLE process = nullptr; return process; }
inline DWORD& Pid() { static DWORD pid = 0; return pid; }
inline bool& ConsoleReady() { static bool ready = false; return ready; }

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
  CloseHandle(process);
  process = nullptr;
  Pid() = 0;
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
  HANDLE logNull = CreateFileW(L"NUL", GENERIC_WRITE,
      FILE_SHARE_READ | FILE_SHARE_WRITE, &sa, OPEN_EXISTING,
      FILE_ATTRIBUTE_NORMAL, nullptr);
  if (logNull == INVALID_HANDLE_VALUE) {
    CloseHandle(inputRead); CloseHandle(inputWrite);
    return false;
  }
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
  startup.hStdOutput = logNull;
  startup.hStdError = logNull;
  PROCESS_INFORMATION pi = {};
  const bool created = CreateProcessW(executable.c_str(),
      mutableCommand.data(), nullptr, nullptr, TRUE,
      CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
      nullptr, nullptr, &startup, &pi) != FALSE;
  CloseHandle(inputRead);
  CloseHandle(logNull);
  if (!created) { CloseHandle(inputWrite); return false; }
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
  return true;
}
}  // namespace twinconnect_openconnect
