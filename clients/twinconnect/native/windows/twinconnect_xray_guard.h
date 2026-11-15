#pragma once
// Guard ONLY the Xray-core executable shipped beside TwinConnect.
// Terminate the app-owned child if the application exits unexpectedly.
#include <windows.h>
#include <cwchar>
#include <string>
#include <cstdint>

namespace twinconnect_xray_guard {
inline HANDLE& Job() {
  static HANDLE job = nullptr;
  return job;
}
inline bool IsBundledEngine(HANDLE process) {
  wchar_t image[MAX_PATH * 2] = {};
  DWORD n = static_cast<DWORD>(sizeof(image) / sizeof(wchar_t));
  if (!QueryFullProcessImageNameW(process, 0, image, &n) || n == 0)
    return false;
  wchar_t own[MAX_PATH * 2] = {};
  const DWORD length = GetModuleFileNameW(
      nullptr, own, static_cast<DWORD>(sizeof(own) / sizeof(wchar_t)));
  if (length == 0 || length >= sizeof(own) / sizeof(wchar_t))
    return false;
  std::wstring expected(own);
  const auto slash = expected.find_last_of(L"\\/");
  if (slash == std::wstring::npos) return false;
  expected.resize(slash + 1);
  expected += L"engines\\xray\\xray.exe";
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
  const bool attached = AssignProcessToJobObject(Job(), child) != FALSE;
  CloseHandle(child);
  return attached;
}
} // namespace twinconnect_xray_guard
