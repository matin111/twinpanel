#pragma once
// Guard only TwinConnect's explicitly trusted installed OpenConnect CLI.
// The guarded child is terminated if the desktop exits unexpectedly.
#include <windows.h>
#include <cwchar>
#include <string>
#include <cstdint>

namespace twinconnect_openconnect_guard {

inline HANDLE& Job() {
  static HANDLE job = nullptr;
  return job;
}

inline bool TrustedImage(HANDLE process) {
  wchar_t image[MAX_PATH * 2] = {};
  DWORD length = static_cast<DWORD>(sizeof(image) / sizeof(wchar_t));
  if (!QueryFullProcessImageNameW(process, 0, image, &length) || !length)
    return false;
  const wchar_t* variants[] = {L"ProgramFiles", L"ProgramFiles(x86)"};
  const wchar_t* folders[] = {L"OpenConnect-GUI", L"OpenConnect"};
  for (const auto* env : variants) {
    wchar_t root[MAX_PATH] = {};
    const DWORD n = GetEnvironmentVariableW(env, root, MAX_PATH);
    if (!n || n >= MAX_PATH) continue;
    for (const auto* folder : folders) {
      std::wstring expected(root);
      expected += L"\\";
      expected += folder;
      expected += L"\\openconnect.exe";
      if (_wcsicmp(image, expected.c_str()) == 0) return true;
    }
  }
  return false;
}

inline bool Guard(int64_t pid) {
  if (pid <= 0 || pid > 0xFFFFFFFFLL) return false;
  HANDLE process = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE |
      PROCESS_QUERY_LIMITED_INFORMATION, FALSE, static_cast<DWORD>(pid));
  if (!process) return false;
  if (!TrustedImage(process)) {
    CloseHandle(process);
    return false;
  }
  if (!Job()) {
    HANDLE job = CreateJobObjectW(nullptr, nullptr);
    if (!job) { CloseHandle(process); return false; }
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits = {};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                 &limits, sizeof(limits))) {
      CloseHandle(job);
      CloseHandle(process);
      return false;
    }
    Job() = job;
  }
  const bool assigned = AssignProcessToJobObject(Job(), process) != FALSE;
  CloseHandle(process);
  return assigned;
}
}  // namespace twinconnect_openconnect_guard
