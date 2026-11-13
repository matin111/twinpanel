// Read-only WFP and Windows-service preflight. Never modifies firewall state.
#pragma once
#ifndef WINVER
#define WINVER 0x0A00
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif

#include <windows.h>
#include <winsvc.h>
#include <fwpmu.h>
#include <flutter/encodable_value.h>
#pragma comment(lib, "Fwpuclnt.lib")
#pragma comment(lib, "Advapi32.lib")

namespace twinconnect_global_killswitch {

// Owned filter keys of the isolated-VM experimental tool.
// Presence alone does NOT prove that the firewall is enforcing protection.
const GUID kGuardV4 = {0xb3f412ad,0x2511,0x40d3,{0x99,0x62,0x72,0x11,0x4a,0x31,0xa9,0x41}};
const GUID kGuardV6 = {0xb3f412ae,0x2511,0x40d3,{0x99,0x62,0x72,0x11,0x4a,0x31,0xa9,0x41}};
const GUID kTransportV4 = {0xb3f412af,0x2511,0x40d3,{0x99,0x62,0x72,0x11,0x4a,0x31,0xa9,0x41}};

inline bool OwnedFilterExists(HANDLE engine, const GUID& key) {
  if (!engine) return false;
  FWPM_FILTER0* filter = nullptr;
  const DWORD status = FwpmFilterGetByKey0(engine, &key, &filter);
  if (filter) FwpmFreeMemory0(reinterpret_cast<void**>(&filter));
  return status == ERROR_SUCCESS;
}

inline bool ServicePresent(bool* running) {
  *running = false;
  SC_HANDLE scm = OpenSCManagerW(nullptr, nullptr, SC_MANAGER_CONNECT);
  if (!scm) return false;
  SC_HANDLE service = OpenServiceW(scm, L"TwinConnectGlobalGuard", SERVICE_QUERY_STATUS);
  bool found = service != nullptr;
  if (service != nullptr) {
    SERVICE_STATUS_PROCESS status = {};
    DWORD bytes = 0;
    if (QueryServiceStatusEx(service, SC_STATUS_PROCESS_INFO,
                            reinterpret_cast<LPBYTE>(&status),
                            sizeof(status), &bytes)) {
      *running = status.dwCurrentState == SERVICE_RUNNING;
    }
    CloseServiceHandle(service);
  }
  CloseServiceHandle(scm);
  return found;
}

inline flutter::EncodableValue Preflight() {
  // Opening the WFP management engine is a capability check only.
  FWPM_SESSION0 session = {};
  session.flags = FWPM_SESSION_FLAG_DYNAMIC;
  session.displayData.name = const_cast<wchar_t*>(L"TwinConnect read-only guard status");
  HANDLE engine = nullptr;
  const DWORD status = FwpmEngineOpen0(
      nullptr, RPC_C_AUTHN_WINNT, nullptr, &session, &engine);
  const bool ready = status == ERROR_SUCCESS && engine != nullptr;

  const bool v4 = ready && OwnedFilterExists(engine, kGuardV4);
  const bool v6 = ready && OwnedFilterExists(engine, kGuardV6);
  const bool transport = ready && OwnedFilterExists(engine, kTransportV4);
  if (engine) FwpmEngineClose0(engine);
  bool running = false;
  const bool installed = ServicePresent(&running);
  // Do NOT declare enforcement until recovery test results and a signed
  // service attestation can be obtained. No service implements that yet.
  const bool recoveryVerified = false;
  const bool armed = installed && running && v4 && v6 && transport &&
                     recoveryVerified;
  const char* reason = !ready ? "WFP_ENGINE_UNAVAILABLE" :
      !installed ? "SERVICE_NOT_INSTALLED" :
      !running ? "SERVICE_NOT_RUNNING" :
      !v4 || !v6 || !transport ? "FILTERS_NOT_VERIFIED" :
      "RECOVERY_NOT_VERIFIED";

  flutter::EncodableMap result = {
    {flutter::EncodableValue("contractVersion"), flutter::EncodableValue(1)},
    {flutter::EncodableValue("wfpAvailable"), flutter::EncodableValue(ready)},
    {flutter::EncodableValue("serviceInstalled"), flutter::EncodableValue(installed)},
    {flutter::EncodableValue("armed"), flutter::EncodableValue(armed)},
    {flutter::EncodableValue("enforcedV4"), flutter::EncodableValue(v4 && installed && running)},
    {flutter::EncodableValue("enforcedV6"), flutter::EncodableValue(v6 && installed && running)},
    {flutter::EncodableValue("recoveryVerified"), flutter::EncodableValue(recoveryVerified)},
    {flutter::EncodableValue("reason"), flutter::EncodableValue(reason)},
  };
  return flutter::EncodableValue(result);
}

}  // namespace twinconnect_global_killswitch
