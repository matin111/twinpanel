#pragma once
// Own and kill ONLY TwinConnect's bundled, official Sudoku CLI process.
// Stage a user-only, delete-on-close config file: the stock CLI accepts -c
// file paths (not stdin), so never place a private split key in argv/logs.
// The file disappears on explicit release OR GUI crash/process termination.
#include <windows.h>
#include <sddl.h>
#include <cwchar>
#include <string>
#include <vector>
#include <cstdint>
#include <random>

namespace twinconnect_sudoku_guard {
inline HANDLE& Job() { static HANDLE job = nullptr; return job; }
inline HANDLE& ConfigHandle() { static HANDLE handle = INVALID_HANDLE_VALUE; return handle; }
inline std::wstring& ConfigPath() { static std::wstring path; return path; }

inline bool IsBundledEngine(HANDLE process) {
  wchar_t image[MAX_PATH * 2] = {};
  DWORD n = static_cast<DWORD>(sizeof(image) / sizeof(wchar_t));
  if (!QueryFullProcessImageNameW(process, 0, image, &n) || !n) return false;
  wchar_t own[MAX_PATH * 2] = {};
  DWORD length = GetModuleFileNameW(nullptr, own,
      static_cast<DWORD>(sizeof(own) / sizeof(wchar_t)));
  if (!length || length >= sizeof(own) / sizeof(wchar_t)) return false;
  std::wstring expected(own);
  auto slash = expected.find_last_of(L"\\/");
  if (slash == std::wstring::npos) return false;
  expected.resize(slash + 1);
  expected += L"engines\\sudoku\\sudoku.exe";
  return _wcsicmp(expected.c_str(), image) == 0;
}

inline bool Guard(int64_t pid) {
  if (pid <= 0 || pid > 0xFFFFFFFFLL) return false;
  HANDLE child = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE |
      PROCESS_QUERY_LIMITED_INFORMATION, FALSE, static_cast<DWORD>(pid));
  if (!child) return false;
  if (!IsBundledEngine(child)) { CloseHandle(child); return false; }
  if (!Job()) {
    HANDLE job = CreateJobObjectW(nullptr, nullptr);
    if (!job) { CloseHandle(child); return false; }
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits = {};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                 &limits, sizeof(limits))) {
      CloseHandle(job); CloseHandle(child); return false;
    }
    Job() = job;
  }
  const bool ok = AssignProcessToJobObject(Job(), child) != FALSE;
  CloseHandle(child);
  return ok;
}

inline bool CurrentSid(std::wstring* text) {
  HANDLE token = nullptr;
  if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return false;
  DWORD bytes = 0;
  GetTokenInformation(token, TokenUser, nullptr, 0, &bytes);
  if (bytes == 0 || bytes > 65536) { CloseHandle(token); return false; }
  std::vector<unsigned char> buffer(bytes);
  if (!GetTokenInformation(token, TokenUser, buffer.data(), bytes, &bytes)) {
    CloseHandle(token); return false;
  }
  CloseHandle(token);
  auto* account = reinterpret_cast<TOKEN_USER*>(buffer.data());
  LPWSTR sid = nullptr;
  if (!ConvertSidToStringSidW(account->User.Sid, &sid)) return false;
  *text = sid;
  LocalFree(sid);
  return !text->empty();
}

inline bool SafeRoot(std::wstring* dir) {
  DWORD size = GetEnvironmentVariableW(L"LOCALAPPDATA", nullptr, 0);
  if (!size || size > 30000) return false;
  std::vector<wchar_t> buffer(size);
  if (!GetEnvironmentVariableW(L"LOCALAPPDATA", buffer.data(), size)) return false;
  std::wstring local(buffer.data());
  if (local.empty()) return false;
  *dir = local + L"\\TwinConnect";
  if (!CreateDirectoryW(dir->c_str(), nullptr) &&
      GetLastError() != ERROR_ALREADY_EXISTS) return false;
  const DWORD attributes = GetFileAttributesW(dir->c_str());
  if (attributes == INVALID_FILE_ATTRIBUTES ||
      !(attributes & FILE_ATTRIBUTE_DIRECTORY) ||
      (attributes & FILE_ATTRIBUTE_REPARSE_POINT)) return false;
  return true;
}

inline void ReleaseConfig() {
  if (ConfigHandle() != INVALID_HANDLE_VALUE) {
    CloseHandle(ConfigHandle()); // FILE_FLAG_DELETE_ON_CLOSE
    ConfigHandle() = INVALID_HANDLE_VALUE;
  }
  ConfigPath().clear();
}

inline bool StageConfig(const std::string& json, std::string* utf8Path) {
  if (!utf8Path || ConfigHandle() != INVALID_HANDLE_VALUE ||
      json.empty() || json.size() > 16384) return false;
  std::wstring dir, sid;
  if (!SafeRoot(&dir) || !CurrentSid(&sid)) return false;
  // Protected DACL: current logon account + SYSTEM ONLY.
  const std::wstring sddl = L"D:P(A;;FA;;;SY)(A;;FA;;;" + sid + L")";
  PSECURITY_DESCRIPTOR sd = nullptr;
  if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(
      sddl.c_str(), SDDL_REVISION_1, &sd, nullptr)) return false;
  SECURITY_ATTRIBUTES attrs = {sizeof(attrs), sd, FALSE};
  bool created = false;
  std::random_device random;
  for (int attempt = 0; attempt < 8 && !created; ++attempt) {
    const auto stamp = static_cast<unsigned long long>(GetTickCount64());
    const auto nonce = static_cast<unsigned long long>(random());
    const auto name = L"\\sudoku-" + std::to_wstring(GetCurrentProcessId()) +
      L"-" + std::to_wstring(stamp) + L"-" + std::to_wstring(nonce) + L".json";
    const auto path = dir + name;
    HANDLE handle = CreateFileW(path.c_str(), GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_DELETE, &attrs, CREATE_NEW,
        FILE_ATTRIBUTE_TEMPORARY | FILE_FLAG_DELETE_ON_CLOSE, nullptr);
    if (handle == INVALID_HANDLE_VALUE) continue;
    DWORD written = 0;
    if (!WriteFile(handle, json.data(), static_cast<DWORD>(json.size()),
                   &written, nullptr) || written != json.size() ||
        !FlushFileBuffers(handle)) {
      CloseHandle(handle);
      break;
    }
    int size = WideCharToMultiByte(CP_UTF8, 0, path.c_str(), -1,
                                   nullptr, 0, nullptr, nullptr);
    if (size < 2) { CloseHandle(handle); break; }
    std::string result(static_cast<size_t>(size), '\0');
    if (!WideCharToMultiByte(CP_UTF8, 0, path.c_str(), -1,
                             result.data(), size, nullptr, nullptr)) {
      CloseHandle(handle); break;
    }
    result.pop_back();
    ConfigHandle() = handle;
    ConfigPath() = path;
    *utf8Path = result;
    created = true;
  }
  LocalFree(sd);
  return created;
}
}  // namespace twinconnect_sudoku_guard
