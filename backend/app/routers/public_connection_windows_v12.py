from __future__ import annotations


_V12_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_WINDOWS_V12 */
.tp-win-v2ray-actions{
  display:flex;
  align-items:center;
  flex-wrap:wrap;
  gap:7px;
}
.tp-win-v2ray-actions .primary-btn,
.tp-win-v2ray-actions .copy-btn{
  min-width:118px;
}
.tp-win-v2ray-note{
  margin-top:7px;
  color:var(--muted);
  font-size:8px;
  line-height:1.8;
}
body:not([data-tp-platform="windows"]) .tp-win-only{display:none}
"""


_V12_SCRIPT = r"""
<script id="twinpanelPublicConnectWindowsV12">
(function(){
  const body=document.body;
  if(body.dataset.tpPlatform!=='windows')return;

  const toast=document.getElementById('toast');
  function notify(text){
    if(!toast)return;
    toast.textContent=text;
    toast.classList.add('show');
    clearTimeout(window.__tpWinV12Toast);
    window.__tpWinV12Toast=setTimeout(()=>toast.classList.remove('show'),1800);
  }
  function absolute(value){
    try{return new URL(value,window.location.href).href}catch(_error){return value}
  }
  function fallbackCopy(value){
    const area=document.createElement('textarea');
    area.value=value;
    area.style.position='fixed';
    area.style.opacity='0';
    document.body.appendChild(area);
    area.select();
    let ok=false;
    try{ok=document.execCommand('copy')}catch(_error){}
    area.remove();
    return ok;
  }
  async function copy(value){
    if(navigator.clipboard&&window.isSecureContext){
      try{await navigator.clipboard.writeText(value);return true}catch(_error){}
    }
    return fallbackCopy(value);
  }
  function isV2RayUri(value){
    return /^(vmess|vless|trojan|ss|hysteria2|hy2|tuic):/i.test(String(value||''));
  }
  function hiddifyLink(value){
    const target=String(value||'').trim();
    if(!target)return'';
    return 'hiddify://import/'+encodeURI(target)+'#TwinPanel';
  }
  function makeCopyButton(value){
    const button=document.createElement('button');
    button.type='button';
    button.className='copy-btn tp-win-only tp-win-v2ray-copy';
    button.textContent='کپی برای v2rayN';
    button.addEventListener('click',async()=>{
      const ok=await copy(value);
      notify(ok?'مولتی‌لینک برای v2rayN کپی شد':'کپی انجام نشد');
    });
    return button;
  }
  function ensureNote(container){
    if(!container||container.querySelector('.tp-win-v2ray-note'))return;
    const note=document.createElement('div');
    note.className='tp-win-v2ray-note tp-win-only';
    note.textContent='Hiddify با یک کلیک Import می‌شود. برای v2rayN لینک را کپی کنید و در Subscription Settings اضافه کنید.';
    container.appendChild(note);
  }

  const subscriptionSource=
    document.querySelector('[data-v7-copy-url]')||
    document.querySelector('[data-v7-share-url]');
  const subscriptionUrl=subscriptionSource?
    absolute(subscriptionSource.dataset.v7CopyUrl||subscriptionSource.dataset.v7ShareUrl||''):'';

  document.querySelectorAll('.action-row a.primary-btn[href]').forEach(link=>{
    const original=link.getAttribute('href')||'';
    if(!isV2RayUri(original))return;
    const importTarget=subscriptionUrl||original;
    const actions=link.closest('.action-buttons')||link.parentElement;
    if(!actions)return;

    link.href=hiddifyLink(importTarget);
    link.removeAttribute('target');
    link.removeAttribute('rel');
    link.textContent='افزودن به Hiddify';
    link.classList.add('tp-win-only','tp-win-hiddify');
    link.title='Import در Hiddify';
    link.addEventListener('click',()=>{
      notify('در حال ارسال اشتراک به Hiddify…');
    });

    if(!actions.querySelector('.tp-win-v2ray-copy')){
      actions.appendChild(makeCopyButton(importTarget));
    }
    actions.classList.add('tp-win-v2ray-actions');
    ensureNote(link.closest('.action-row'));
  });

  const multi=document.querySelector('.multi-link-card');
  const multiActions=multi&&multi.querySelector('.multi-link-actions');
  if(subscriptionUrl&&multiActions){
    if(!multiActions.querySelector('.tp-win-hiddify')){
      const hiddify=document.createElement('a');
      hiddify.className='primary-btn tp-win-only tp-win-hiddify';
      hiddify.href=hiddifyLink(subscriptionUrl);
      hiddify.textContent='افزودن به Hiddify';
      hiddify.title='Import مولتی‌لینک در Hiddify';
      hiddify.addEventListener('click',()=>notify('در حال ارسال اشتراک به Hiddify…'));
      multiActions.appendChild(hiddify);
    }
    if(!multiActions.querySelector('.tp-win-v2ray-copy')){
      multiActions.appendChild(makeCopyButton(subscriptionUrl));
    }
    multiActions.classList.add('tp-win-v2ray-actions');
    ensureNote(multi);
  }
})();
</script>
"""


def refine_public_connection_windows_v12(source: str) -> str:
    """Replace unreliable generic Windows V2Ray deep-links with app-specific import actions."""
    if "TWINPANEL_PUBLIC_CONNECT_WINDOWS_V12" in source:
        return source
    source = source.replace("</style>", _V12_CSS + "\n</style>", 1)
    source = source.replace("</body>", _V12_SCRIPT + "\n</body>", 1)
    return source
