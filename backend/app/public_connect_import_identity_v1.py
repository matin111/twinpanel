from __future__ import annotations

from .routers import public_connection_final_presentation_v37 as final_v37
from .routers import public_connection_forward_v34 as forward_v34
from .routers import public_connection_reference_layout_v38 as reference_v38


# TWINPANEL_PUBLIC_CONNECT_IMPORT_IDENTITY_V1
# Multi-Link endpoints already publish the canonical customer-facing title in
# Profile-Title (username-protocol). Do not override it in Karing/Hiddify with
# a panel-branded deep-link name. When the explicit name/fragment is omitted,
# clients use the subscription metadata returned by the URL itself.

_HIDDIFY_OLD = "'hiddify://import/'+encodeURI(url)+'#TwinPanel-'+encodeURIComponent(protocol)"
_HIDDIFY_NEW = "'hiddify://import/'+encodeURI(url)"
_KARING_OLD = "'karing://install-config?url='+encodeURIComponent(url)+'&name='+encodeURIComponent('TwinPanel '+protocol)"
_KARING_NEW = "'karing://install-config?url='+encodeURIComponent(url)"


def _clean_script(value: str) -> str:
    return str(value or "").replace(_HIDDIFY_OLD, _HIDDIFY_NEW).replace(_KARING_OLD, _KARING_NEW)


def install() -> None:
    forward_v34._SCRIPT = _clean_script(forward_v34._SCRIPT)
    final_v37._SCRIPT = _clean_script(final_v37._SCRIPT)
    reference_v38._SCRIPT = _clean_script(reference_v38._SCRIPT)


install()
