// TwinConnect experimental system-wide Windows outbound lock.
// NOT connected to production UI. Requires isolated-VM validation before use.
// Persistent WFP filters survive an app crash. Administrator can recover with
// the "disarm" command from a separate console/physical access.
// IMPORTANT: This prototype is not boot-time protection and must not be
// advertised as a production always-on kill switch.

#ifndef WINVER
#define WINVER 0x0A00
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00
#endif

#include <winsock2.h>
#include <windows.h>
#include <fwpmu.h>
#include <netioapi.h>
#include <ws2tcpip.h>
#include <cstdio>
#include <cwchar>
#include <string>

#pragma comment(lib, "Fwpuclnt.lib")
#pragma comment(lib, "Iphlpapi.lib")
#pragma comment(lib, "Ws2_32.lib")
#pragma comment(lib, "Rpcrt4.lib")

namespace {

// Keys are fixed and uniquely owned by this tool; never enumerate or delete
// another vendor's firewall filters.
const GUID kSubLayer = {0xb3f412ac,0x2511,0x40d3,{0x99,0x62,0x72,0x11,0x4a,0x31,0xa9,0x41}};
const GUID kBlockV4 = {0xb3f412ad,0x2511,0x40d3,{0x99,0x62,0x72,0x11,0x4a,0x31,0xa9,0x41}};
const GUID kBlockV6 = {0xb3f412ae,0x2511,0x40d3,{0x99,0x62,0x72,0x11,0x4a,0x31,0xa9,0x41}};
const GUID kPermitV4 = {0xb3f412af,0x2511,0x40d3,{0x99,0x62,0x72,0x11,0x4a,0x31,0xa9,0x41}};

struct Engine {
  HANDLE handle = nullptr;
  ~Engine() {
    if (handle != nullptr) FwpmEngineClose0(handle);
  }
};

DWORD Open(Engine& engine) {
  return FwpmEngineOpen0(nullptr, RPC_C_AUTHN_WINNT, nullptr,
                         nullptr, &engine.handle);
}

// Recovery audit intentionally checks GUID presence without validating shape.
// A malformed owned rule is still present and MUST block an uninstall.
bool OwnedFilterPresent(HANDLE handle, const GUID& key) {
  FWPM_FILTER0* filter = nullptr;
  const DWORD status = FwpmFilterGetByKey0(handle, &key, &filter);
  if (filter != nullptr) FwpmFreeMemory0(reinterpret_cast<void**>(&filter));
  return status == ERROR_SUCCESS;
}

// Read and verify the exact TwinConnect-owned filter contract. A filter
// merely existing by GUID must never be treated as proof of protection.
bool Exists(HANDLE handle, const GUID& key) {
  FWPM_FILTER0* filter = nullptr;
  const DWORD result = FwpmFilterGetByKey0(handle, &key, &filter);
  if (result != ERROR_SUCCESS || !filter) return false;

  const bool blockV4 = InlineIsEqualGUID(key, kBlockV4);
  const bool blockV6 = InlineIsEqualGUID(key, kBlockV6);
  const bool permitV4 = InlineIsEqualGUID(key, kPermitV4);
  bool valid = (blockV4 || blockV6 || permitV4) &&
      InlineIsEqualGUID(filter->subLayerKey, kSubLayer) &&
      (filter->flags & FWPM_FILTER_FLAG_PERSISTENT) != 0 &&
      InlineIsEqualGUID(filter->layerKey, blockV6
          ? FWPM_LAYER_ALE_AUTH_CONNECT_V6
          : FWPM_LAYER_ALE_AUTH_CONNECT_V4) &&
      static_cast<unsigned int>(filter->action.type) ==
          static_cast<unsigned int>(permitV4 ? FWP_ACTION_PERMIT : FWP_ACTION_BLOCK) &&
      filter->filterCondition != nullptr &&
      filter->numFilterConditions == (permitV4 ? 2u : 1u);
  if (valid && !permitV4) {
    const auto& rule = filter->filterCondition[0];
    valid = InlineIsEqualGUID(rule.fieldKey, FWPM_CONDITION_IP_LOCAL_INTERFACE) &&
        rule.matchType == FWP_MATCH_NOT_EQUAL &&
        rule.conditionValue.type == FWP_UINT64 &&
        rule.conditionValue.uint64 != nullptr &&
        *rule.conditionValue.uint64 != 0;
  }
  if (valid && permitV4) {
    const auto& app = filter->filterCondition[0];
    const auto& address = filter->filterCondition[1];
    valid = InlineIsEqualGUID(app.fieldKey, FWPM_CONDITION_ALE_APP_ID) &&
        app.matchType == FWP_MATCH_EQUAL &&
        app.conditionValue.type == FWP_BYTE_BLOB_TYPE &&
        app.conditionValue.byteBlob != nullptr &&
        app.conditionValue.byteBlob->size > 0 &&
        InlineIsEqualGUID(address.fieldKey, FWPM_CONDITION_IP_REMOTE_ADDRESS) &&
        address.matchType == FWP_MATCH_EQUAL &&
        address.conditionValue.type == FWP_UINT32 &&
        address.conditionValue.uint32 != 0;
  }
  FwpmFreeMemory0(reinterpret_cast<void**>(&filter));
  return valid;
}

DWORD RemoveOwned(HANDLE handle, const GUID& key) {
  const DWORD status = FwpmFilterDeleteByKey0(handle, &key);
  return status == FWP_E_FILTER_NOT_FOUND ? ERROR_SUCCESS : status;
}

DWORD AddBlockRule(HANDLE engine, const GUID& key, const GUID& layer,
                   const UINT64 localInterfaceLuid) {
  FWPM_FILTER_CONDITION0 condition = {};
  condition.fieldKey = FWPM_CONDITION_IP_LOCAL_INTERFACE;
  condition.matchType = FWP_MATCH_NOT_EQUAL;
  condition.conditionValue.type = FWP_UINT64;
  UINT64 luid = localInterfaceLuid;
  condition.conditionValue.uint64 = &luid;

  FWPM_FILTER0 filter = {};
  filter.filterKey = key;
  filter.displayData.name =
      const_cast<wchar_t*>(L"TwinConnect experimental outbound block");
  filter.layerKey = layer;
  filter.subLayerKey = kSubLayer;
  filter.flags = FWPM_FILTER_FLAG_PERSISTENT;
  filter.action.type = FWP_ACTION_BLOCK;
  filter.weight.type = FWP_UINT8;
  filter.weight.uint8 = 200;
  filter.numFilterConditions = 1;
  filter.filterCondition = &condition;
  return FwpmFilterAdd0(engine, &filter, nullptr, nullptr);
}

// An IP-only exception is a privacy leak: unrelated applications could
// connect directly to the same server. Require BOTH exact executable AppId
// and exact destination IP. Production still requires signature/ACL review.
DWORD AddTransportPermit(HANDLE engine, UINT32 endpoint,
                         const std::wstring& executablePath) {
  FWP_BYTE_BLOB* appId = nullptr;
  DWORD result = FwpmGetAppIdFromFileName0(executablePath.c_str(), &appId);
  if (result != ERROR_SUCCESS) return result;
  if (appId == nullptr) return ERROR_INVALID_DATA;

  FWPM_FILTER_CONDITION0 conditions[2] = {};
  conditions[0].fieldKey = FWPM_CONDITION_ALE_APP_ID;
  conditions[0].matchType = FWP_MATCH_EQUAL;
  conditions[0].conditionValue.type = FWP_BYTE_BLOB_TYPE;
  conditions[0].conditionValue.byteBlob = appId;
  conditions[1].fieldKey = FWPM_CONDITION_IP_REMOTE_ADDRESS;
  conditions[1].matchType = FWP_MATCH_EQUAL;
  conditions[1].conditionValue.type = FWP_UINT32;
  conditions[1].conditionValue.uint32 = endpoint;

  FWPM_FILTER0 filter = {};
  filter.filterKey = kPermitV4;
  filter.displayData.name =
      const_cast<wchar_t*>(L"TwinConnect experimental transport permit");
  filter.layerKey = FWPM_LAYER_ALE_AUTH_CONNECT_V4;
  filter.subLayerKey = kSubLayer;
  filter.flags = FWPM_FILTER_FLAG_PERSISTENT;
  filter.action.type = FWP_ACTION_PERMIT;
  filter.weight.type = FWP_UINT8;
  filter.weight.uint8 = 250;
  filter.numFilterConditions = 2;
  filter.filterCondition = conditions;
  result = FwpmFilterAdd0(engine, &filter, nullptr, nullptr);
  FwpmFreeMemory0(reinterpret_cast<void**>(&appId));
  return result;
}

DWORD EnsureSubLayer(HANDLE engine) {
  FWPM_SUBLAYER0 layer = {};
  layer.subLayerKey = kSubLayer;
  layer.displayData.name =
      const_cast<wchar_t*>(L"TwinConnect experimental system guard");
  layer.flags = FWPM_SUBLAYER_FLAG_PERSISTENT;
  layer.weight = 0xD000;
  const DWORD status = FwpmSubLayerAdd0(engine, &layer, nullptr);
  return status == FWP_E_ALREADY_EXISTS ? ERROR_SUCCESS : status;
}

DWORD TransactionalDisarm(HANDLE engine);

DWORD TransactionalArm(HANDLE engine, UINT64 tunnelLuid, UINT32 endpoint,
                       const std::wstring& executablePath) {
  DWORD result = FwpmTransactionBegin0(engine, 0);
  if (result != ERROR_SUCCESS) return result;
  result = EnsureSubLayer(engine);
  if (result == ERROR_SUCCESS) result = RemoveOwned(engine, kBlockV4);
  if (result == ERROR_SUCCESS) result = RemoveOwned(engine, kBlockV6);
  if (result == ERROR_SUCCESS) result = RemoveOwned(engine, kPermitV4);
  if (result == ERROR_SUCCESS)
    result = AddTransportPermit(engine, endpoint, executablePath);
  if (result == ERROR_SUCCESS)
    result = AddBlockRule(engine, kBlockV4, FWPM_LAYER_ALE_AUTH_CONNECT_V4,
                          tunnelLuid);
  if (result == ERROR_SUCCESS)
    result = AddBlockRule(engine, kBlockV6, FWPM_LAYER_ALE_AUTH_CONNECT_V6,
                          tunnelLuid);
  if (result != ERROR_SUCCESS) {
    FwpmTransactionAbort0(engine);
    return result;
  }
  result = FwpmTransactionCommit0(engine);
  if (result != ERROR_SUCCESS) return result;
  if (Exists(engine, kBlockV4) && Exists(engine, kBlockV6) &&
      Exists(engine, kPermitV4)) return ERROR_SUCCESS;
  // A committed but unverifiable policy must be rolled back immediately,
  // rather than leaving hidden persistent firewall rules behind.
  const DWORD recovery = TransactionalDisarm(engine);
  return recovery == ERROR_SUCCESS ? ERROR_INVALID_STATE : recovery;
}

DWORD TransactionalDisarm(HANDLE engine) {
  DWORD result = FwpmTransactionBegin0(engine, 0);
  if (result != ERROR_SUCCESS) return result;
  result = RemoveOwned(engine, kBlockV4);
  if (result == ERROR_SUCCESS) result = RemoveOwned(engine, kBlockV6);
  if (result == ERROR_SUCCESS) result = RemoveOwned(engine, kPermitV4);
  // Leave only our sublayer removed; do not touch Windows firewall profiles.
  if (result == ERROR_SUCCESS) {
    result = FwpmSubLayerDeleteByKey0(engine, &kSubLayer);
    if (result == FWP_E_SUBLAYER_NOT_FOUND) result = ERROR_SUCCESS;
  }
  if (result != ERROR_SUCCESS) {
    FwpmTransactionAbort0(engine);
    return result;
  }
  return FwpmTransactionCommit0(engine);
}

void PrintStatus(HANDLE engine) {
  const bool v4 = Exists(engine, kBlockV4);
  const bool v6 = Exists(engine, kBlockV6);
  const bool permit = Exists(engine, kPermitV4);
  wprintf(L"TwinConnect test WFP: IPv4=%ls IPv6=%ls appPermit=%ls\n",
          v4 ? L"armed" : L"off", v6 ? L"armed" : L"off",
          permit ? L"present" : L"absent");
  if (v4 != v6 || v4 != permit) {
    wprintf(L"INCOMPLETE: run disarm with offline recovery access.\n");
  }
}

void Usage() {
  wprintf(L"Experimental WFP guard (NOT production Kill Switch)\n"
          L" status\n"
          L" arm <verified-tunnel-interface-alias> <VPN-endpoint-IPv4> "
          L"<trusted-transport-executable> I_ACCEPT_OFFLINE_RECOVERY\n"
          L" disarm I_ACCEPT_OFFLINE_RECOVERY\n"
          L"Run only on disposable Windows VM with administrator rights.\n");
}

} // namespace

