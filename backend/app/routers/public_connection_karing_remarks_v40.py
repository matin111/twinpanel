from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_KARING_REMARKS_V40"


_SCRIPT = r"""
<script id="twinpanelPublicConnectKaringRemarksV40">
(function(){
  function accountName(){
    const service=document.querySelector('.service');
    const value=String(service?.textContent||'').trim();
    if(value)return value;
    const title=String(document.title||'').split('·').pop()?.trim()||'';
    return title;
  }

  function withName(raw,name){
    let href=String(raw||'').trim();
    if(!href||!name)return href;
    href=href.replace(/([?&])name=[^&]*/i,'$1').replace(/[?&]$/,'');
    const join=href.includes('?')?'&':'?';
    return href+join+'name='+encodeURIComponent(name);
  }

  function patch(){
    const account=accountName();
    if(!account)return;
    document.querySelectorAll('.v38-all-card[data-v38-protocol]').forEach(function(card){
      const protocol=String(card.dataset.v38Protocol||'').trim().toLowerCase();
      if(!protocol)return;
      const profile=account+'-'+protocol;
      card.querySelectorAll('a[href^="karing://install-config"]').forEach(function(link){
        const current=link.getAttribute('href')||'';
        const next=withName(current,profile);
        if(next&&next!==current)link.setAttribute('href',next);
        link.dataset.tpKaringProfile=profile;
      });
    });
  }

  patch();
  window.setTimeout(patch,0);
  window.setTimeout(patch,300);
  window.setTimeout(patch,900);
  const observer=new MutationObserver(patch);
  observer.observe(document.documentElement,{subtree:true,childList:true});
  window.setTimeout(()=>observer.disconnect(),4000);
})();
</script>
"""


def refine_public_connection_karing_remarks_v40(source: str) -> str:
    """Force Karing HA import remarks to canonical account username + protocol."""
    if _MARKER in source:
        return source
    return source.replace(
        "</body>",
        _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>",
        1,
    )
