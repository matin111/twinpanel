from __future__ import annotations

import copy
import html
import json
import re
from typing import Any
from urllib.parse import quote, urlencode

from sqlalchemy.orm import Session

from .account_delivery import _public_payload, _subscription_from_share_token
from .public_connection_modern_delivery_v13 import (
    MODERN_PROTOCOLS,
    _items,
    _mieru_karing_yaml,
    _status_value,
    _sudoku_uri,
)
from .public_connection_modern_names_v14 import _profile_name


# Karing 1.2.25 supports the first cohort below. Newer 1.2.26 builds also add
# sing-box JSON import for Snell, Sudoku and TrustTunnel, but TwinPanel must not
# advertise those as one-click imports to older installed clients.
KARING_DIRECT_PROTOCOLS = {
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "mieru",
}

KARING_126_PROTOCOLS = {
    "snell",
    "sudoku",
    "trusttunnel",
}

STANDARD_SHARE_PROTOCOLS = {
    "hysteria2",
    "tuic",
    "anytls",
}


def _h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _host_for_uri(value: Any) -> str:
    host = str(value or "").strip()
    if not host:
        return ""
    if ":" in host and not (host.startswith("[") and host.endswith("]")):
        return f"[{host}]"
    return host


def _outbound(item: dict[str, Any]) -> dict[str, Any] | None:
    outbound = item.get("outbound")
    if isinstance(outbound, dict):
        return dict(outbound)

    raw = str(item.get("config") or "").strip()
    if not raw:
        return None

    try:
        config = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

    rows = config.get("outbounds") if isinstance(config, dict) else None
    if not isinstance(rows, list):
        return None

    for row in rows:
        if not isinstance(row, dict):
            continue
        outbound_type = str(row.get("type") or "").strip().lower()
        if outbound_type and outbound_type not in {"direct", "block", "dns"}:
            return dict(row)

    return None


def _tls_params(outbound: dict[str, Any]) -> list[tuple[str, str]]:
    tls = outbound.get("tls")
    if not isinstance(tls, dict):
        return []

    params: list[tuple[str, str]] = []
    server_name = str(tls.get("server_name") or "").strip()
    if server_name:
        params.append(("sni", server_name))
    if bool(tls.get("insecure")):
        params.append(("insecure", "1"))
    return params


def standard_share_uri(protocol: str, item: dict[str, Any], profile_name: str) -> str:
    protocol = str(protocol or "").strip().lower()
    if protocol not in STANDARD_SHARE_PROTOCOLS:
        return ""

    outbound = _outbound(item)
    if not isinstance(outbound, dict):
        return ""
    if str(outbound.get("type") or "").strip().lower() != protocol:
        return ""

    host = _host_for_uri(outbound.get("server"))
    try:
        port = int(outbound.get("server_port") or 0)
    except (TypeError, ValueError):
        port = 0
    if not host or not 1 <= port <= 65535:
        return ""

    label = quote(str(profile_name or "TwinPanel"), safe="")

    if protocol == "hysteria2":
        password = str(outbound.get("password") or "")
        if not password:
            return ""
        params = _tls_params(outbound)
        obfs = outbound.get("obfs")
        if isinstance(obfs, dict):
            obfs_type = str(obfs.get("type") or "").strip()
            obfs_password = str(obfs.get("password") or "").strip()
            if obfs_type:
                params.append(("obfs", obfs_type))
            if obfs_password:
                params.append(("obfs-password", obfs_password))
        query = urlencode(params)
        suffix = ("?" + query) if query else ""
        return (
            "hysteria2://"
            + quote(password, safe="")
            + "@"
            + host
            + f":{port}/"
            + suffix
            + "#"
            + label
        )

    if protocol == "tuic":
        uuid = str(outbound.get("uuid") or "").strip()
        password = str(outbound.get("password") or "")
        if not uuid or not password:
            return ""
        params = []
        congestion = str(outbound.get("congestion_control") or "").strip()
        if congestion:
            params.append(("congestion_control", congestion))
        udp_relay = str(outbound.get("udp_relay_mode") or "native").strip()
        if udp_relay:
            params.append(("udp_relay_mode", udp_relay))
        tls = outbound.get("tls")
        if isinstance(tls, dict):
            server_name = str(tls.get("server_name") or "").strip()
            if server_name:
                params.append(("sni", server_name))
            if bool(tls.get("insecure")):
                params.append(("allow_insecure", "1"))
        if bool(outbound.get("zero_rtt_handshake")):
            params.append(("reduce_rtt", "1"))
        query = urlencode(params)
        suffix = ("?" + query) if query else ""
        return (
            "tuic://"
            + quote(uuid, safe="")
            + ":"
            + quote(password, safe="")
            + "@"
            + host
            + f":{port}/"
            + suffix
            + "#"
            + label
        )

    if protocol == "anytls":
        password = str(outbound.get("password") or "")
        if not password:
            return ""
        params: list[tuple[str, str]] = [("security", "tls")]
        params.extend(_tls_params(outbound))
        query = urlencode(params)
        return (
            "anytls://"
            + quote(password, safe="")
            + "@"
            + host
            + f":{port}/?"
            + query
            + "#"
            + label
        )

    return ""


