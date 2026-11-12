#pragma once
// TwinConnect-owned Windows L2TP/IPsec through the OS RAS API.
// No subprocess command-line credentials, no network PSK inspection, and
// no changes to any phone-book entry not created by this process.
#include <windows.h>
#include <ras.h>
#include <raserror.h>
#include <string>
#include <vector>
#include <atomic>
#include <thread>
#include <algorithm>
#include <cwctype>
#include <cstdint>
#pragma comment(lib, "Rasapi32.lib")

namespace twinconnect_l2tp {

// 0 idle, 1 dialing, 2 RAS connected, 3 disconnecting, -1 error.
inline std::atomic<int>& State() {
  static std::atomic<int> state{0}; return state;
}
inline std::atomic<DWORD>& LastErrorCode() {
  static std::atomic<DWORD> error{0}; return error;
}
inline std::atomic<bool>& Cancelled() {
  static std::atomic<bool> cancel{false}; return cancel;
}
inline std::atomic<HRASCONN>& Tunnel() {
  static std::atomic<HRASCONN> handle{nullptr}; return handle;
}
inline std::wstring& EntryName() {
  static std::wstring name; return name;
}

inline std::wstring Utf8(const std::string& input) {
  if (input.empty()) return {};
  int count = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS,
      input.data(), static_cast<int>(input.size()), nullptr, 0);
  if (count <= 0) return {};
  std::wstring result(static_cast<size_t>(count), L'\0');
  if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS,
      input.data(), static_cast<int>(input.size()), result.data(), count)
      != count) return {};
  return result;
}
inline bool SecretSafe(const std::string& value, size_t maximum) {
  if (value.empty() || value.size() > maximum) return false;
  for (unsigned char c : value) {
    if (c == 0 || c < 0x20 || c == 0x7f) return false;
  }
  return true;
}
inline bool HostSafe(const std::string& host) {
  if (host.empty() || host.size() > 253 || host.front() == '-' ||
      host.back() == '.' || host.find("..") != std::string::npos) return false;
  return std::all_of(host.begin(), host.end(), [](unsigned char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
           (c >= '0' && c <= '9') || c == '.' || c == '-';
  });
}
template <size_t N>
inline bool Copy(wchar_t (&buffer)[N], const std::wstring& value) {
  if (value.empty() || value.size() >= N) return false;
  std::copy(value.begin(), value.end(), buffer);
  buffer[value.size()] = L'\0';
  return true;
}
inline void Wipe(std::wstring& value) {
  if (!value.empty()) SecureZeroMemory(value.data(),
      value.size() * sizeof(wchar_t));
  value.clear();
}

inline DWORD FindL2tpDevice(std::wstring* name) {
  if (!name) return ERROR_INVALID_PARAMETER;
  // Use the documented two-call enumeration. A single RASDEVINFO buffer
  // cannot enumerate computers that have multiple VPN miniports.
  DWORD bytes = 0, count = 0;
  DWORD rc = RasEnumDevicesW(nullptr, &bytes, &count);
  if (rc != ERROR_BUFFER_TOO_SMALL || bytes < sizeof(RASDEVINFOW) ||
      bytes > 65536) {
    return rc == ERROR_SUCCESS ? ERROR_NOT_FOUND : rc;
  }
  std::vector<BYTE> buffer(bytes, 0);
  auto* devices = reinterpret_cast<RASDEVINFOW*>(buffer.data());
  devices[0].dwSize = sizeof(RASDEVINFOW);
  rc = RasEnumDevicesW(devices, &bytes, &count);
  if (rc != ERROR_SUCCESS) return rc;
  for (DWORD i = 0; i < count; i++) {
    if (wcscmp(devices[i].szDeviceType, RASDT_Vpn) != 0) continue;
    std::wstring label(devices[i].szDeviceName);
    std::transform(label.begin(), label.end(), label.begin(),
        [](wchar_t c) { return static_cast<wchar_t>(towlower(c)); });
    if (label.find(L"l2tp") != std::wstring::npos) {
      *name = devices[i].szDeviceName;
      return ERROR_SUCCESS;
    }
  }
  return ERROR_NOT_FOUND;
}

inline void RemoveOwnedEntry(const std::wstring& name) {
  if (name.size() > 24 &&
      name.compare(0, 17, L"TwinConnect-L2TP-") == 0)
    RasDeleteEntryW(nullptr, name.c_str());
}
inline void CloseTunnel(HRASCONN conn) {
  if (!conn) return;
  RasHangUpW(conn);
  RASCONNSTATUSW status = {};
  status.dwSize = sizeof(status);
  // Wait for actual OS disconnection before deleting our own phonebook entry.
  for (int n = 0; n < 70; n++) {
    DWORD rc = RasGetConnectStatusW(conn, &status);
    if (rc == ERROR_INVALID_HANDLE) return;
    if (rc == ERROR_SUCCESS && status.rasconnstate == RASCS_Disconnected)
      return;
    Sleep(100);
  }
}

