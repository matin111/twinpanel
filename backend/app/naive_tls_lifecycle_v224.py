from __future__ import annotations

import base64
import shlex
from typing import Any

from .models import Node
from .modern_protocol_runtime import CONFIG_DIR, CERT_PATH, KEY_PATH, SERVICE_NAME
from .routers.provision import cmd


MANAGED_CA_CERT_PATH = f"{CONFIG_DIR}/managed-ca.crt"
MANAGED_CA_KEY_PATH = f"{CONFIG_DIR}/managed-ca.key"
MANAGED_CERT_RENEW_SCRIPT = "/usr/local/sbin/twinpanel-modern-tls-renew"
MANAGED_CERT_RENEW_SERVICE = "twinpanel-modern-tls-renew.service"
MANAGED_CERT_RENEW_TIMER = "twinpanel-modern-tls-renew.timer"

MANAGED_NAIVE_TRUST_MODEL = "managed-ca-v1"
CUSTOM_NAIVE_TRUST_MODEL = "custom-cert-v1"

LEAF_VALIDITY_DAYS = 180
MAX_CHROMIUM_LEAF_DAYS = 200
LEAF_RENEW_BEFORE_DAYS = 30
CA_VALIDITY_DAYS = 3650


class NaiveTLSLifecycleError(RuntimeError):
    pass


def _safe_cert_identity(node: Node) -> tuple[str, list[str]]:
    from .modern_protocol_runtime import _safe_cert_name

    return _safe_cert_name(node)


