#pragma once

// Windows TUN diagnostics based on long-supported IP Helper APIs.
// No PowerShell or network mutation. No account data is inspected or logged.
#include <windows.h>
#include <iphlpapi.h>
#include <iptypes.h>
#include <iprtrmib.h>
#include <flutter/encodable_value.h>
#include <string>
#include <vector>
#include <cwchar>
#pragma comment(lib, "Iphlpapi.lib")

namespace twinconnect_tun_inspect {

inline flutter::EncodableValue Inspect() {
  flutter::EncodableMap output;
  const auto put = [&](const char* key, bool value) {
    output[flutter::EncodableValue(key)] = flutter::EncodableValue(value);
  };

  // GetAdaptersAddresses is supported on Windows XP and later and does not
  // depend on the newer MIB_IF_TABLE2 SDK feature guards.
  ULONG buffer_size = 0;
  ULONG status = GetAdaptersAddresses(
      AF_UNSPEC, GAA_FLAG_INCLUDE_ALL_INTERFACES,
      nullptr, nullptr, &buffer_size);
  if (status != ERROR_BUFFER_OVERFLOW || buffer_size == 0 ||
      buffer_size > 8 * 1024 * 1024) {
    put("inspectionOk", false);
    return flutter::EncodableValue(output);
  }
  std::vector<BYTE> adapter_buffer(buffer_size);
  auto adapters = reinterpret_cast<PIP_ADAPTER_ADDRESSES>(
      adapter_buffer.data());
  status = GetAdaptersAddresses(
      AF_UNSPEC, GAA_FLAG_INCLUDE_ALL_INTERFACES,
      nullptr, adapters, &buffer_size);
  if (status != NO_ERROR) {
    put("inspectionOk", false);
    return flutter::EncodableValue(output);
  }
  ULONG target_index = 0;
  bool adapter_up = false;
  for (auto* adapter = adapters; adapter; adapter = adapter->Next) {
    if (adapter->FriendlyName &&
        _wcsicmp(adapter->FriendlyName, L"TwinConnectSB") == 0) {
      target_index = adapter->IfIndex;
      adapter_up = static_cast<unsigned>(adapter->OperStatus) == 1;
      break;
    }
  }
  put("adapterPresent", target_index != 0);
  if (target_index == 0) {
    put("inspectionOk", true);
    put("defaultRoutePresent", false);
    return flutter::EncodableValue(output);
  }
  put("adapterUp", adapter_up);

  // GetIpForwardTable is also available on Windows XP+, unlike the API v2
  // structs which some Flutter SDK templates hide behind older target macros.
  ULONG route_bytes = 0;
  status = GetIpForwardTable(nullptr, &route_bytes, FALSE);
  if (status != ERROR_INSUFFICIENT_BUFFER || route_bytes == 0 ||
      route_bytes > 8 * 1024 * 1024) {
    put("inspectionOk", false);
    return flutter::EncodableValue(output);
  }
  std::vector<BYTE> route_buffer(route_bytes);
  auto* routes = reinterpret_cast<PMIB_IPFORWARDTABLE>(route_buffer.data());
  status = GetIpForwardTable(routes, &route_bytes, FALSE);
  if (status != NO_ERROR) {
    put("inspectionOk", false);
    return flutter::EncodableValue(output);
  }
  bool default_route = false;
  for (DWORD i = 0; i < routes->dwNumEntries; ++i) {
    const auto& route = routes->table[i];
    if (route.dwForwardIfIndex != target_index) continue;
    // 0.0.0.0/0 and /1 split default, including network-byte-order
    // representations of the /1 mask on little-endian hosts.
    if (route.dwForwardMask == 0 ||
        route.dwForwardMask == 0x80000000UL ||
        route.dwForwardMask == 0x00000080UL) {
      default_route = true;
      break;
    }
  }
  put("inspectionOk", true);
  put("defaultRoutePresent", default_route);
  return flutter::EncodableValue(output);
}

}  // namespace twinconnect_tun_inspect
