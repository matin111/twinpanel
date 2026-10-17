#!/usr/bin/env bash
set -Eeuo pipefail

EXPECTED_HOST="CLY871416"
API_URL="${API_URL:-http://127.0.0.1:8095}"
WEB_URL="${WEB_URL:-http://127.0.0.1:3010}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
CUSTOMER_TOKEN="${CUSTOMER_TOKEN:-}"
TMP_DIR="$(mktemp -d /tmp/twinpanel-smoke.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

log() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

fail() {
  echo "SMOKE_FAIL: $*" >&2
  exit 1
}

request_code() {
  local method="$1"
  local url="$2"
  local outfile="$3"
  shift 3
  curl -sS -o "$outfile" -w '%{http_code}' -X "$method" "$url" "$@" || true
}

expect_200() {
  local label="$1"
  local method="$2"
  local url="$3"
  local outfile="$4"
  shift 4
  local code
  code="$(request_code "$method" "$url" "$outfile" "$@")"
  echo "$label -> HTTP $code"
  if [[ "$code" != "200" ]]; then
    cat "$outfile" 2>/dev/null || true
    echo
    fail "$label expected HTTP 200"
  fi
}

ACTUAL_HOST="$(hostname)"
if [[ "$ACTUAL_HOST" != "$EXPECTED_HOST" && "${ALLOW_HOST_MISMATCH:-0}" != "1" ]]; then
  fail "expected host $EXPECTED_HOST but current host is $ACTUAL_HOST"
fi

log "PUBLIC HEALTH"
expect_200 "API health" GET "$API_URL/health" "$TMP_DIR/health.json"
expect_200 "API readiness" GET "$API_URL/health/ready" "$TMP_DIR/ready.json"
expect_200 "Frontend login" GET "$WEB_URL/login" "$TMP_DIR/login.html"

log "FRONTEND API PROXY"
LOGIN_CODE="$(request_code POST "$WEB_URL/v1/auth/login" "$TMP_DIR/login-proxy.json" \
  -H 'Content-Type: application/json' \
  --data '{"email":"invalid-runtime-smoke@example.com","password":"invalid-runtime-smoke-password"}')"
echo "Invalid login through proxy -> HTTP $LOGIN_CODE"
case "$LOGIN_CODE" in
  000|5??)
    cat "$TMP_DIR/login-proxy.json" 2>/dev/null || true
    echo
    fail "frontend API proxy returned $LOGIN_CODE"
    ;;
esac

log "OPENAPI ROUTES"
expect_200 "OpenAPI" GET "$API_URL/openapi.json" "$TMP_DIR/openapi.json"
python3 - "$TMP_DIR/openapi.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    doc = json.load(fh)
paths = doc.get("paths", {})
required = {
    "/v1/payments/methods",
    "/v1/payments/intents",
    "/v1/payments/intents/{intent_id}/receipt-upload",
    "/v1/payments/admin/crypto-discount",
    "/v1/wallet/methods",
    "/v1/wallet/topups",
    "/v1/wallet/topups/{topup_id}/submit",
    "/v1/admin/wallet/wallets",
    "/v1/admin/wallet/topups",
    "/v1/admin/wallet/topups/{topup_id}/approve",
    "/v1/admin/telegram-bot",
    "/v1/admin/telegram-bot/test",
}
missing = sorted(required - set(paths))
if missing:
    print("Missing routes:")
    for item in missing:
        print(" -", item)
    raise SystemExit(1)
print("Required runtime routes: OK")
PY

log "PAYMENT METHODS - CARD / CRYPTO"
expect_200 "Payment methods" GET "$API_URL/v1/payments/methods" "$TMP_DIR/payment-methods.json"
python3 - "$TMP_DIR/payment-methods.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    data = json.load(fh)
methods = data.get("methods", []) if isinstance(data, dict) else []
print("Configured payment methods:")
if not methods:
    print(" - none enabled")
for row in methods:
    method = row.get("id") or "?"
    title = row.get("title") or method
    asset = row.get("asset") or ""
    auto = row.get("auto_verify")
    discount = row.get("crypto_discount_percent")
    print(f" - {method}: {title}; asset={asset or '-'}; auto_verify={auto}; crypto_discount={discount}")