def _renew_script(node: Node) -> str:
    common_name, sans = _safe_cert_identity(node)
    san_text = ",".join(sans) or f"DNS:{common_name}"

    san_checks: list[str] = []
    for value in sans:
        if value.startswith("IP:"):
            rendered = "IP Address:" + value.split(":", 1)[1]
        else:
            rendered = value
        san_checks.append(
            "  openssl x509 -in \"$CERT\" -noout -ext subjectAltName 2>/dev/null "
            f"| grep -Fq {shlex.quote(rendered)} || need_rotate=1"
        )

    san_guard = "\n".join(san_checks) or "  :"

    return f'''#!/bin/sh
set -eu
umask 077

CONFIG_DIR={shlex.quote(CONFIG_DIR)}
CA_CERT={shlex.quote(MANAGED_CA_CERT_PATH)}
CA_KEY={shlex.quote(MANAGED_CA_KEY_PATH)}
CERT={shlex.quote(CERT_PATH)}
KEY={shlex.quote(KEY_PATH)}
SERVICE={shlex.quote(SERVICE_NAME + ".service")}
COMMON_NAME={shlex.quote(common_name)}
SAN_TEXT={shlex.quote(san_text)}
LEAF_DAYS={LEAF_VALIDITY_DAYS}
MAX_LEAF_SECONDS={MAX_CHROMIUM_LEAF_DAYS * 86400}
RENEW_BEFORE_SECONDS={LEAF_RENEW_BEFORE_DAYS * 86400}

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

if {{ [ -s "$CA_CERT" ] && [ ! -s "$CA_KEY" ]; }} || {{ [ ! -s "$CA_CERT" ] && [ -s "$CA_KEY" ]; }}; then
  echo "managed CA material is incomplete" >&2
  exit 30
fi

if [ ! -s "$CA_CERT" ] && [ ! -s "$CA_KEY" ]; then
  ca_tmp="$(mktemp -d "$CONFIG_DIR/.ca-new.XXXXXX")"
  trap 'rm -rf "$ca_tmp"' EXIT HUP INT TERM

  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
    -sha256 -nodes -days {CA_VALIDITY_DAYS} \
    -subj "/CN=TwinPanel Modern Local CA" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -keyout "$ca_tmp/ca.key" -out "$ca_tmp/ca.crt" >/dev/null 2>&1

  chmod 600 "$ca_tmp/ca.key"
  chmod 644 "$ca_tmp/ca.crt"
  mv "$ca_tmp/ca.key" "$CA_KEY"
  mv "$ca_tmp/ca.crt" "$CA_CERT"

  rm -rf "$ca_tmp"
  trap - EXIT HUP INT TERM
fi

chmod 600 "$CA_KEY"
chmod 644 "$CA_CERT"

ca_cert_pub="$(
  openssl x509 -in "$CA_CERT" -pubkey -noout 2>/dev/null |
  openssl pkey -pubin -outform DER 2>/dev/null |
  openssl dgst -sha256 2>/dev/null || true
)"
ca_key_pub="$(
  openssl pkey -in "$CA_KEY" -pubout -outform DER 2>/dev/null |
  openssl dgst -sha256 2>/dev/null || true
)"
if [ -z "$ca_cert_pub" ] || [ "$ca_cert_pub" != "$ca_key_pub" ]; then
  echo "managed CA certificate/key mismatch" >&2
  exit 30
fi

need_rotate=0

if [ ! -s "$CERT" ] || [ ! -s "$KEY" ]; then
  need_rotate=1
else
  start_text="$(openssl x509 -in "$CERT" -noout -startdate 2>/dev/null | cut -d= -f2- || true)"
  end_text="$(openssl x509 -in "$CERT" -noout -enddate 2>/dev/null | cut -d= -f2- || true)"
  start_epoch="$(date -u -d "$start_text" +%s 2>/dev/null || true)"
  end_epoch="$(date -u -d "$end_text" +%s 2>/dev/null || true)"

  if [ -z "$start_epoch" ] || [ -z "$end_epoch" ]; then
    need_rotate=1
  elif [ "$((end_epoch - start_epoch))" -gt "$MAX_LEAF_SECONDS" ]; then
    need_rotate=1
  fi

  openssl x509 -checkend "$RENEW_BEFORE_SECONDS" -noout -in "$CERT" >/dev/null 2>&1 \
    || need_rotate=1

  openssl verify -CAfile "$CA_CERT" "$CERT" >/dev/null 2>&1 \
    || need_rotate=1

  cert_pub="$(
    openssl x509 -in "$CERT" -pubkey -noout 2>/dev/null |
    openssl pkey -pubin -outform DER 2>/dev/null |
    openssl dgst -sha256 2>/dev/null || true
  )"
  key_pub="$(
    openssl pkey -in "$KEY" -pubout -outform DER 2>/dev/null |
    openssl dgst -sha256 2>/dev/null || true
  )"

  [ -n "$cert_pub" ] && [ "$cert_pub" = "$key_pub" ] || need_rotate=1

  openssl x509 -in "$CERT" -noout -text 2>/dev/null |
    grep -A1 "Basic Constraints" |
    grep -q "CA:FALSE" || need_rotate=1

{san_guard}
fi

if [ "$need_rotate" -eq 0 ]; then
  echo "managed_tls_rotated=no"
  exit 0
fi

tmp="$(mktemp -d "$CONFIG_DIR/.leaf-new.XXXXXX")"
backup=""
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
  -sha256 -nodes \
  -subj "/CN=$COMMON_NAME" \
  -keyout "$tmp/server.key" -out "$tmp/server.csr" >/dev/null 2>&1

cat > "$tmp/server.ext" <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=serverAuth
subjectAltName=$SAN_TEXT
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
EOF

openssl x509 -req -in "$tmp/server.csr" \
  -CA "$CA_CERT" -CAkey "$CA_KEY" -CAcreateserial \
  -sha256 -days "$LEAF_DAYS" \
  -extfile "$tmp/server.ext" \
  -out "$tmp/server.crt" >/dev/null 2>&1

openssl verify -CAfile "$CA_CERT" "$tmp/server.crt" >/dev/null

new_start="$(
  openssl x509 -in "$tmp/server.crt" -noout -startdate |
  cut -d= -f2-
)"
new_end="$(
  openssl x509 -in "$tmp/server.crt" -noout -enddate |
  cut -d= -f2-
)"
new_start_epoch="$(date -u -d "$new_start" +%s)"
new_end_epoch="$(date -u -d "$new_end" +%s)"

if [ "$((new_end_epoch - new_start_epoch))" -gt "$MAX_LEAF_SECONDS" ]; then
  echo "generated certificate validity exceeds Chromium policy" >&2
  exit 31
fi

chmod 600 "$tmp/server.key"
chmod 644 "$tmp/server.crt"

if [ -s "$CERT" ] && [ -s "$KEY" ]; then
  backup="$CONFIG_DIR/tls-backup-$(date -u +%Y%m%d-%H%M%S)"
  mkdir -p "$backup"
  chmod 700 "$backup"
  cp -a "$CERT" "$backup/server.crt"
  cp -a "$KEY" "$backup/server.key"
fi

mv "$tmp/server.key" "$KEY"
mv "$tmp/server.crt" "$CERT"
chmod 600 "$KEY"
chmod 644 "$CERT"

if systemctl is-active --quiet "$SERVICE"; then
  if ! systemctl restart "$SERVICE"; then
    if [ -n "$backup" ] && [ -s "$backup/server.crt" ] && [ -s "$backup/server.key" ]; then
      cp -a "$backup/server.crt" "$CERT"
      cp -a "$backup/server.key" "$KEY"
      chmod 600 "$KEY"
      chmod 644 "$CERT"
      systemctl restart "$SERVICE" || true
    fi
    echo "managed TLS rotation restart failed" >&2
    exit 32
  fi
fi

rm -rf "$tmp"
trap - EXIT HUP INT TERM

echo "managed_tls_rotated=yes"
'''