def _copy_content(protocol: str, item: dict[str, Any], profile_name: str) -> str:
    protocol = str(protocol or "").strip().lower()

    standard = standard_share_uri(protocol, item, profile_name)
    if standard:
        return standard

    if protocol == "mieru":
        content = _mieru_karing_yaml(item)
        if content:
            old = json.dumps("TwinPanel Mieru", ensure_ascii=False)
            new = json.dumps(profile_name, ensure_ascii=False)
            return content.replace(old, new)

    uri = str(item.get("uri") or "").strip()
    if protocol == "sudoku" and not uri:
        uri = _sudoku_uri(item)
    if uri:
        return uri

    config = str(item.get("config") or "").strip()
    if config:
        return config

    outbound = _outbound(item)
    if isinstance(outbound, dict):
        node = copy.deepcopy(outbound)
        node["tag"] = str(profile_name or "TwinPanel").strip() or "TwinPanel"
        return json.dumps(
            {"outbounds": [node]},
            ensure_ascii=False,
            separators=(",", ":"),
        )

    return ""


def karing_inline_uri(protocol: str, item: dict[str, Any], profile_name: str) -> str:
    """Return Karing's registered system scheme with config content inline.

    Karing's scheme handler names the argument ``url`` for historical reasons,
    but passes it to the Add Profile screen as ``urlOrContent``. It can therefore
    carry a proxy/share URI or raw configuration content directly and avoids a
    second HTTP fetch back to TwinPanel.
    """
    protocol = str(protocol or "").strip().lower()
    if protocol not in KARING_DIRECT_PROTOCOLS:
        return ""

    content = _copy_content(protocol, item, profile_name)
    if not content:
        return ""

    return (
        "karing://install-config?url="
        + quote(content, safe="")
        + "&name="
        + quote(str(profile_name or "TwinPanel"), safe="")
    )


def _replace_remote_karing_button(
    source: str,
    *,
    config_path: str,
    karing_uri: str,
    copy_target: str,
    standard_uri: str,
) -> str:
    escaped_path = _h(config_path)
    pattern = re.compile(
        r'<button class="primary-btn v13-karing-import" type="button" '
        r'data-config-path="'
        + re.escape(escaped_path)
        + r'"[^>]*>افزودن مستقیم به Karing</button>'
    )

    if not pattern.search(source):
        return source

    controls = (
        '<a class="primary-btn v15-karing-inline tp-v15-app-launch" '
        f'href="{_h(karing_uri)}" data-tp-copy-target="{_h(copy_target)}">'
        'افزودن مستقیم به Karing</a>'
    )
    if standard_uri:
        controls += (
            '<button class="v13-secondary copy-btn v15-standard-link" '
            f'type="button" data-copy="{_h(standard_uri)}">'
            'کپی لینک استاندارد</button>'
        )

    return pattern.sub(controls, source, count=1)