PY

log "WALLET PAYMENT METHODS"
expect_200 "Wallet methods" GET "$API_URL/v1/wallet/methods" "$TMP_DIR/wallet-methods.json"
python3 - "$TMP_DIR/wallet-methods.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    data = json.load(fh)
methods = data.get("methods", []) if isinstance(data, dict) else []
print("Configured wallet top-up methods:")
if not methods:
    print(" - none enabled")
for row in methods:
    print(
        " -",
        row.get("id") or "?",
        "asset=", row.get("asset") or "-",
        "auto_verify=", row.get("auto_verify"),
    )
PY

if [[ -n "$ADMIN_TOKEN" ]]; then
  log "AUTHENTICATED ADMIN CHECKS"
  AUTH=(-H "Authorization: Bearer $ADMIN_TOKEN")
  expect_200 "Admin wallets" GET "$API_URL/v1/admin/wallet/wallets" "$TMP_DIR/admin-wallets.json" "${AUTH[@]}"
  expect_200 "Admin wallet topups" GET "$API_URL/v1/admin/wallet/topups" "$TMP_DIR/admin-topups.json" "${AUTH[@]}"
  expect_200 "Crypto discount settings" GET "$API_URL/v1/payments/admin/crypto-discount" "$TMP_DIR/crypto-discount.json" "${AUTH[@]}"
  expect_200 "Telegram manager status" GET "$API_URL/v1/admin/telegram-bot" "$TMP_DIR/telegram-status.json" "${AUTH[@]}"

  TELEGRAM_CONFIGURED="$(python3 - "$TMP_DIR/telegram-status.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as fh:
    data=json.load(fh)
print('1' if data.get('token_configured') else '0')
print(
    f"Telegram installed={data.get('installed')} runtime_ready={data.get('runtime_ready')} service_state={data.get('service_state')}",
    file=sys.stderr,
)
PY
)"

  if [[ "$TELEGRAM_CONFIGURED" == "1" ]]; then
    expect_200 "Telegram getMe test" POST "$API_URL/v1/admin/telegram-bot/test" "$TMP_DIR/telegram-test.json" "${AUTH[@]}"
  else
    echo "Telegram token is not configured; external getMe test skipped."
  fi
else
  log "ADMIN TOKEN NOT PROVIDED"
  echo "Set ADMIN_TOKEN to test admin wallet, crypto discount and Telegram getMe endpoints."
fi

if [[ -n "$CUSTOMER_TOKEN" ]]; then
  log "AUTHENTICATED CUSTOMER CHECKS"
  CUST=(-H "Authorization: Bearer $CUSTOMER_TOKEN")
  expect_200 "Customer wallet" GET "$API_URL/v1/wallet/me" "$TMP_DIR/customer-wallet.json" "${CUST[@]}"
  expect_200 "Customer wallet transactions" GET "$API_URL/v1/wallet/transactions" "$TMP_DIR/customer-wallet-transactions.json" "${CUST[@]}"
  expect_200 "Customer wallet topups" GET "$API_URL/v1/wallet/topups/me" "$TMP_DIR/customer-wallet-topups.json" "${CUST[@]}"
  expect_200 "Customer payments" GET "$API_URL/v1/payments/intents/me" "$TMP_DIR/customer-payments.json" "${CUST[@]}"
else
  log "CUSTOMER TOKEN NOT PROVIDED"
  echo "Set CUSTOMER_TOKEN to test the authenticated customer wallet/payment history endpoints."
fi

log "SERVICE STATES"
systemctl is-active twinpanel-api.service
systemctl is-active twinpanel-preview.service
if systemctl cat twinpanel-bot.service >/dev/null 2>&1; then
  systemctl is-active twinpanel-bot.service || true
fi

echo
echo "============================================================"
echo " TWINPANEL RUNTIME SMOKE SUCCESS"
echo " HOST: $ACTUAL_HOST"
echo " API:  $API_URL"
echo " WEB:  $WEB_URL"
echo "============================================================"
