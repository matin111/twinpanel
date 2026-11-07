from __future__ import annotations

import re

from .routers import public_connection_final_presentation_v37 as final_v37
from .routers import public_connection_forward_v34 as forward_v34
from .routers import public_connection_reference_layout_v38 as reference_v38


# TWINPANEL_PUBLIC_CONNECT_IMPORT_IDENTITY_V3
#
# Karing uses the outer install-config `name=` value for the Add Profile
# "Remarks" field. If that value is absent, Karing falls back to the subscription
# host (for example sub.example.com). Resolve the canonical Profile-Title from
# the same-origin subscription endpoint and always pass it explicitly.
#
# V34 owns the visible desktop "اتصال به Karing" / subscription action. V37/V38
# own the HA/reference cards. All three must carry the same username-protocol
# identity; provisioning, credentials and dataplane are intentionally untouched.

_HIDDIFY_OLD = "'hiddify://import/'+encodeURI(url)+'#TwinPanel-'+encodeURIComponent(protocol)"
_HIDDIFY_NEW = "'hiddify://import/'+encodeURI(url)"
_KARING_OLD = "'karing://install-config?url='+encodeURIComponent(url)+'&name='+encodeURIComponent('TwinPanel '+protocol)"
_KARING_NEW = "'karing://install-config?url='+encodeURIComponent(url)"

_ASYNC_IMPORT_OLD = "function importHref(protocol,client,url){"
_ASYNC_IMPORT_NEW = "async function importHref(protocol,client,url){"
_DEEP_OLD = "const deep=importHref(protocol,client,url);"
_DEEP_NEW = "const deep=await importHref(protocol,client,url);"
_V38_ALL_OLD = "function allCard(panel,protocol,url,count,kind){"
_V38_ALL_NEW = "async function allCard(panel,protocol,url,count,kind){"

_V34_USE_OLD = "function useSubscription(protocol,client){"
_V34_USE_NEW = "async function useSubscription(protocol,client){"
_V34_URL_LINE = "    const url=subscriptionUrl(protocol);if(!url)return;\n"
_V34_HIDDIFY_CLEAN = "      window.location.href='hiddify://import/'+encodeURI(url);return;"
_V34_HIDDIFY_CANONICAL = "      window.location.href='hiddify://import/'+encodeURI(url)+'#'+encodeURIComponent(profile);return;"
_V34_KARING_CLEAN = "      window.location.href='karing://install-config?url='+encodeURIComponent(url);return;"
_V34_KARING_CANONICAL = "      window.location.href='karing://install-config?url='+encodeURIComponent(url)+'&name='+encodeURIComponent(profile);return;"

_HIDDIFY_CLEAN = "return 'hiddify://import/'+encodeURI(url);"
_HIDDIFY_CANONICAL = "return 'hiddify://import/'+encodeURI(url)+'#'+encodeURIComponent(profile);"
_KARING_CLEAN = "return 'karing://install-config?url='+encodeURIComponent(url);"
_KARING_CANONICAL = "return 'karing://install-config?url='+encodeURIComponent(url)+'&name='+encodeURIComponent(profile);"

_PROFILE_RESOLVER = """\n    let profile=String(protocol||'vpn');\n    try{\n      const match=String(window.location.pathname||'').match(/^\\/v1\\/connect\\/([^/]+)/);\n      const account=match?(decodeURIComponent(match[1])||''):'';\n      if(account)profile=account+'-'+String(protocol||'vpn');\n    }catch(_error){}\n    try{\n      const response=await fetch(url,{cache:'no-store'});\n      const header=String(response.headers.get('Profile-Title')||'').trim();\n      if(header)profile=header;\n    }catch(_error){}\n"""


def _remove_panel_brand(value: str) -> str:
    return str(value or "").replace(_HIDDIFY_OLD, _HIDDIFY_NEW).replace(_KARING_OLD, _KARING_NEW)


def _make_async_once(source: str, signature: str) -> str:
    """Upgrade a JS function exactly once, including already-patched source."""
    # Plain substring replacement also matches inside "async function", leading
    # to the invalid browser JavaScript "async async function".
    source = source.replace("async async " + signature, "async " + signature)
    return re.sub(r"(?<!async )" + re.escape(signature), "async " + signature, source, count=1)


def _inject_resolver_once(source: str, async_signature: str) -> str:
    marker = "let profile=String(protocol||'vpn');"
    pos = source.find(async_signature)
    if pos < 0:
        return source
    tail = source[pos + len(async_signature):]
    if marker in tail[:1000]:
        return source
    return source[:pos + len(async_signature)] + _PROFILE_RESOLVER + tail


def _canonicalize_v34_subscription_name(value: str) -> str:
    source = _remove_panel_brand(value)
    if _V34_USE_OLD not in source:
        return source

    source = _make_async_once(source, _V34_USE_OLD)
    if _V34_URL_LINE in source and "let profile=String(protocol||'vpn');" not in source:
        source = source.replace(_V34_URL_LINE, _V34_URL_LINE + _PROFILE_RESOLVER, 1)
    source = source.replace(_V34_HIDDIFY_CLEAN, _V34_HIDDIFY_CANONICAL, 1)
    source = source.replace(_V34_KARING_CLEAN, _V34_KARING_CANONICAL, 1)
    return source


def _canonicalize_import_name(value: str, *, v38: bool = False) -> str:
    source = _remove_panel_brand(value)
    if _ASYNC_IMPORT_OLD not in source:
        return source

    source = _make_async_once(source, _ASYNC_IMPORT_OLD)
    source = _inject_resolver_once(source, _ASYNC_IMPORT_NEW)
    source = source.replace(_HIDDIFY_CLEAN, _HIDDIFY_CANONICAL)
    source = source.replace(_KARING_CLEAN, _KARING_CANONICAL)
    source = source.replace(_DEEP_OLD, _DEEP_NEW)
    if v38:
        source = _make_async_once(source, _V38_ALL_OLD)
    return source


def install() -> None:
    # V34 owns the visible desktop subscription action shown in the customer
    # page. Carry the canonical username-protocol explicitly into Karing.
    forward_v34._SCRIPT = _canonicalize_v34_subscription_name(forward_v34._SCRIPT)

    # HA/reference layouts use the same canonical identity contract.
    final_v37._SCRIPT = _canonicalize_import_name(final_v37._SCRIPT)
    reference_v38._SCRIPT = _canonicalize_import_name(reference_v38._SCRIPT, v38=True)


install()
