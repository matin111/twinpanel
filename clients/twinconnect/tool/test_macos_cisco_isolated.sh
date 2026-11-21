#!/usr/bin/env bash
# Never uses sudo, real VPN profiles, route, networksetup or OpenConnect.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m unittest discover -s macos_native -p 'test_cisco_isolated_network_lifecycle.py' -v
python3 -m unittest discover -s macos_native -p 'test_cisco*.py' -q
echo "CISCO_ISOLATED_TESTS_PASSED"
echo "NO_VPN_LAUNCHED; NO_NETWORK_CHANGES; CISCO_PRODUCTION_LOCK_PRESERVED"
