from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_KARING_REMARKS_V40"


_SCRIPT = r"""
<script id="twinpanelPublicConnectKaringRemarksV40">
(function(){
  function accountName(){
    const match=String(window.location.pathname||'').match(/^\/v1\/connect\/([^/]+)/);
    if(match){
      try{return decodeURIComponent(match[1])}catch(_error){return match[1]}
    }
    const service=document.querySelector('.service');
    const value=String(service?.textContent||'').trim();
    if(value)return value;
    const title=String(document.title||'').split('·').pop()?.trim()||'';
    return title;
  }

  function deepParts(raw){
    const href=String(raw||'').trim();
    if(!href)return null;
    try{
      const deep=new URL(href);
      const innerRaw=String(deep.searchParams.get('url')||'').trim();
      if(!innerRaw)return null;
      const inner=new URL(innerRaw,window.location.origin);
      return {deep,inner};
    }catch(_error){return null}
  }

  function withName(raw,name){
    const parts=deepParts(raw);
    if(!parts||!name)return String(raw||'');

    // Karing's Add Profile dialog derives Remarks from the subscription URL
    // itself (fragment -> remarks -> name -> title -> host). Therefore the
    // canonical profile name must live on the inner Multi-Link URL, not only
    // on the outer karing://install-config deep link.
    parts.inner.searchParams.set('name',name);
    parts.deep.searchParams.set('url',parts.inner.toString());

    // Keep the outer name as a compatibility hint for Karing versions that
    // consume install-config metadata directly.
    parts.deep.searchParams.set('name',name);
    return parts.deep.toString();
  }

  async function canonicalProfile(raw,fallback){
    const parts=deepParts(raw);
    if(!parts)return fallback;
    try{
      const response=await fetch(parts.inner.toString(),{cache:'no-store'});
      const header=String(response.headers.get('Profile-Title')||'').trim();
      if(header)return header;
    }catch(_error){}
    return fallback;
  }

  function patch(){
    const account=accountName();
    if(!account)return;
    document.querySelectorAll('.v38-all-card[data-v38-protocol]').forEach(function(card){
      const protocol=String(card.dataset.v38Protocol||'').trim().toLowerCase();
      if(!protocol)return;
      const fallback=account+'-'+protocol;
      card.querySelectorAll('a[href^="karing://install-config"]').forEach(async function(link){
        if(link.dataset.tpKaringInnerName==='pending')return;
        link.dataset.tpKaringInnerName='pending';
        const current=link.getAttribute('href')||'';
        const profile=await canonicalProfile(current,fallback);
        const next=withName(current,profile);
        if(next&&next!==current)link.setAttribute('href',next);
        link.dataset.tpKaringProfile=profile;
        link.dataset.tpKaringInnerName='ready';
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
