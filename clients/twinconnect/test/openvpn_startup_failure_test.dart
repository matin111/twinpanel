import 'package:flutter_test/flutter_test.dart';
import 'package:twinconnect/openvpn_startup_failure.dart';

void main() {
  test('categorizes actionable startup errors without leaking process output', () {
    final cases = <String, String>{
      'AUTH_FAILED user=somebody': 'OPENVPN_AUTH_REJECTED',
      'VERIFY ERROR: certificate verify failed for a private CN':
          'OPENVPN_CERTIFICATE_REJECTED',
      'Cannot open TUN/TAP dev /dev/tun': 'OPENVPN_ADAPTER_UNAVAILABLE',
      'All TAP-Windows adapters on this system are currently in use':
          'OPENVPN_ADAPTER_UNAVAILABLE',
      'Access is denied while creating device':
          'OPENVPN_PERMISSION_DENIED',
      'Options error: Unrecognized option or missing parameter(s)':
          'OPENVPN_OPTIONS_INVALID',
      'Cannot resolve host address: private.example:1194':
          'OPENVPN_ENDPOINT_DNS_FAILED',
      'ERROR: Windows route add command failed [adaptive]':
          'OPENVPN_ROUTE_FAILED',
    };
    for (final entry in cases.entries) {
      final code = OpenVpnStartupFailure.classify(entry.key);
      expect(code, entry.value, reason: entry.key);
      expect(code, isNot(contains('private')));
      expect(code, isNot(contains('somebody')));
    }
  });

  test('unknown messages never become user-facing engine logs', () {
    expect(OpenVpnStartupFailure.classify('remote 10.0.0.8 cipher AES'),
        isNull);
    expect(OpenVpnStartupFailure.classify('Initialization Sequence Completed'),
        isNull);
  });

  test('classifies well known Windows native OpenVPN exit codes', () {
    expect(OpenVpnStartupFailure.fromExitCode(-1073741515),
        'OPENVPN_DEPENDENCY_MISSING');
    expect(OpenVpnStartupFailure.fromExitCode(0xC000007B),
        'OPENVPN_INVALID_BINARY_ARCHITECTURE');
    expect(OpenVpnStartupFailure.fromExitCode(0xC0000005),
        'OPENVPN_NATIVE_CRASH');
    expect(OpenVpnStartupFailure.fromExitCode(0xC0000142),
        'OPENVPN_DLL_INITIALIZATION_FAILED');
    expect(OpenVpnStartupFailure.fromExitCode(0xC000013A),
        'OPENVPN_PROCESS_INTERRUPTED');
    expect(OpenVpnStartupFailure.fromExitCode(1), isNull);
  });

  test('fatal and retryable errors are distinguished', () {
    expect(OpenVpnStartupFailure.isTerminal('OPENVPN_AUTH_REJECTED'), isTrue);
    expect(OpenVpnStartupFailure.isTerminal('OPENVPN_ADAPTER_UNAVAILABLE'),
        isTrue);
    expect(OpenVpnStartupFailure.isTerminal('OPENVPN_ENDPOINT_DNS_FAILED'),
        isFalse);
    expect(OpenVpnStartupFailure.isTerminal('OPENVPN_ROUTE_FAILED'), isFalse);
  });
}
