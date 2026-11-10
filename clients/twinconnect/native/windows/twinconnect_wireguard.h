#pragma once

// TwinConnect Windows WireGuard tunnel bridge.
//
// Uses the user's locally installed official WireGuard for Windows;
// NEVER downloads drivers, executes arbitrary programs or runs shell commands.
// The config is DPAPI-encrypted for LocalMachine and stored under a
// SYSTEM/Administrators-only ProgramData directory. No plaintext config is
// written to disk. Only a process already running as Administrator may start
// or stop the dedicated TwinConnect tunnel.
//
// "interface_up" means Windows reports the official WireGuard tunnel service
// running. It does NOT prove any peer handshake, traffic or public IP.

#include <windows.h>
#include <wincrypt.h>
#include <sddl.h>
#include <shlobj.h>
#include <winsvc.h>
#include <flutter/encodable_value.h>
#include <algorithm>
#include <cctype>
#include <string>
#include <vector>
#include <array>
#include <ctime>
#include <cstdint>
#include <sstream>

#pragma comment(lib, "Crypt32.lib")
#pragma comment(lib, "Advapi32.lib")
#pragma comment(lib, "Shell32.lib")
#pragma comment(lib, "Ole32.lib")

namespace twinconnect_wireguard {

static constexpr wchar_t kTunnelName[] = L"TwinConnect";
static constexpr wchar_t kServiceName[] = L"WireGuardTunnel$TwinConnect";

inline bool IsAdmin() {
  HANDLE token = nullptr;
  if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token))
    return false;
  TOKEN_ELEVATION elevation = {};
  DWORD len = 0;
  const bool ok = GetTokenInformation(token, TokenElevation, &elevation,
                                      sizeof(elevation), &len) != FALSE;
  CloseHandle(token);
  return ok && elevation.TokenIsElevated != 0;
}

inline std::wstring TrustedFolder(REFKNOWNFOLDERID folder) {
  PWSTR path = nullptr;
  const HRESULT result = SHGetKnownFolderPath(folder, 0, nullptr, &path);
  if (FAILED(result) || !path) return L"";
  const std::wstring value(path);
  CoTaskMemFree(path);
  return value;
}

inline bool IsFile(const std::wstring& path) {
  const DWORD flags = GetFileAttributesW(path.c_str());
  return flags != INVALID_FILE_ATTRIBUTES &&
         !(flags & FILE_ATTRIBUTE_DIRECTORY);
}

inline std::wstring WireGuardExe() {
  const auto files = TrustedFolder(FOLDERID_ProgramFiles);
  if (files.empty()) return L"";
  const auto path = files + L"\\WireGuard\\wireguard.exe";
  return IsFile(path) ? path : L"";
}

inline bool ServiceRunning() {
  SC_HANDLE scm = OpenSCManagerW(nullptr, nullptr, SC_MANAGER_CONNECT);
  if (!scm) return false;
  SC_HANDLE svc = OpenServiceW(scm, kServiceName, SERVICE_QUERY_STATUS);
  if (!svc) { CloseServiceHandle(scm); return false; }
  SERVICE_STATUS_PROCESS status = {};
  DWORD needed = 0;
  const bool success = QueryServiceStatusEx(
      svc, SC_STATUS_PROCESS_INFO, reinterpret_cast<LPBYTE>(&status),
      sizeof(status), &needed) != FALSE;
  CloseServiceHandle(svc);
  CloseServiceHandle(scm);
  return success && status.dwCurrentState == SERVICE_RUNNING;
}

inline bool ServiceExists() {
  SC_HANDLE scm = OpenSCManagerW(nullptr, nullptr, SC_MANAGER_CONNECT);
  if (!scm) return false;
  SC_HANDLE svc = OpenServiceW(scm, kServiceName, SERVICE_QUERY_STATUS);
  const bool found = svc != nullptr;
  if (svc) CloseServiceHandle(svc);
  CloseServiceHandle(scm);
  return found;
}

