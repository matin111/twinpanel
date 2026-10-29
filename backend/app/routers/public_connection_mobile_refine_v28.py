from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_MOBILE_REFINE_V28"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MOBILE_REFINE_V28 */
@media(max-width:720px){
  /* Modern protocols are delivered by URI/config/import actions. Generic
     Server / Username / Password facts are not a customer connection method. */
  body.v27-mobile-ui .protocol-panel[data-modern-protocol] .facts{
    display:none!important;
  }

  /* Make the horizontally scrollable protocol picker visually explicit. */
  body.v27-mobile-ui .v27-protocol-strip{
    position:relative;
    padding:8px!important;
    border:1px solid var(--line);
    border-radius:14px;
    background:var(--surface2);
    box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--p) 4%,transparent);
  }

  body.v27-mobile-ui .v27-protocol-strip.v28-scrollable{
    border-color:color-mix(in srgb,var(--p) 34%,var(--line));
  }

  body.v27-mobile-ui .v28-scroll-hint{
    margin-top:7px;
    display:flex;
    align-items:center;
    justify-content:center;
    gap:6px;
    color:var(--muted);
    font-size:10px;
    font-weight:800;
    line-height:1.5;
    text-align:center;
    user-select:none;
  }

  body.v27-mobile-ui .v28-scroll-hint .v28-arrows{
    color:var(--p);
    font-size:15px;
    font-weight:900;
    line-height:1;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectMobileRefineV28">
(function(){
  const MOBILE='(max-width:720px)';

  function enhanceProtocolScroller(){
    if(!window.matchMedia(MOBILE).matches)return;
    const strip=document.querySelector('.v27-protocol-strip');
    if(!strip)return;

    const scrollable=strip.scrollWidth>strip.clientWidth+2;
    strip.classList.toggle('v28-scrollable',scrollable);

    let hint=document.querySelector('.v28-scroll-hint');
    if(!scrollable){
      hint?.remove();
      return;
    }

    if(!hint){
      hint=document.createElement('div');
      hint.className='v28-scroll-hint';
      hint.setAttribute('aria-hidden','true');
      hint.innerHTML='<span class="v28-arrows">↔</span><span>برای دیدن همه پروتکل‌ها به چپ یا راست بکشید</span>';
      strip.insertAdjacentElement('afterend',hint);
    }
  }

  function apply(){
    if(!window.matchMedia(MOBILE).matches)return;
    document.body.dataset.tpMobileRefine='v28';
    enhanceProtocolScroller();
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,160);
  window.addEventListener('resize',()=>window.setTimeout(apply,60),{passive:true});
})();
</script>
"""


def refine_public_connection_mobile_v28(source: str) -> str:
    """Refine phone-only modern protocol details and protocol navigation affordance."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    source = source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
    return source
