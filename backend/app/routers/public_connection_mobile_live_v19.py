from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_MOBILE_LIVE_V19"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MOBILE_LIVE_V19 */
@media(max-width:720px){
  .v17-protocol-card.v19-live-online{
    border-color:var(--ok);
    box-shadow:
      0 0 0 1px color-mix(in srgb,var(--ok) 28%,transparent),
      0 10px 28px color-mix(in srgb,var(--ok) 10%,transparent);
    background:linear-gradient(
      180deg,
      color-mix(in srgb,var(--ok) 4%,var(--surface)),
      var(--surface)
    );
  }
  .v17-protocol-card.v19-live-online .v17-count{
    color:var(--ok);
    border-color:color-mix(in srgb,var(--ok) 46%,var(--line));
    background:color-mix(in srgb,var(--ok) 10%,var(--surface));
  }
  .v17-protocol-card.v19-live-online .v17-title small{
    color:var(--ok);
    font-weight:900;
  }
  .v17-protocol-card.v19-live-online .v17-mark{
    box-shadow:0 0 0 2px color-mix(in srgb,var(--ok) 30%,transparent);
  }
  .v17-protocol-card.v19-live-online .v17-chevron{color:var(--ok)}
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectMobileLiveV19">
(function(){
  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='v2ray')return'xray';
    if(key==='naiveproxy')return'naive';
    if(key==='openconnect'||key==='ocserv'||key==='anyconnect')return'cisco';
    return key;
  }

  function sourceChoices(){
    const map=new Map();
    document.querySelectorAll('.protocol-choice[data-protocol-key]').forEach(choice=>{
      const key=normalize(choice.dataset.protocolKey||'');
      if(key&&!map.has(key))map.set(key,choice);
    });
    return map;
  }

  function mobileCards(){
    const map=new Map();
    document.querySelectorAll('.v17-protocol-card[data-protocol-key]').forEach(card=>{
      const key=normalize(card.dataset.protocolKey||'');
      if(key&&!map.has(key))map.set(key,card);
    });
    return map;
  }

  function syncLiveState(){
    if(!window.matchMedia('(max-width:720px)').matches)return;
    const sources=sourceChoices();
    const cards=mobileCards();

    cards.forEach((card,key)=>{
      const source=sources.get(key)||null;
      const online=Boolean(source&&source.classList.contains('live-online'));
      card.classList.toggle('v19-live-online',online);
      card.dataset.connection=online?'online':'idle';

      const subtitle=card.querySelector('.v17-title small');
      if(!subtitle)return;
      if(!subtitle.dataset.v19IdleSubtitle){
        subtitle.dataset.v19IdleSubtitle=String(subtitle.textContent||'').trim();
      }
      subtitle.textContent=online
        ? 'آنلاین · آماده اتصال'
        : (subtitle.dataset.v19IdleSubtitle||'آماده اتصال');
    });
  }

  function start(){
    if(!window.matchMedia('(max-width:720px)').matches)return;
    syncLiveState();

    const observer=new MutationObserver(syncLiveState);
    document.querySelectorAll('.protocol-choice[data-protocol-key]').forEach(choice=>{
      observer.observe(choice,{attributes:true,attributeFilter:['class']});
    });

    document.addEventListener('visibilitychange',()=>{
      if(!document.hidden)syncLiveState();
    });
    window.addEventListener('pageshow',syncLiveState);
  }

  window.setTimeout(start,40);
})();
</script>
"""


def refine_public_connection_mobile_live_v19(source: str) -> str:
    """Mirror the canonical live protocol class into the device-aware mobile cards."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    source = source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
    return source