// Read only handshake and transfer statistics from the locally installed
// signed WireGuard tools. Never invoke a shell or request private-key output.
inline bool WgQuery(const wchar_t* fixedArgs, std::string* output) {
  const auto programFiles = TrustedFolder(FOLDERID_ProgramFiles);
  if (programFiles.empty()) return false;
  const auto exe = programFiles + L"\\WireGuard\\wg.exe";
  if (!IsFile(exe)) return false;

  SECURITY_ATTRIBUTES pipeAttrs = {sizeof(SECURITY_ATTRIBUTES), nullptr, TRUE};
  HANDLE readPipe = nullptr, writePipe = nullptr;
  if (!CreatePipe(&readPipe, &writePipe, &pipeAttrs, 0)) return false;
  SetHandleInformation(readPipe, HANDLE_FLAG_INHERIT, 0);
  // A Flutter GUI process may have no STDIN. Use an explicit inherited NUL
  // handle instead of a missing console handle for subprocess creation.
  HANDLE nullInput = CreateFileW(L"NUL", GENERIC_READ,
      FILE_SHARE_READ | FILE_SHARE_WRITE, &pipeAttrs,
      OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (nullInput == INVALID_HANDLE_VALUE) {
    CloseHandle(writePipe);
    CloseHandle(readPipe);
    return false;
  }

  std::wstring command = L"\"" + exe + L"\" show TwinConnect " + fixedArgs;
  STARTUPINFOW startup = {};
  startup.cb = sizeof(startup);
  startup.dwFlags = STARTF_USESTDHANDLES;
  startup.hStdOutput = writePipe;
  startup.hStdError = writePipe;
  startup.hStdInput = nullInput;
  PROCESS_INFORMATION process = {};
  const BOOL started = CreateProcessW(
      exe.c_str(), command.data(), nullptr, nullptr, TRUE,
      CREATE_NO_WINDOW, nullptr, nullptr, &startup, &process);
  CloseHandle(writePipe);
  CloseHandle(nullInput);
  if (!started) { CloseHandle(readPipe); return false; }

  const DWORD result = WaitForSingleObject(process.hProcess, 6000);
  DWORD code = 1;
  if (result == WAIT_TIMEOUT) {
    TerminateProcess(process.hProcess, 1);
    WaitForSingleObject(process.hProcess, 3000);
  } else if (result == WAIT_OBJECT_0) {
    GetExitCodeProcess(process.hProcess, &code);
  }
  CloseHandle(process.hThread);
  CloseHandle(process.hProcess);

  std::string buffer;
  std::array<char, 1024> chunk = {};
  DWORD received = 0;
  while (buffer.size() < 8192 &&
         ReadFile(readPipe, chunk.data(), static_cast<DWORD>(chunk.size()),
                  &received, nullptr) && received > 0)
    buffer.append(chunk.data(), received);
  CloseHandle(readPipe);
  if (result != WAIT_OBJECT_0 || code != 0) return false;
  *output = buffer;
  return true;
}

inline int64_t LatestHandshakeEpoch() {
  std::string out;
  if (!WgQuery(L"latest-handshakes", &out)) return 0;
  std::istringstream stream(out);
  std::string publicKey;
  int64_t timestamp = 0;
  stream >> publicKey >> timestamp;
  return timestamp > 0 ? timestamp : 0;
}

inline void TransferTotals(int64_t* received, int64_t* sent) {
  *received = 0;
  *sent = 0;
  std::string out;
  if (!WgQuery(L"transfer", &out)) return;
  std::istringstream stream(out);
  std::string publicKey;
  int64_t rx = -1, tx = -1;
  stream >> publicKey >> rx >> tx;
  if (rx >= 0 && tx >= 0) {
    *received = rx;
    *sent = tx;
  }
}

inline std::wstring PrivateFolder() {
  const auto root = TrustedFolder(FOLDERID_ProgramData);
  return root.empty() ? L"" : root + L"\\TwinConnect";
}

inline std::wstring EncryptedPath() {
  const auto dir = PrivateFolder();
  return dir.empty() ? L"" : dir + L"\\TwinConnect.conf.dpapi";
}

inline bool EnsurePrivateFolder() {
  const auto dir = PrivateFolder();
  if (dir.empty()) return false;
  // Protected directory, never expose private keys to ordinary users.
  PSECURITY_DESCRIPTOR descriptor = nullptr;
  if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(
          L"D:P(A;;GA;;;SY)(A;;GA;;;BA)", SDDL_REVISION_1,
          &descriptor, nullptr)) return false;
  SECURITY_ATTRIBUTES attrs = {sizeof(SECURITY_ATTRIBUTES), descriptor, FALSE};
  const BOOL created = CreateDirectoryW(dir.c_str(), &attrs);
  bool ok = created != FALSE || GetLastError() == ERROR_ALREADY_EXISTS;
  // Enforce the ACL also if a directory already existed.
  if (ok) ok = SetFileSecurityW(dir.c_str(), DACL_SECURITY_INFORMATION,
                                descriptor) != FALSE;
  LocalFree(descriptor);
  return ok;
}

