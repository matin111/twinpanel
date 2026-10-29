from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_ACTION_V44"


_SCRIPT = r"""
<script id="twinpanelPublicConnectV2rayMultilinkActionV44">
(function(){
  function token(){
    const match=String(window.location.pathname||'').match(/^\/v1\/connect\/([^/]+)/);
    if(!match)return'';
    try{return decodeURIComponent(match[1])}catch(_error){return match[1]}
  }

  function multiUrl(){
    const value=token();
    if(!value)return'';
    return window.location.origin+'/v1/connect/'+encodeURIComponent(value)+'/multi/v2ray';
  }

  function hiddifyUrl(url){
    return 'hiddify://import/'+encodeURI(url)+'#TwinPanel-v2ray';
  }

  function fallbackCopy(value){
    const area=document.createElement('textarea');
    area.value=String(value||'');
    area.readOnly=true;
    area.style.position='fixed';
    area.style.left='-9999px';
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
    const raw=String(value||'').trim();
    if(!raw)return false;
    if(navigator.clipboard&&window.isSecureContext){
      try{await navigator.clipboard.writeText(raw);return true}catch(_error){}
    }
    return fallbackCopy(raw);
  }

  function notify(message){
    const toast=document.getElementById('toast');
    if(!toast)return;
    toast.textContent=message;
    toast.classList.add('show');
    clearTimeout(window.__tpV44Toast);
    window.__tpV44Toast=setTimeout(()=>toast.classList.remove('show'),1500);
  }

  function rewrite(){
    const url=multiUrl();
    if(!url)return;

    document.querySelectorAll('.v38-all-card[data-v38-protocol="v2ray"]').forEach(card=>{
      const actions=card.querySelector('.v38-all-actions');
      if(!actions)return;

      const send=document.createElement('a');
      send.className='v38-primary v44-v2ray-multi-hiddify';
      send.textContent='ارسال همه به Hiddify';
      send.href=hiddifyUrl(url);
      send.setAttribute('aria-label','ارسال مولتی لینک ۹ کانفیگ V2Ray به Hiddify');

      const copyButton=document.createElement('button');
      copyButton.type='button';
      copyButton.className='v38-copy v44-v2ray-multi-copy';
      copyButton.textContent='کپی لینک';
      copyButton.setAttribute('aria-label','کپی لینک مولتی V2Ray');
      copyButton.addEventListener('click',async()=>{
        notify(await copy(url)?'لینک مولتی V2Ray کپی شد ✓':'کپی انجام نشد');
      });

      actions.replaceChildren(send,copyButton);
      card.dataset.v44V2rayMulti='1';
      card.dataset.v44Endpoint='/multi/v2ray';
    });
  }

  rewrite();
  window.setTimeout(rewrite,0);
  window.setTimeout(rewrite,300);
  window.setTimeout(rewrite,950);
})();
</script>
"""


def refine_public_connection_v2ray_multilink_action_v44(source: str) -> str:
    """Wire the V2Ray Multi Server UI exclusively to the all-profile /multi/v2ray endpoint."""
    if _MARKER in source:
        return source
    return source.replace(
        "</body>",
        _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>",
        1,
    )