#ifndef TWINCONNECT_GUARD_NO_MAIN
int wmain(int argc, wchar_t** argv) {
  if (argc < 2) { Usage(); return 2; }
  Engine engine;
  DWORD result = Open(engine);
  if (result != ERROR_SUCCESS) {
    fwprintf(stderr, L"Cannot open WFP engine: 0x%08lx\n", result);
    return 1;
  }
  if (_wcsicmp(argv[1], L"status") == 0 && argc == 2) {
    PrintStatus(engine.handle);
    return 0;
  }
  if (_wcsicmp(argv[1], L"disarm") == 0 && argc == 3 &&
      wcscmp(argv[2], L"I_ACCEPT_OFFLINE_RECOVERY") == 0) {
    result = TransactionalDisarm(engine.handle);
  } else if (_wcsicmp(argv[1], L"arm") == 0 && argc == 6 &&
             wcscmp(argv[5], L"I_ACCEPT_OFFLINE_RECOVERY") == 0) {
    // Never permit choosing a physical Ethernet/Wi-Fi adapter: doing so
    // would make the block condition a no-op for direct user traffic.
    if (_wcsicmp(argv[2], L"TwinConnectSB") != 0 &&
        _wcsicmp(argv[2], L"TwinConnect") != 0) {
      fwprintf(stderr, L"Only TwinConnect-owned tunnel aliases are allowed.\n");
      return 2;
    }
    NET_LUID interfaceLuid = {};
    if (ConvertInterfaceAliasToLuid(argv[2], &interfaceLuid)
        != NO_ERROR || interfaceLuid.Value == 0) {
      fwprintf(stderr, L"Verified VPN interface not found.\n");
      return 2;
    }
    IN_ADDR address = {};
    if (InetPtonW(AF_INET, argv[3], &address) != 1) {
      fwprintf(stderr, L"Endpoint must be a numeric IPv4 address.\n");
      return 2;
    }
    const UINT32 endpoint = ntohl(address.S_un.S_addr);
    if (endpoint == 0 || endpoint == 0xFFFFFFFF ||
        (endpoint >> 24) == 127 || (endpoint >> 24) >= 224) {
      fwprintf(stderr, L"Unsupported VPN endpoint address.\n");
      return 2;
    }
    const std::wstring programPath(argv[4]);
    const DWORD flags = GetFileAttributesW(programPath.c_str());
    const std::wstring trusted = L"C:\\Program Files\\";
    const std::wstring trusted86 = L"C:\\Program Files (x86)\\";
    const bool managedPath =
        (programPath.size() > trusted.size() &&
         _wcsnicmp(programPath.c_str(), trusted.c_str(), trusted.size()) == 0) ||
        (programPath.size() > trusted86.size() &&
         _wcsnicmp(programPath.c_str(), trusted86.c_str(), trusted86.size()) == 0);
    if (!managedPath || flags == INVALID_FILE_ATTRIBUTES ||
        (flags & FILE_ATTRIBUTE_DIRECTORY)) {
      fwprintf(stderr, L"Transport executable must be installed in Program Files.\n");
      return 2;
    }
    result = TransactionalArm(engine.handle, interfaceLuid.Value,
                              endpoint, programPath);
  } else {
    Usage();
    return 2;
  }

  if (result != ERROR_SUCCESS) {
    fwprintf(stderr, L"WFP transaction failed: 0x%08lx\n", result);
    return 1;
  }
  PrintStatus(engine.handle);
  return 0;
}
#endif  // TWINCONNECT_GUARD_NO_MAIN