def _insert_modern_copy_button(
    source: str,
    *,
    protocol: str,
    copy_target: str,
    requires_karing_126: bool,
) -> str:
    marker = (
        f'<div class="v13-modern-action" data-v13-protocol="{_h(protocol)}">'
    )
    replacement = (
        f'<div class="v13-modern-action" data-v13-protocol="{_h(protocol)}" '
        'data-v15-delivery="1">'
    )
    anchor = source.find(marker)
    if anchor < 0:
        return source

    source = source[:anchor] + replacement + source[anchor + len(marker):]
    actions = source.find('<div class="v13-action-buttons">', anchor)
    if actions < 0:
        return source

    insert_at = actions + len('<div class="v13-action-buttons">')
    copy_button = (
        '<button class="v13-secondary copy-btn tp-v15-copy-config" '
        f'type="button" data-tp-copy-target="{_h(copy_target)}">'
        'کپی کانفیگ</button>'
    )
    if requires_karing_126:
        copy_button += (
            '<span class="tp-v15-client-note">'
            'Import مستقیم این پروتکل در Karing به نسخه 1.2.26+ نیاز دارد.'
            '</span>'
        )

    return source[:insert_at] + copy_button + source[insert_at:]


_V15_SCRIPT = r"""
<script id="twinpanelPublicModernImportV15">
(function(){
  const toast=document.getElementById('toast');

  function notify(text){
    if(!toast)return;
    toast.textContent=text;
    toast.classList.add('show');
    clearTimeout(window.__tpV15Toast);
    window.__tpV15Toast=setTimeout(()=>toast.classList.remove('show'),1800);
  }

  function fallbackCopy(value){
    const area=document.createElement('textarea');
    area.value=String(value||'');
    area.setAttribute('readonly','');
    area.style.position='fixed';
    area.style.left='-9999px';
    area.style.top='0';
    document.body.appendChild(area);
    area.focus();
    area.select();
    area.setSelectionRange(0,area.value.length);
    let ok=false;
    try{ok=document.execCommand('copy')}catch(_error){}
    area.remove();
    return ok;
  }

  async function copy(value){
    const text=String(value||'');
    if(!text)return false;
    if(navigator.clipboard&&window.isSecureContext){
      try{await navigator.clipboard.writeText(text);return true}catch(_error){}
    }
    return fallbackCopy(text);
  }

  function valueFromTarget(id){
    const el=document.getElementById(String(id||''));
    if(!el)return'';
    return String('value' in el?el.value:el.textContent||'');
  }

  document.addEventListener('click',async function(event){
    const targetButton=event.target.closest('[data-tp-copy-target]');
    if(targetButton&&!targetButton.classList.contains('tp-v15-app-launch')){
      event.preventDefault();
      const value=valueFromTarget(targetButton.dataset.tpCopyTarget);
      notify(await copy(value)?'کانفیگ کپی شد ✓':'کپی انجام نشد');
      return;
    }

    const launch=event.target.closest('a.tp-v15-app-launch');
    if(launch){
      event.preventDefault();
      const value=valueFromTarget(launch.dataset.tpCopyTarget);
      const ok=await copy(value);
      notify(ok?'کانفیگ کپی شد؛ در حال باز کردن برنامه…':'در حال باز کردن برنامه…');
      window.location.href=launch.getAttribute('href')||'';
      return;
    }

    const openUri=event.target.closest('a.v13-open-uri[href]');
    if(openUri){
      const value=openUri.getAttribute('href')||'';
      await copy(value);
      notify('لینک کپی شد؛ در حال باز کردن برنامه…');
    }
  },true);

  document.querySelectorAll('.download-config[data-target]').forEach(function(download){
    const row=download.closest('.action-row')||download.parentElement;
    if(!row||row.querySelector('.tp-v15-classic-copy'))return;
    const button=document.createElement('button');
    button.type='button';
    button.className='copy-btn tp-v15-classic-copy';
    button.dataset.tpCopyTarget=download.dataset.target||'';
    button.textContent='کپی کانفیگ';
    download.insertAdjacentElement('beforebegin',button);
  });

  document.querySelectorAll('.action-row .copy-btn[data-copy]').forEach(function(copyButton){
    const content=String(copyButton.dataset.copy||'').trim();
    if(!/^(vmess|vless|trojan|ss|hysteria2|hy2|tuic):/i.test(content))return;
    const actions=copyButton.closest('.action-buttons');
    if(!actions||actions.querySelector('.tp-v15-karing-classic'))return;
    const link=document.createElement('a');
    link.className='primary-btn tp-v15-karing-classic tp-v15-app-launch';
    link.href='karing://install-config?url='+encodeURIComponent(content)+'&name='+encodeURIComponent('TwinPanel');
    link.textContent='افزودن به Karing';
    const source=document.createElement('textarea');
    const id='tp-v15-classic-'+Math.random().toString(36).slice(2);
    source.id=id;
    source.className='hidden-source';
    source.readOnly=true;
    source.value=content;
    document.body.appendChild(source);
    link.dataset.tpCopyTarget=id;
    actions.appendChild(link);
  });
})();
</script>
"""