inline bool WriteEncryptedConfig(const std::string& raw) {
  if (!IsAdmin() || !EnsurePrivateFolder() || raw.empty()) return false;
  const auto path = EncryptedPath();
  if (path.empty() || IsFile(path)) return false;
  DATA_BLOB input = {
      static_cast<DWORD>(raw.size()),
      reinterpret_cast<BYTE*>(const_cast<char*>(raw.data()))
  };
  DATA_BLOB encrypted = {};
  if (!CryptProtectData(&input, L"TwinConnect", nullptr, nullptr, nullptr,
                        CRYPTPROTECT_LOCAL_MACHINE | CRYPTPROTECT_UI_FORBIDDEN,
                        &encrypted)) return false;
  PSECURITY_DESCRIPTOR descriptor = nullptr;
  if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(
          L"D:P(A;;GA;;;SY)(A;;GA;;;BA)", SDDL_REVISION_1,
          &descriptor, nullptr)) {
    LocalFree(encrypted.pbData);
    return false;
  }
  SECURITY_ATTRIBUTES attrs = {sizeof(SECURITY_ATTRIBUTES), descriptor, FALSE};
  HANDLE file = CreateFileW(path.c_str(), GENERIC_WRITE, 0, &attrs,
                            CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
  LocalFree(descriptor);
  bool ok = false;
  if (file != INVALID_HANDLE_VALUE) {
    DWORD written = 0;
    ok = WriteFile(file, encrypted.pbData, encrypted.cbData, &written, nullptr) &&
         written == encrypted.cbData && FlushFileBuffers(file);
    CloseHandle(file);
    if (!ok) DeleteFileW(path.c_str());
  }
  SecureZeroMemory(encrypted.pbData, encrypted.cbData);
  LocalFree(encrypted.pbData);
  return ok;
}

inline bool InvokeOfficialWireGuard(const wchar_t* command,
                                    const std::wstring& argument) {
  const auto exe = WireGuardExe();
  if (exe.empty() || !IsAdmin()) return false;
  std::wstring args = L"\"" + exe + L"\" " + command + L" \"" + argument + L"\"";
  STARTUPINFOW startup = {};
  startup.cb = sizeof(startup);
  PROCESS_INFORMATION process = {};
  // Do not use cmd.exe, PowerShell or the system PATH.
  if (!CreateProcessW(exe.c_str(), args.data(), nullptr, nullptr, FALSE,
                      CREATE_NO_WINDOW, nullptr, nullptr, &startup, &process))
    return false;
  const DWORD wait = WaitForSingleObject(process.hProcess, 30000);
  DWORD exit_code = 1;
  if (wait == WAIT_OBJECT_0)
    GetExitCodeProcess(process.hProcess, &exit_code);
  CloseHandle(process.hThread);
  CloseHandle(process.hProcess);
  return wait == WAIT_OBJECT_0 && exit_code == 0;
}

