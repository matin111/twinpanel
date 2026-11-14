// TwinConnect selected-app VPN bypass guard.
// Persistent WFP filters block ONE selected app on interfaces OTHER than the
// verified TwinConnect tunnel. This is not a whole-device Kill Switch.
// Only an Administrator may run the bundled CLI. Recovery works offline.
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
#include <cwchar>
#include <cstring>
#include <string>
#include <cstdio>
#pragma comment(lib, "Fwpuclnt.lib")
#pragma comment(lib, "Iphlpapi.lib")
#pragma comment(lib, "Rpcrt4.lib")
#pragma comment(lib, "Advapi32.lib")

namespace {
const GUID sublayer = {0x7c77bb10,0x62e4,0x410c,{0xa1,0xe4,0x7c,0x4b,0x3d,0x19,0x22,0xf2}};
const GUID v4 = {0x7c77bb11,0x62e4,0x410c,{0xa1,0xe4,0x7c,0x4b,0x3d,0x19,0x22,0xf2}};
const GUID v6 = {0x7c77bb12,0x62e4,0x410c,{0xa1,0xe4,0x7c,0x4b,0x3d,0x19,0x22,0xf2}};
struct Engine {
  HANDLE h = nullptr;
  ~Engine() { if (h) FwpmEngineClose0(h); }
};
DWORD Open(Engine& e) {
  return FwpmEngineOpen0(nullptr, RPC_C_AUTHN_WINNT, nullptr, nullptr, &e.h);
}
bool IsAdmin() {
  BOOL admin = FALSE;
  SID_IDENTIFIER_AUTHORITY authority = SECURITY_NT_AUTHORITY;
  PSID sid = nullptr;
  if (AllocateAndInitializeSid(&authority, 2, SECURITY_BUILTIN_DOMAIN_RID,
      DOMAIN_ALIAS_RID_ADMINS, 0, 0, 0, 0, 0, 0, &sid)) {
    CheckTokenMembership(nullptr, sid, &admin);
    FreeSid(sid);
  }
  return admin != FALSE;
}
bool AppBlob(const wchar_t* path, FWP_BYTE_BLOB** app) {
  *app = nullptr;
  return FwpmGetAppIdFromFileName0(path, app) == ERROR_SUCCESS && *app;
}
bool IsTrustedApp(const wchar_t* path) {
  if (!path || !*path) return false;
  const wchar_t* ext = wcsrchr(path, L'.');
  if (!ext || _wcsicmp(ext, L".exe") != 0) return false;
  DWORD attributes = GetFileAttributesW(path);
  return attributes != INVALID_FILE_ATTRIBUTES &&
      (attributes & FILE_ATTRIBUTE_DIRECTORY) == 0;
}
bool TunnelLuid(const wchar_t* alias, UINT64* result) {
  if (!alias || (_wcsicmp(alias,L"TwinConnect") != 0 &&
      _wcsicmp(alias,L"TwinConnectSB") != 0)) return false;
  NET_LUID luid = {};
  if (ConvertInterfaceAliasToLuid(alias, &luid) != NO_ERROR ||
      luid.Value == 0) return false;
  MIB_IF_ROW2 row = {};
  row.InterfaceLuid = luid;
  if (GetIfEntry2(&row) != NO_ERROR || row.OperStatus != IfOperStatusUp ||
      row.InterfaceAndOperStatusFlags.HardwareInterface ||
      row.Type == IF_TYPE_SOFTWARE_LOOPBACK) return false;
  *result = luid.Value;
  return true;
}
FWPM_FILTER0* Get(HANDLE engine, const GUID& key) {
  FWPM_FILTER0* f = nullptr;
  if (FwpmFilterGetByKey0(engine, &key, &f) != ERROR_SUCCESS) return nullptr;
  return f;
}
bool OwnedValid(const FWPM_FILTER0* f, const GUID& layer,
                const FWP_BYTE_BLOB* app, UINT64* luid) {
  if (!f || !f->filterCondition || f->numFilterConditions != 2 ||
      !InlineIsEqualGUID(f->layerKey, layer) ||
      !InlineIsEqualGUID(f->subLayerKey, sublayer) ||
      (f->flags & FWPM_FILTER_FLAG_PERSISTENT) == 0 ||
      f->action.type != FWP_ACTION_BLOCK) return false;
  const auto& a = f->filterCondition[0];
  const auto& i = f->filterCondition[1];
  if (!InlineIsEqualGUID(a.fieldKey, FWPM_CONDITION_ALE_APP_ID) ||
      a.matchType != FWP_MATCH_EQUAL || a.conditionValue.type != FWP_BYTE_BLOB_TYPE ||
      !a.conditionValue.byteBlob || !app ||
      a.conditionValue.byteBlob->size != app->size ||
      memcmp(a.conditionValue.byteBlob->data, app->data, app->size) != 0 ||
      !InlineIsEqualGUID(i.fieldKey, FWPM_CONDITION_IP_LOCAL_INTERFACE) ||
      i.matchType != FWP_MATCH_NOT_EQUAL ||
      i.conditionValue.type != FWP_UINT64 ||
      !i.conditionValue.uint64 || *i.conditionValue.uint64 == 0) return false;
  if (luid) *luid = *i.conditionValue.uint64;
  return true;
}
DWORD Remove(HANDLE h, const GUID& key) {
  DWORD code = FwpmFilterDeleteByKey0(h, &key);
  return code == FWP_E_FILTER_NOT_FOUND ? ERROR_SUCCESS : code;
}
DWORD RemoveOwned(HANDLE h) {
  DWORD code = FwpmTransactionBegin0(h, 0);
  if (code != ERROR_SUCCESS) return code;
  code = Remove(h, v4);
  if (code == ERROR_SUCCESS) code = Remove(h, v6);
  if (code == ERROR_SUCCESS) {
    code = FwpmSubLayerDeleteByKey0(h, &sublayer);
    if (code == FWP_E_SUBLAYER_NOT_FOUND) code = ERROR_SUCCESS;
  }
  if (code != ERROR_SUCCESS) { FwpmTransactionAbort0(h); return code; }
  return FwpmTransactionCommit0(h);
}
DWORD Add(HANDLE h, const GUID& key, const GUID& layer,
          FWP_BYTE_BLOB* app, UINT64 interfaceLuid) {
  FWPM_FILTER_CONDITION0 c[2] = {};
  c[0].fieldKey = FWPM_CONDITION_ALE_APP_ID;
  c[0].matchType = FWP_MATCH_EQUAL;
  c[0].conditionValue.type = FWP_BYTE_BLOB_TYPE;
  c[0].conditionValue.byteBlob = app;
  c[1].fieldKey = FWPM_CONDITION_IP_LOCAL_INTERFACE;
  c[1].matchType = FWP_MATCH_NOT_EQUAL;
  c[1].conditionValue.type = FWP_UINT64;
  c[1].conditionValue.uint64 = &interfaceLuid;
  FWPM_FILTER0 f = {};
  f.filterKey = key;
  f.displayData.name = const_cast<wchar_t*>(L"TwinConnect Selected App VPN Bypass Block");
  f.layerKey = layer;
  f.subLayerKey = sublayer;
  f.flags = FWPM_FILTER_FLAG_PERSISTENT;
  f.action.type = FWP_ACTION_BLOCK;
  f.weight.type = FWP_UINT8;
  f.weight.uint8 = 225;
  f.filterCondition = c;
  f.numFilterConditions = 2;
  return FwpmFilterAdd0(h, &f, nullptr, nullptr);
}
DWORD Arm(HANDLE h, FWP_BYTE_BLOB* app, UINT64 luid) {
  // Never replace rules for another app or adapter without explicit recovery.
  FWPM_FILTER0* old4 = Get(h, v4);
  FWPM_FILTER0* old6 = Get(h, v6);
  UINT64 a = 0, b = 0;
  bool already = OwnedValid(old4, FWPM_LAYER_ALE_AUTH_CONNECT_V4, app, &a) &&
      OwnedValid(old6, FWPM_LAYER_ALE_AUTH_CONNECT_V6, app, &b) &&
      a == luid && b == luid;
  if (old4) FwpmFreeMemory0(reinterpret_cast<void**>(&old4));
  if (old6) FwpmFreeMemory0(reinterpret_cast<void**>(&old6));
  if (already) return ERROR_SUCCESS;
  // Fail closed on an existing conflicting or incomplete policy.
  old4 = Get(h, v4);
  old6 = Get(h, v6);
  bool occupied = old4 || old6;
  if (old4) FwpmFreeMemory0(reinterpret_cast<void**>(&old4));
  if (old6) FwpmFreeMemory0(reinterpret_cast<void**>(&old6));
  if (occupied) return ERROR_ALREADY_EXISTS;
  DWORD code = FwpmTransactionBegin0(h, 0);
  if (code != ERROR_SUCCESS) return code;
  FWPM_SUBLAYER0 layer = {};
  layer.subLayerKey = sublayer;
  layer.displayData.name = const_cast<wchar_t*>(L"TwinConnect Selected App Guard");
  layer.flags = FWPM_SUBLAYER_FLAG_PERSISTENT;
  layer.weight = 0xD400;
  code = FwpmSubLayerAdd0(h, &layer, nullptr);
  if (code == FWP_E_ALREADY_EXISTS) code = ERROR_SUCCESS;
  if (code == ERROR_SUCCESS) code = Add(h, v4, FWPM_LAYER_ALE_AUTH_CONNECT_V4, app, luid);
  if (code == ERROR_SUCCESS) code = Add(h, v6, FWPM_LAYER_ALE_AUTH_CONNECT_V6, app, luid);
  if (code != ERROR_SUCCESS) { FwpmTransactionAbort0(h); return code; }
  code = FwpmTransactionCommit0(h);
  if (code != ERROR_SUCCESS) return code;
  // Confirm exact application identity and adapter LUID on both stacks.
  old4 = Get(h, v4);
  old6 = Get(h, v6);
  a = 0; b = 0;
  bool verified = OwnedValid(old4,FWPM_LAYER_ALE_AUTH_CONNECT_V4,app,&a) &&
      OwnedValid(old6,FWPM_LAYER_ALE_AUTH_CONNECT_V6,app,&b) && a==luid && b==luid;
  if (old4) FwpmFreeMemory0(reinterpret_cast<void**>(&old4));
  if (old6) FwpmFreeMemory0(reinterpret_cast<void**>(&old6));
  if (!verified) return RemoveOwned(h) == ERROR_SUCCESS ? ERROR_INVALID_STATE : ERROR_WRITE_FAULT;
  return ERROR_SUCCESS;
}
} // namespace
int wmain(int argc, wchar_t** argv) {
  // Read-only 'audit' needs no user arguments and works without the app running.
  if (argc < 2) return 2;
  const bool audit = _wcsicmp(argv[1], L"audit") == 0;
  const bool statusOnly = _wcsicmp(argv[1], L"status") == 0;
  // Reading filter status is safe for the unprivileged desktop process.
  // Persistent WFP changes still require an elevated administrator token.
  if (!audit && !statusOnly && !IsAdmin()) {
    fwprintf(stderr,L"ADMINISTRATOR_REQUIRED\n");
    return 2;
  }
  Engine engine;
  if (Open(engine) != ERROR_SUCCESS) { fwprintf(stderr,L"WFP_UNAVAILABLE\n"); return 1; }
  FWPM_FILTER0* current4 = Get(engine.h, v4);
  FWPM_FILTER0* current6 = Get(engine.h, v6);
  const bool has4 = current4 != nullptr, has6 = current6 != nullptr;
  if (current4) FwpmFreeMemory0(reinterpret_cast<void**>(&current4));
  if (current6) FwpmFreeMemory0(reinterpret_cast<void**>(&current6));
  if (audit && argc == 2) {
    wprintf(L"OWNED_APP_RULES_PRESENT %d %d\n",has4?1:0,has6?1:0);
    return 0;
  }
  if (_wcsicmp(argv[1], L"recover") == 0 && argc == 2) {
    DWORD code = RemoveOwned(engine.h);
    if (code != ERROR_SUCCESS) return 1;
    wprintf(L"TWINCONNECT_APP_RECOVERED\n");
    return 0;
  }
  if (argc < 3) return 2;
  const wchar_t* appPath = argv[2];
  if (!IsTrustedApp(appPath)) { fwprintf(stderr,L"INVALID_APP_PATH\n"); return 2; }
  FWP_BYTE_BLOB* app = nullptr;
  if (!AppBlob(appPath, &app)) { fwprintf(stderr,L"APP_ID_FAILED\n"); return 1; }
  const bool status = _wcsicmp(argv[1], L"status") == 0;
  const bool disarm = _wcsicmp(argv[1], L"disarm") == 0;
  const bool arm = _wcsicmp(argv[1], L"arm") == 0;
  if (!status && !disarm && !arm) { FwpmFreeMemory0(reinterpret_cast<void**>(&app)); return 2; }
  current4 = Get(engine.h, v4);
  current6 = Get(engine.h, v6);
  UINT64 luid4 = 0,luid6 = 0;
  bool matched = OwnedValid(current4,FWPM_LAYER_ALE_AUTH_CONNECT_V4,app,&luid4) &&
      OwnedValid(current6,FWPM_LAYER_ALE_AUTH_CONNECT_V6,app,&luid6) &&
      luid4 == luid6;
  if (current4) FwpmFreeMemory0(reinterpret_cast<void**>(&current4));
  if (current6) FwpmFreeMemory0(reinterpret_cast<void**>(&current6));
  DWORD result = ERROR_SUCCESS;
  if (status) {
    if (!has4 && !has6) wprintf(L"TWINCONNECT_APP_UNLOCKED\n");
    else if (matched) wprintf(L"TWINCONNECT_APP_LOCKED\n");
    else { fwprintf(stderr,L"OTHER_APP_OR_INCOMPLETE_POLICY\n"); result = ERROR_INVALID_STATE; }
  } else if (disarm) {
    if (!has4 && !has6) wprintf(L"TWINCONNECT_APP_UNLOCKED\n");
    else if (!matched) { fwprintf(stderr,L"OTHER_APP_OR_INCOMPLETE_POLICY\n"); result=ERROR_ACCESS_DENIED; }
    else {
      result = RemoveOwned(engine.h);
      if (result == ERROR_SUCCESS) wprintf(L"TWINCONNECT_APP_UNLOCKED\n");
    }
  } else {
    UINT64 tunnel = 0;
    if (argc != 4 || !TunnelLuid(argv[3], &tunnel)) {
      fwprintf(stderr,L"VERIFIED_TWINCONNECT_TUNNEL_REQUIRED\n");
      result = ERROR_INVALID_PARAMETER;
    } else {
      result = Arm(engine.h, app, tunnel);
      if (result == ERROR_SUCCESS) wprintf(L"TWINCONNECT_APP_LOCKED\n");
    }
  }
  FwpmFreeMemory0(reinterpret_cast<void**>(&app));
  return result == ERROR_SUCCESS ? 0 : 1;
}
