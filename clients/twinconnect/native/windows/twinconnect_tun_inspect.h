#pragma once

// Read-only Windows IP Helper inspection for TwinConnect sing-box TUN.
// No shell, PowerShell, route mutation, or sensitive account information.
#include <windows.h>
#include <iphlpapi.h>
#include <netioapi.h>
#include <flutter/encodable_value.h>
#include <string>
#pragma comment(lib, "Iphlpapi.lib")

namespace twinconnect_tun_inspect {

inline flutter::EncodableValue Inspect() {
  flutter::EncodableMap data;
  auto put = [&](const char* name, bool v) {
    data[flutter::EncodableValue(name)] = flutter::EncodableValue(v);
  };
  MIB_IF_TABLE2* interfaces = nullptr;
  const DWORD interfaces_status = GetIfTable2(&interfaces);
  if (interfaces_status != NO_ERROR || interfaces == nullptr) {
    put("inspectionOk", false);
    return flutter::EncodableValue(data);
  }
  NET_LUID target = {};
  bool found = false;
  for (ULONG i = 0; i < interfaces->NumEntries; ++i) {
    const MIB_IF_ROW2& row = interfaces->Table[i];
    if (_wcsicmp(row.Alias, L"TwinConnectSB") == 0) {
      target = row.InterfaceLuid;
      found = true;
      put("adapterUp", row.OperStatus == IfOperStatusUp);
      break;
    }
  }
  FreeMibTable(interfaces);
  put("adapterPresent", found);
  if (!found) {
    put("inspectionOk", true);
    put("defaultRoutePresent", false);
    return flutter::EncodableValue(data);
  }
  MIB_IPFORWARD_TABLE2* routes = nullptr;
  const DWORD routes_status = GetIpForwardTable2(AF_INET, &routes);
  if (routes_status != NO_ERROR || routes == nullptr) {
    put("inspectionOk", false);
    return flutter::EncodableValue(data);
  }
  bool found_route = false;
  for (ULONG i = 0; i < routes->NumEntries; ++i) {
    const MIB_IPFORWARD_ROW2& route = routes->Table[i];
    if (route.InterfaceLuid.Value != target.Value) continue;
    const auto& prefix = route.DestinationPrefix;
    // Valid IPv4 /1 routes are always 0.0.0.0/1 or 128.0.0.0/1.
    // Avoid endianness-dependent address parsing in the native runner.
    if (prefix.PrefixLength == 0 || prefix.PrefixLength == 1) {
      found_route = true;
      break;
    }
  }
  FreeMibTable(routes);
  put("inspectionOk", true);
  put("defaultRoutePresent", found_route);
  return flutter::EncodableValue(data);
}

}  // namespace twinconnect_tun_inspect
