// System-wide kill-switch preflight ONLY. It never installs or deletes WFP
// filters and cannot modify the user's network. An independent privileged
// Windows service is required before any actual global lockdown is enabled.
#pragma once

#ifndef WINVER
#define WINVER 0x0A00
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif

#include <windows.h>
#include <fwpmu.h>
#include <flutter/encodable_value.h>
#pragma comment(lib, "Fwpuclnt.lib")

namespace twinconnect_global_killswitch {

inline flutter::EncodableValue Preflight() {
  // A successfully opened WFP management engine does NOT prove that traffic
  // blocking is active. The UI must never confuse capability with enforcement.
  FWPM_SESSION0 session = {};
  session.flags = FWPM_SESSION_FLAG_DYNAMIC;
  session.displayData.name = const_cast<wchar_t*>(L"TwinConnect WFP read-only probe");
  HANDLE engine = nullptr;
  const DWORD status = FwpmEngineOpen0(
      nullptr, RPC_C_AUTHN_WINNT, nullptr, &session, &engine);
  const bool wfp_ready = status == ERROR_SUCCESS && engine != nullptr;
  if (engine != nullptr) FwpmEngineClose0(engine);

  flutter::EncodableMap result = {
    {flutter::EncodableValue("contractVersion"), flutter::EncodableValue(1)},
    {flutter::EncodableValue("wfpAvailable"), flutter::EncodableValue(wfp_ready)},
    {flutter::EncodableValue("serviceInstalled"), flutter::EncodableValue(false)},
    {flutter::EncodableValue("armed"), flutter::EncodableValue(false)},
    {flutter::EncodableValue("enforcedV4"), flutter::EncodableValue(false)},
    {flutter::EncodableValue("enforcedV6"), flutter::EncodableValue(false)},
    {flutter::EncodableValue("recoveryVerified"), flutter::EncodableValue(false)},
    {flutter::EncodableValue("reason"), flutter::EncodableValue(
       wfp_ready ? "SERVICE_NOT_INSTALLED" : "WFP_ENGINE_UNAVAILABLE")},
  };
  return flutter::EncodableValue(result);
}

}  // namespace twinconnect_global_killswitch