def _renew_service_unit() -> str:
    return f'''[Unit]
Description=TwinPanel managed Modern TLS leaf renewal
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart={MANAGED_CERT_RENEW_SCRIPT}
'''


def _renew_timer_unit() -> str:
    return '''[Unit]
Description=Daily TwinPanel managed Modern TLS leaf renewal

[Timer]
OnCalendar=*-*-* 04:00:00
RandomizedDelaySec=1h
Persistent=true
Unit=twinpanel-modern-tls-renew.service

[Install]
WantedBy=timers.target
'''


async def ensure_managed_naive_tls(conn, node: Node) -> dict[str, Any]:
    '''Migrate and maintain the default Modern TLS certificate for Naive.

    The CA is stable trust material. The server certificate is a short-lived
    CA-signed leaf that complies with Chromium's current maximum lifetime and
    renews automatically without changing subscriber credentials or client
    configuration.
    '''

    script = _renew_script(node)
    script_b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
    service_b64 = base64.b64encode(_renew_service_unit().encode("utf-8")).decode("ascii")
    timer_b64 = base64.b64encode(_renew_timer_unit().encode("utf-8")).decode("ascii")

    output = await cmd(
        conn,
        "set -eu; "
        "command -v openssl >/dev/null 2>&1; "
        f"mkdir -p {shlex.quote(CONFIG_DIR)} /usr/local/sbin; "
        f"chmod 700 {shlex.quote(CONFIG_DIR)}; "
        f"printf '%s' {shlex.quote(script_b64)} | base64 -d > {shlex.quote(MANAGED_CERT_RENEW_SCRIPT)}.new; "
        f"chmod 700 {shlex.quote(MANAGED_CERT_RENEW_SCRIPT)}.new; "
        f"mv {shlex.quote(MANAGED_CERT_RENEW_SCRIPT)}.new {shlex.quote(MANAGED_CERT_RENEW_SCRIPT)}; "
        f"printf '%s' {shlex.quote(service_b64)} | base64 -d > /etc/systemd/system/{MANAGED_CERT_RENEW_SERVICE}.new; "
        f"mv /etc/systemd/system/{MANAGED_CERT_RENEW_SERVICE}.new /etc/systemd/system/{MANAGED_CERT_RENEW_SERVICE}; "
        f"printf '%s' {shlex.quote(timer_b64)} | base64 -d > /etc/systemd/system/{MANAGED_CERT_RENEW_TIMER}.new; "
        f"mv /etc/systemd/system/{MANAGED_CERT_RENEW_TIMER}.new /etc/systemd/system/{MANAGED_CERT_RENEW_TIMER}; "
        "systemctl daemon-reload; "
        f"systemctl enable --now {MANAGED_CERT_RENEW_TIMER} >/dev/null; "
        f"{shlex.quote(MANAGED_CERT_RENEW_SCRIPT)}",
        timeout=120,
    )

    rotated = "managed_tls_rotated=yes" in str(output or "")
    return {
        "ok": True,
        "rotated": rotated,
        "ca_certificate_path": MANAGED_CA_CERT_PATH,
        "leaf_certificate_path": CERT_PATH,
        "leaf_validity_days": LEAF_VALIDITY_DAYS,
        "renew_before_days": LEAF_RENEW_BEFORE_DAYS,
        "trust_model": MANAGED_NAIVE_TRUST_MODEL,
    }
