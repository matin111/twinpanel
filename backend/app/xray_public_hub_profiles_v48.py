from __future__ import annotations

import html
from typing import Any, Callable
from urllib.parse import quote


# TWINPANEL_XRAY_PUBLIC_HUB_PROFILES_V48
#
# Public payload/profile policy remains owned by the Xray runtime (V47+). V48
# only expands the real ordered profiles already selected for one Xray server
# into Hub V5 Quick Connect. Smart Connect keeps its canonical single action;
# Multilink/Subscription delivery is not imported or modified.

MARKER = "TWINPANEL_XRAY_PUBLIC_HUB_PROFILES_V48"
_runtime_applied = False
_original_item_detail: Callable[..., str] | None = None


def _h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _profile_title(profile: dict[str, Any], index: int) -> str:
    return str(
        profile.get("title")
        or profile.get("profile_title")
        or profile.get("name")
        or profile.get("id")
        or profile.get("profile")
        or f"Xray Profile {index + 1}"
    ).strip()


def _profiles(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only real usable profiles, preserving producer-provided order."""

    raw = item.get("profiles")
    if not isinstance(raw, list):
        return []

    result: list[dict[str, Any]] = []
    for value in raw:
        if not isinstance(value, dict):
            continue
        profile = dict(value)
        if not str(profile.get("uri") or "").strip():
            continue
        result.append(profile)
    return result


def _hiddify_link(uri: str, title: str) -> str:
    # Current Hiddify URL-scheme accepts a single proxy link as <sublink>.
    return f"hiddify://import/{quote(uri, safe='')}#{quote(title, safe='')}"


def _karing_link(uri: str, title: str) -> str:
    # Same direct-config URL scheme already used by TwinPanel Modern Import V15.
    return (
        "karing://install-config?url="
        f"{quote(uri, safe='')}&name={quote(title, safe='')}"
    )


def render_xray_quick_connect_profiles(item: dict[str, Any]) -> str | None:
    """Render real per-server profiles, or None to preserve legacy fallback."""

    profiles = _profiles(item)
    if not profiles:
        return None

    cards: list[str] = []
    for index, profile in enumerate(profiles):
        uri = str(profile.get("uri") or "").strip()
        title = _profile_title(profile, index)
        profile_id = str(profile.get("id") or profile.get("profile") or "").strip()
        transport = str(profile.get("transport") or "").strip()
        security = str(profile.get("security") or "").strip()
        qr = str(profile.get("qr") or "").strip()

        qr_html = (
            f'<img class="qr" src="{_h(qr)}" alt="QR {_h(title)}">'
            if qr
            else ""
        )
        metadata = " · ".join(value for value in (transport, security) if value)
        subtitle = metadata or "V2Ray / Xray"
        hiddify = _hiddify_link(uri, title)
        karing = _karing_link(uri, title)

        cards.append(
            '<div class="action-row tp-v48-xray-profile" '
            f'data-tp-xray-profile-id="{_h(profile_id)}" '
            f'data-tp-xray-profile-title="{_h(title)}">'
            f'{qr_html}'
            '<div class="action-copy">'
            f'<b class="tp-v48-profile-title">{_h(title)}</b>'
            f'<small>{_h(subtitle)}</small>'
            '</div>'
            '<div class="action-buttons tp-v48-profile-actions">'
            f'<button class="copy-btn" type="button" data-copy="{_h(uri)}">کپی لینک</button>'
            f'<a class="primary-btn tp-v48-v2rayn" href="{_h(uri)}" rel="noopener noreferrer">v2rayN / Client</a>'
            f'<a class="primary-btn tp-v48-hiddify" href="{_h(hiddify)}" rel="noopener noreferrer">Hiddify</a>'
            f'<a class="primary-btn tp-v48-karing" href="{_h(karing)}" rel="noopener noreferrer">Karing</a>'
            '</div>'
            '</div>'
        )

    return (
        f'<div class="tp-v48-xray-profiles" data-tp-xray-profile-count="{len(cards)}">'
        + "".join(cards)
        + "</div>"
    )


def _item_detail_v48(
    protocol: str,
    item: dict[str, Any],
    username: str,
    password: str,
    index: int,
    prefix: str,
) -> str:
    """Expand Xray only in server-specific Quick Connect, never Smart Connect."""

    if str(protocol or "").strip().lower() in {"v2ray", "xray"} and prefix != "smart":
        # V47 replaces this callable at runtime. Resolve it lazily so V48 always
        # consumes the final three-profile policy rather than an import-time copy.
        from . import xray_public_delivery_runtime as delivery

        prepared: list[dict[str, Any]] = []
        for profile in delivery._customer_profiles(item):
            entry = delivery._profile_delivery_item(item, profile)
            if entry is None:
                continue
            entry["id"] = str(profile.get("id") or entry.get("profile") or "")
            entry["title"] = str(
                profile.get("title")
                or entry.get("profile_title")
                or profile.get("id")
                or "Xray"
            )
            prepared.append(entry)

        if prepared:
            expanded = dict(item)
            expanded["profiles"] = prepared
            rendered = render_xray_quick_connect_profiles(expanded)
            if rendered:
                return rendered

    assert _original_item_detail is not None
    return _original_item_detail(
        protocol,
        item,
        username,
        password,
        index,
        prefix,
    )


def apply_xray_public_hub_profiles_v48() -> None:
    """Install the additive Hub V5 renderer overlay once per API process."""

    global _runtime_applied, _original_item_detail
    if _runtime_applied:
        return

    from .routers import public_connection_hub_v5 as hub

    _original_item_detail = hub._item_detail
    hub._item_detail = _item_detail_v48
    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_PUBLIC_HUB_PROFILES_V48_ACTIVE "
        "quick_connect_real_profiles=1 smart_connect_preserved=1 "
        "mobile_profile_actions=1 multilink_untouched=1",
        flush=True,
    )


_CSS = r"""
/* TWINPANEL_XRAY_PUBLIC_HUB_PROFILES_V48 */
.tp-v48-xray-profiles{display:grid;gap:10px;width:100%}
.tp-v48-xray-profile{width:100%}
.tp-v48-profile-actions{display:flex;flex-wrap:wrap;gap:8px}
@media(max-width:720px){
  .tp-v48-mobile-profiles{display:grid;gap:9px;width:100%}
  .tp-v48-mobile-profile{display:grid;grid-template-columns:auto 1fr;gap:9px;padding:10px;border:1px solid var(--line);border-radius:14px;background:var(--surface)}
  .tp-v48-mobile-profile .qr{width:52px;height:52px;grid-row:1 / span 2}
  .tp-v48-mobile-title{font-size:12px;font-weight:800;line-height:1.6}
  .tp-v48-mobile-actions{display:flex;flex-wrap:wrap;gap:6px}
  .tp-v48-mobile-actions .v17-action{font-size:11px;min-height:36px;padding:0 10px}
}
"""

_SCRIPT = r"""
<script id="twinpanelXrayPublicHubProfilesV48">
(function(){
  const MOBILE='(max-width:720px)';
  let observer=null,timer=null,patching=false;
  const norm=v=>{const x=String(v||'').trim().toLowerCase();return x==='v2ray'?'xray':x};
  const txt=el=>String(el?.textContent||'').trim();
  function choiceFor(panel){return [...document.querySelectorAll('.protocol-choice')].find(c=>c.dataset.protocol===panel.id)||null}
  function xrayPanel(){return [...document.querySelectorAll('.protocol-panel')].find(p=>norm(choiceFor(p)?.dataset.protocolKey||'')==='xray')||null}
  function actionLink(source,label,primary){
    if(!source)return null;
    const out=document.createElement('a');
    out.href=source.getAttribute('href')||'#';out.className='v17-action'+(primary?' primary':'');out.textContent=label;
    if(source.target)out.target=source.target;if(source.rel)out.rel=source.rel;
    return out;
  }
  function actionButton(source,label){
    if(!source)return null;
    const out=document.createElement('button');out.type='button';out.className='v17-action';out.textContent=label;
    out.addEventListener('click',()=>source.click());return out;
  }
  function mobileProfile(source){
    const card=document.createElement('div');card.className='tp-v48-mobile-profile';
    const qr=source.querySelector('img.qr');if(qr)card.appendChild(qr.cloneNode(true));
    const title=document.createElement('div');title.className='tp-v48-mobile-title';
    title.textContent=txt(source.querySelector('.tp-v48-profile-title'))||source.dataset.tpXrayProfileTitle||'Xray';card.appendChild(title);
    const actions=document.createElement('div');actions.className='tp-v48-mobile-actions';
    const copy=actionButton(source.querySelector('.copy-btn[data-copy]'),'کپی لینک');if(copy)actions.appendChild(copy);
    const direct=actionLink(source.querySelector('.tp-v48-v2rayn'),'v2rayN / Client',true);if(direct)actions.appendChild(direct);
    const hiddify=actionLink(source.querySelector('.tp-v48-hiddify'),'Hiddify',false);if(hiddify)actions.appendChild(hiddify);
    const karing=actionLink(source.querySelector('.tp-v48-karing'),'Karing',false);if(karing)actions.appendChild(karing);
    card.appendChild(actions);return card;
  }
  function patch(){
    if(patching||!window.matchMedia(MOBILE).matches)return;
    const panel=xrayPanel();if(!panel)return;
    const views=[...panel.querySelectorAll('.server-view')];
    const card=[...document.querySelectorAll('.v17-protocol-card[data-protocol-key]')].find(c=>norm(c.dataset.protocolKey)==='xray');
    if(!card)return;
    const rows=[...card.querySelectorAll('.v17-server-list>.v17-server-row')];
    patching=true;
    try{
      rows.forEach((row,index)=>{
        const profiles=[...(views[index]?.querySelectorAll('.tp-v48-xray-profile')||[])];
        if(!profiles.length)return;
        const actions=row.querySelector('.v17-server-actions');if(!actions)return;
        if(Number(actions.dataset.tpXrayV48Count||0)===profiles.length)return;
        const box=document.createElement('div');box.className='tp-v48-mobile-profiles';profiles.forEach(p=>box.appendChild(mobileProfile(p)));
        actions.replaceChildren(box);actions.dataset.tpXrayV48Count=String(profiles.length);
      });
      document.body.dataset.tpXrayProfilesV48='ready';
    }finally{patching=false}
  }
  function schedule(){clearTimeout(timer);timer=setTimeout(patch,0)}
  function connect(){
    const root=document.querySelector('.v17-mobile-stack')||document.body;
    observer?.disconnect();observer=new MutationObserver(schedule);observer.observe(root,{childList:true,subtree:true});patch();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(connect,0),{once:true});else setTimeout(connect,0);
  window.addEventListener('resize',schedule,{passive:true});
})();
</script>
"""


def refine_public_connection_xray_profiles_v48(source: str) -> str:
    """Keep all Xray profile actions visible in the V17 mobile presentation."""

    if f'id="twinpanelXrayPublicHubProfilesV48"' in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {MARKER} -->\n</body>", 1)