inline void DialWorker(std::wstring entry, std::wstring host,
    std::wstring username, std::wstring password, std::wstring psk) {
  DWORD rc = ERROR_SUCCESS;
  std::wstring device;
  bool created = false;
  HRASCONN conn = nullptr;
  RASENTRYW settings = {};
  settings.dwSize = sizeof(settings);
  settings.dwfOptions = RASEO_RemoteDefaultGateway |
                         RASEO_RequireMsEncryptedPw |
                         RASEO_RequireMsCHAP2;
  settings.dwfOptions2 = RASEO2_UsePreSharedKey;
  settings.dwFramingProtocol = RASFP_Ppp;
  settings.dwType = RASET_Vpn;
  settings.dwVpnStrategy = VS_L2tpOnly;
  if (!Copy(settings.szLocalPhoneNumber, host)) {
    rc = ERROR_INVALID_PARAMETER;
  }
  if (rc == ERROR_SUCCESS) rc = FindL2tpDevice(&device);
  if (rc == ERROR_SUCCESS && !Copy(settings.szDeviceType,
      std::wstring(RASDT_Vpn))) rc = ERROR_INVALID_PARAMETER;
  if (rc == ERROR_SUCCESS && !Copy(settings.szDeviceName, device))
    rc = ERROR_INVALID_PARAMETER;
  if (rc == ERROR_SUCCESS) {
    rc = RasValidateEntryNameW(nullptr, entry.c_str());
    // ERROR_ALREADY_EXISTS signals a collision; never modify other entries.
  }
  if (rc == ERROR_SUCCESS) {
    rc = RasSetEntryPropertiesW(nullptr, entry.c_str(),
                               &settings, sizeof(settings), nullptr, 0);
    created = (rc == ERROR_SUCCESS);
  }
  RASCREDENTIALSW creds = {};
  creds.dwSize = sizeof(creds);
  creds.dwMask = RASCM_PreSharedKey;
  if (rc == ERROR_SUCCESS && !Copy(creds.szPassword, psk))
    rc = ERROR_INVALID_PARAMETER;
  if (rc == ERROR_SUCCESS)
    rc = RasSetCredentialsW(nullptr, entry.c_str(), &creds, FALSE);
  SecureZeroMemory(&creds, sizeof(creds));
  Wipe(psk);
  RASDIALPARAMSW params = {};
  params.dwSize = sizeof(params);
  if (rc == ERROR_SUCCESS && (!Copy(params.szEntryName, entry) ||
      !Copy(params.szUserName, username) ||
      !Copy(params.szPassword, password))) rc = ERROR_INVALID_PARAMETER;
  Wipe(username);
  Wipe(password);
  if (rc == ERROR_SUCCESS && !Cancelled()) {
    rc = RasDialW(nullptr, nullptr, &params, 0, nullptr, &conn);
    if (rc == ERROR_SUCCESS && conn) Tunnel().store(conn);
  }
  SecureZeroMemory(&params, sizeof(params));
  if (Cancelled() || rc != ERROR_SUCCESS || !conn) {
    if (conn) CloseTunnel(conn);
    if (created) RemoveOwnedEntry(entry);
    Tunnel().store(nullptr);
    LastErrorCode().store(rc == ERROR_SUCCESS ?
        ERROR_OPERATION_ABORTED : rc);
    State().store(-1);
    return;
  }
  State().store(2);
}

inline bool Start(const std::string& host, const std::string& username,
    const std::string& password, const std::string& psk) {
  int expected = 0;
  if (!State().compare_exchange_strong(expected, 1)) return false;
  if (!HostSafe(host) || !SecretSafe(username, 256) ||
      !SecretSafe(password, 256) || !SecretSafe(psk, 256)) {
    State().store(0);
    return false;
  }
  Cancelled().store(false);
  LastErrorCode().store(0);
  std::wstring entry = L"TwinConnect-L2TP-" +
      std::to_wstring(GetCurrentProcessId()) + L"-" +
      std::to_wstring(GetTickCount64());
  EntryName() = entry;
  auto wHost = Utf8(host);
  auto wUser = Utf8(username);
  auto wPass = Utf8(password);
  auto wPsk = Utf8(psk);
  if (wHost.empty() || wUser.empty() || wPass.empty() || wPsk.empty()) {
    Wipe(wPass); Wipe(wPsk); State().store(0); return false;
  }
  try {
    std::thread(DialWorker, entry, wHost, wUser, wPass, wPsk).detach();
  } catch (...) {
    Wipe(wPass); Wipe(wPsk); State().store(0); return false;
  }
  Wipe(wPass); Wipe(wPsk);
  return true;
}
inline int Status() {
  int state = State().load();
  if (state == 2) {
    RASCONNSTATUSW info = {};
    info.dwSize = sizeof(info);
    const HRASCONN connection = Tunnel().load();
    const DWORD rc = connection
        ? RasGetConnectStatusW(connection, &info)
        : ERROR_INVALID_HANDLE;
    if (rc != ERROR_SUCCESS || info.rasconnstate == RASCS_Disconnected) {
      LastErrorCode().store(rc != ERROR_SUCCESS
          ? rc : (info.dwError ? info.dwError : ERROR_PORT_NOT_CONNECTED));
      State().store(-1);
      return -1;
    }
  }
  return state;
}
inline DWORD Error() { return LastErrorCode().load(); }
inline bool Bytes(uint64_t* received, uint64_t* sent) {
  if (!received || !sent || Status() != 2) return false;
  RAS_STATS stats = {};
  stats.dwSize = sizeof(stats);
  if (RasGetConnectionStatistics(Tunnel().load(), &stats) != ERROR_SUCCESS)
    return false;
  *received = static_cast<uint64_t>(stats.dwBytesRcved);
  *sent = static_cast<uint64_t>(stats.dwBytesXmited);
  return true;
}
inline bool Stop() {
  int state = State().load();
  if (state == 0) return true;
  Cancelled().store(true);
  if (state == 1 || state == 3) return false;
  State().store(3);
  HRASCONN handle = Tunnel().exchange(nullptr);
  if (handle) CloseTunnel(handle);
  RemoveOwnedEntry(EntryName());
  EntryName().clear();
  State().store(0);
  return true;
}
inline void ResetError() {
  if (State().load() == -1) {
    RemoveOwnedEntry(EntryName());
    EntryName().clear();
    State().store(0);
  }
}
}  // namespace twinconnect_l2tp
