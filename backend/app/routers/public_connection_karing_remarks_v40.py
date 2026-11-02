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
    parts.inner.searchParams.set('name',name);
    parts.deep.searchParams.set('url',parts.inner.toString());
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

  function protocolFor(link){
    const card=link.closest('.v38-all-card[data-v38-protocol]');
    return String(card?.dataset?.v38Protocol||'').trim().toLowerCase();
  }

  async function prepare(link){
    const protocol=protocolFor(link);if(!protocol)return link.getAttribute('href')||'';
    const current=link.getAttribute('href')||'';
    const fallback=accountName()+'-'+protocol;
    const profile=await canonicalProfile(current,fallback);
    const next=withName(current,profile);
    if(next)link.setAttribute('href',next);
    link.dataset.tpKaringProfile=profile;
    link.dataset.tpKaringInnerName='ready';
    return next||current;
  }

  function patch(){
    document.querySelectorAll('.v38-all-card[data-v38-protocol] a[href^="karing://install-config"]').forEach(function(link){
      if(link.dataset.tpKaringInnerName==='ready'||link.dataset.tpKaringInnerName==='pending')return;
      link.dataset.tpKaringInnerName='pending';
      prepare(link).catch(function(){link.dataset.tpKaringInnerName='idle'});
    });
  }

  document.addEventListener('click',async function(event){
    const link=event.target?.closest?.('.v38-all-card[data-v38-protocol] a[href^="karing://install-config"]');
    if(!link)return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const href=await prepare(link);
    if(href)window.location.href=href;
  },true);

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