def refine_public_connection_modern_import_v15(
    source: str,
    token: str,
    db: Session,
) -> str:
    """Make every delivered protocol copyable and use registered app schemes."""
    if "TWINPANEL_PUBLIC_MODERN_IMPORT_V15" in source:
        return source

    sub = _subscription_from_share_token(token, db)
    if _status_value(sub) != "active":
        return source

    payload = _public_payload(db, sub)
    credentials = payload.get("credentials") if isinstance(payload, dict) else []
    hidden_sources: list[str] = []

    for cred in credentials if isinstance(credentials, list) else []:
        if not isinstance(cred, dict):
            continue
        protocol = str(cred.get("protocol") or "").strip().lower()
        if protocol not in MODERN_PROTOCOLS:
            continue

        for item in _items(cred):
            try:
                node_id = int(item.get("node_id") or 0)
            except (TypeError, ValueError):
                node_id = 0
            if node_id <= 0:
                continue

            profile_name = _profile_name(sub, protocol, item)
            copy_content = _copy_content(protocol, item, profile_name)
            if not copy_content:
                continue

            copy_target = f"tp-v15-copy-{protocol}-{node_id}-{len(hidden_sources)}"
            hidden_sources.append(
                f'<textarea id="{_h(copy_target)}" class="hidden-source" '
                f'readonly>{_h(copy_content)}</textarea>'
            )

            source = _insert_modern_copy_button(
                source,
                protocol=protocol,
                copy_target=copy_target,
                requires_karing_126=protocol in KARING_126_PROTOCOLS,
            )

            karing_uri = karing_inline_uri(protocol, item, profile_name)
            if not karing_uri:
                continue

            standard_uri = standard_share_uri(protocol, item, profile_name)
            config_path = (
                f"/v1/connect/{quote(str(token), safe='')}/modern-config-v14/"
                f"{quote(protocol, safe='')}/{node_id}"
            )
            if protocol == "mieru":
                config_path += "?profile=karing"

            source = _replace_remote_karing_button(
                source,
                config_path=config_path,
                karing_uri=karing_uri,
                copy_target=copy_target,
                standard_uri=standard_uri,
            )

    source = source.replace(
        "</style>",
        """
/* TWINPANEL_PUBLIC_MODERN_IMPORT_V15 */
.v15-karing-inline{white-space:nowrap}
.v15-standard-link{display:inline-flex;align-items:center;justify-content:center}
.tp-v15-copy-config,.tp-v15-classic-copy{white-space:nowrap}
.tp-v15-client-note{color:var(--muted);font-size:8px;line-height:1.7;max-width:250px}
""" + "\n</style>",
        1,
    )

    if hidden_sources:
        source = source.replace(
            "</body>",
            "".join(hidden_sources) + "\n</body>",
            1,
        )

    source = source.replace(
        "</body>",
        _V15_SCRIPT
        + "\n<!-- TWINPANEL_PUBLIC_MODERN_IMPORT_V15 -->\n</body>",
        1,
    )
    return source
