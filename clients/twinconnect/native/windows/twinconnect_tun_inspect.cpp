// Independent Windows SDK translation unit to avoid Flutter runner's
// earlier Windows header targets hiding IP Helper API v2 declarations.
#ifndef WINVER
#define WINVER 0x0A00
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif
#ifndef NTDDI_VERSION
#define NTDDI_VERSION 0x0A000000
#endif

#include <winsock2.h>
#include <windows.h>
#include <iphlpapi.h>
#include <netioapi.h>
#include <cwchar>
#include "twinconnect_tun_inspect.h"
#pragma comment(lib, "Iphlpapi.lib")

namespace twinconnect_tun_inspect {

flutter::EncodableValue Inspect() {
  flutter::EncodableMap output;
  auto put = [&](const char* key, bool value) {
    output[flutter::EncodableValue(key)] = flutter::EncodableValue(value);
  };
  MIB_IF_TABLE2* table = nullptr;
  if (GetIfTable2(&table) != NO_ERROR || table == nullptr) {
    put("inspectionOk", false);
    return flutter::EncodableValue(output);
  }
  NET_LUID target = {};
  ULONG index = 0;
  bool found = false;
  bool up = false;
  for (ULONG i = 0; i < table->NumEntries; ++i) {
    const auto& row = table->Table[i];
    if (_wcsicmp(row.Alias, L"TwinConnectSB") == 0) {
      target = row.InterfaceLuid;
      index = row.InterfaceIndex;
      found = true;
      up = row.OperStatus == IfOperStatusUp;
      break;
    }
  }
  FreeMibTable(table);
  put("adapterPresent", found);
  if (!found) {
    put("inspectionOk", true);
    put("defaultRoutePresent", false);
    return flutter::EncodableValue(output);
  }
  put("adapterUp", up);

  MIB_IPFORWARD_TABLE2* routes = nullptr;
  if (GetIpForwardTable2(AF_INET, &routes) != NO_ERROR || routes == nullptr) {
    put("inspectionOk", false);
    return flutter::EncodableValue(output);
  }
  bool default_route = false;
  for (ULONG i = 0; i < routes->NumEntries; ++i) {
    const auto& route = routes->Table[i];
    if (route.InterfaceLuid.Value != target.Value) continue;
    if (route.DestinationPrefix.PrefixLength <= 1) {
      default_route = true;
      break;
    }
  }
  FreeMibTable(routes);
  put("inspectionOk", true);
  put("defaultRoutePresent", default_route);
  // Test the actual best IPv4 route rather than just the presence of one.
  MIB_IPFORWARDROW best = {};
  const DWORD best_status = GetBestRoute(0x01010101UL, 0, &best);
  put("bestRouteKnown", best_status == NO_ERROR);
  if (best_status == NO_ERROR) {
    put("tunPreferred", best.dwForwardIfIndex == index);
  }
  return flutter::EncodableValue(output);
}

}  // namespace twinconnect_tun_inspect
