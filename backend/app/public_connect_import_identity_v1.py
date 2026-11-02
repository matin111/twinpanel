from __future__ import annotations

from .routers import public_connection_final_presentation_v37 as final_v37
from .routers import public_connection_forward_v34 as forward_v34
from .routers import public_connection_reference_layout_v38 as reference_v38


# TWINPANEL_PUBLIC_CONNECT_IMPORT_IDENTITY_V3
#
# The subscription endpoints already publish the canonical customer-facing
# Profile-Title (`username-protocol`). Karing's add-profile screen derives the
# Remarks value from the subscription URL itself in this order: fragment,
# `remarks`, `name`, response title, then host. Passing only `name=` on the
# outer karing://install-config scheme is therefore not sufficient on all
# Karing builds and can still fall back to the subscription domain.
#
# Resolve Profile-Title from the same-origin subscription response and also
# carry it as a URL fragment inside the encoded subscription URL. URL fragments
# are client-side only and are never sent to the subscription server, so this
# changes presentation/import identity only; provisioning and credentials are
# untouched.

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

_HIDDIFY_CLEAN = "return 'hiddify://import/'+encodeURI(url);"
_HIDDIFY_CANONICAL = "return 'hiddify://import/'+encodeURI(url)+'#'+encodeURIComponent(profile);"
_KARING_CLEAN = "return 'karing://install-config?url='+encodeURIComponent(url);"
_KARING_CANONICAL = "const karingUrl=String(url||'').split('#')[0]+'#'+profile;return 'karing://install-config?url='+encodeURIComponent(karingUrl)+'&name='+encodeURIComponent(profile);"

_PROFILE_RESOLVER = """\n    let profile=String(protocol||'vpn');\n    try{\n      const response=await fetch(url,{cache:'no-store'});\n      const header=String(response.headers.get('Profile-Title')||'').trim();\n      if(header)profile=header;\n    }catch(_error){}\n"""


def _remove_panel_brand(value: str) -> str:
    return str(value or "").replace(_HIDDIFY_OLD, _HIDDIFY_NEW).replace(_KARING_OLD, _KARING_NEW)


def _canonicalize_import_name(value: str, *, v38: bool = False) -> str:
    source = _remove_panel_brand(value)
    if _ASYNC_IMPORT_OLD not in source:
        return source

    source = source.replace(_ASYNC_IMPORT_OLD, _ASYNC_IMPORT_NEW)
    source = source.replace(_ASYNC_IMPORT_NEW, _ASYNC_IMPORT_NEW + _PROFILE_RESOLVER, 1)
    source = source.replace(_HIDDIFY_CLEAN, _HIDDIFY_CANONICAL)
    source = source.replace(_KARING_CLEAN, _KARING_CANONICAL)
    source = source.replace(_DEEP_OLD, _DEEP_NEW)
    if v38:
        source = source.replace(_V38_ALL_OLD, _V38_ALL_NEW)
    return source


def install() -> None:
    # Forward V34 is legacy/fallback presentation; remove stale branding there.
    forward_v34._SCRIPT = _remove_panel_brand(forward_v34._SCRIPT)

    # Active final/reference layouts explicitly carry username-protocol into the
    # Karing Remarks field instead of allowing the client to substitute domain.
    final_v37._SCRIPT = _canonicalize_import_name(final_v37._SCRIPT)
    reference_v38._SCRIPT = _canonicalize_import_name(reference_v38._SCRIPT, v38=True)


install()