inline std::string TrimLower(const std::string& s) {
  const auto a = s.find_first_not_of(" \t\r");
  if (a == std::string::npos) return "";
  const auto b = s.find_last_not_of(" \t\r");
  std::string out = s.substr(a, b - a + 1);
  std::transform(out.begin(), out.end(), out.begin(),
    [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
  return out;
}

inline bool ValidConfig(const std::string& text) {
  if (text.size() < 80 || text.size() > 65536 ||
      text.find('\0') != std::string::npos) return false;
  bool iface = false, peer = false;
  bool private_key = false, address = false, dns = false;
  bool public_key = false, endpoint = false, full_v4 = false, full_v6 = false;
  int peer_count = 0;
  size_t pos = 0;
  while (pos <= text.size()) {
    const auto end = text.find('\n', pos);
    const auto line = text.substr(pos, end == std::string::npos
        ? std::string::npos : end - pos);
    pos = end == std::string::npos ? text.size() + 1 : end + 1;
    const auto normalized = TrimLower(line);
    if (normalized.empty() || normalized[0] == '#' || normalized[0] == ';')
      continue;
    if (normalized == "[interface]") { iface = true; peer = false; continue; }
    if (normalized == "[peer]") {
      peer = true; iface = false; ++peer_count; continue;
    }
    // No arbitrary shell hooks, unmanaged table, script values or extra
    // sections. These are fixed-role tunnel profiles from an entitled panel.
    const auto equal = normalized.find('=');
    if (equal == std::string::npos || (!iface && !peer)) return false;
    const auto key = TrimLower(normalized.substr(0, equal));
    const auto value = TrimLower(normalized.substr(equal + 1));
    if (value.empty()) return false;
    if (iface) {
      if (key == "privatekey") private_key = true;
      else if (key == "address") address = true;
      else if (key == "dns") dns = true;
      else if (key == "mtu" || key == "listenport") {}
      else return false;
    } else {
      if (key == "publickey") public_key = true;
      else if (key == "endpoint") endpoint = true;
      else if (key == "allowedips") {
        size_t start = 0;
        while (start <= value.size()) {
          const auto comma = value.find(',', start);
          const auto item = TrimLower(value.substr(start,
              comma == std::string::npos ? std::string::npos : comma - start));
          if (item == "0.0.0.0/0") full_v4 = true;
          if (item == "::/0") full_v6 = true;
          if (comma == std::string::npos) break;
          start = comma + 1;
        }
      } else if (key == "presharedkey" || key == "persistentkeepalive") {}
      else return false;
    }
  }
  // A single peer + both /0 routes activates official Windows WireGuard's
  // restrictive firewall rules, including DNS to the configured resolver.
  return private_key && address && dns && public_key && endpoint &&
         peer_count == 1 && full_v4 && full_v6;
}

inline flutter::EncodableValue Info(const char* state) {
  const bool isUp = std::string(state) == "interface_up";
  const int64_t handshake = isUp ? LatestHandshakeEpoch() : 0;
  const int64_t now = static_cast<int64_t>(std::time(nullptr));
  const bool verified = handshake > 0 && now >= handshake &&
      (now - handshake) < 180;
  int64_t rx = 0, tx = 0;
  if (isUp) TransferTotals(&rx, &tx);
  flutter::EncodableMap map = {
      {flutter::EncodableValue("contractVersion"), flutter::EncodableValue(1)},
      {flutter::EncodableValue("protocol"), flutter::EncodableValue("wireguard")},
      {flutter::EncodableValue("state"),
       flutter::EncodableValue(verified ? "peer_verified" : state)},
      {flutter::EncodableValue("peerHandshakeVerified"),
       flutter::EncodableValue(verified)},
      {flutter::EncodableValue("lastHandshakeEpoch"),
       flutter::EncodableValue(handshake)},
      {flutter::EncodableValue("rxBytes"),
       flutter::EncodableValue(rx)},
      {flutter::EncodableValue("txBytes"),
       flutter::EncodableValue(tx)},
  };
  return flutter::EncodableValue(map);
}

inline flutter::EncodableValue Capabilities() {
  const bool ready = IsAdmin() && !WireGuardExe().empty();
  flutter::EncodableMap map = {
      {flutter::EncodableValue("contractVersion"), flutter::EncodableValue(1)},
      {flutter::EncodableValue("engineReady"), flutter::EncodableValue(ready)},
      {flutter::EncodableValue("fullTunnel"), flutter::EncodableValue(ready)},
      {flutter::EncodableValue("dnsGuard"), flutter::EncodableValue(ready)},
      {flutter::EncodableValue("ipv6Guard"), flutter::EncodableValue(ready)},
      {flutter::EncodableValue("killSwitchEnforced"), flutter::EncodableValue(false)},
      {flutter::EncodableValue("includeApps"), flutter::EncodableValue(false)},
      {flutter::EncodableValue("excludeApps"), flutter::EncodableValue(false)},
      {flutter::EncodableValue("localNetworkBypass"), flutter::EncodableValue(false)},
      {flutter::EncodableValue("autoConnect"), flutter::EncodableValue(false)},
      {flutter::EncodableValue("autoReconnect"), flutter::EncodableValue(false)}
  };
  return flutter::EncodableValue(map);
}

inline flutter::EncodableValue ProtocolCapabilities() {
  flutter::EncodableList supported;
  if (IsAdmin() && !WireGuardExe().empty())
    supported.push_back(flutter::EncodableValue("wireguard"));
  flutter::EncodableMap map = {
      {flutter::EncodableValue("contractVersion"), flutter::EncodableValue(1)},
      {flutter::EncodableValue("supportedProtocols"), flutter::EncodableValue(supported)}
  };
  return flutter::EncodableValue(map);
}

inline flutter::EncodableValue Status() {
  const bool exists = ServiceExists();
  const bool ownedConfig = IsFile(EncryptedPath());
  if (exists && !ownedConfig) return Info("unmanaged_service");
  return Info(ServiceRunning() ? "interface_up" :
      exists ? "needs_cleanup" : "down");
}

inline bool Start(const std::string& config) {
  if (!IsAdmin() || WireGuardExe().empty() || ServiceExists() ||
      !ValidConfig(config)) return false;
  // Reclaim only this application's own orphaned encrypted configuration
  // after an interrupted prior run, never an active service's profile.
  const auto stale = EncryptedPath();
  if (!stale.empty() && IsFile(stale) && !DeleteFileW(stale.c_str()))
    return false;
  if (!WriteEncryptedConfig(config)) return false;
  if (!InvokeOfficialWireGuard(L"/installtunnelservice", EncryptedPath())) {
    // If an install timed out but actually started, do not delete the
    // configuration that the running service still needs.
    if (!ServiceExists()) DeleteFileW(EncryptedPath().c_str());
    return false;
  }
  for (int i = 0; i < 20; i++) {
    if (ServiceRunning()) return true;
    Sleep(250);
  }
  // Do not claim VPN connectivity before Windows confirms service started.
  return false;
}

inline bool Stop() {
  if (!IsAdmin() || WireGuardExe().empty()) return false;
  // Never remove a same-named tunnel created by another client/tool.
  if (ServiceExists() && !IsFile(EncryptedPath())) return false;
  if (ServiceExists()) {
    if (!InvokeOfficialWireGuard(L"/uninstalltunnelservice", kTunnelName))
      return false;
    for (int i = 0; i < 20; i++) {
      if (!ServiceExists()) break;
      Sleep(250);
    }
    if (ServiceExists()) return false;
  }
  const auto path = EncryptedPath();
  if (!path.empty() && IsFile(path) && !DeleteFileW(path.c_str())) return false;
  return !ServiceRunning();
}

}  // namespace twinconnect_wireguard
