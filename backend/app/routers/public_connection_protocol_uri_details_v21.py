from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_PROTOCOL_URI_DETAILS_V21"


_SCRIPT = r"""
<script id="twinpanelPublicConnectProtocolUriDetailsV21">
(function(){
  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='v2ray')return'xray';
    if(key==='naiveproxy')return'naive';
    if(key==='openconnect'||key==='ocserv'||key==='anyconnect')return'cisco';
    return key;
  }
  function sourceValue(id){
    const el=document.getElementById(String(id||''));
    return el?String('value' in el?el.value:el.textContent||''):'';
  }
  function canonicalCopy(view){
    const target=view.querySelector('[data-tp-copy-target]');
    if(target){const value=sourceValue(target.dataset.tpCopyTarget);if(value)return value}
    const direct=view.querySelector('.copy-btn[data-copy]');
    if(direct&&String(direct.dataset.copy||'').trim())return String(direct.dataset.copy||'');
    const open=view.querySelector('a.v13-open-uri[href]');
    return open?String(open.getAttribute('href')||''):'';
  }
  function line(label,value){
    const raw=String(value??'').trim();
    return raw?[label,raw]:null;
  }
  function safeDecode(value){try{return decodeURIComponent(String(value||''))}catch(_error){return String(value||'')}}
  function parseStandardUri(raw,key){
    let url;
    try{url=new URL(String(raw||''))}catch(_error){return[]}
    const server=url.hostname.replace(/^\[|\]$/g,'');
    const port=url.port;
    const sni=url.searchParams.get('sni')||'';
    if(key==='hysteria2')return[
      line('Server',server),line('Port',port),line('Password',safeDecode(url.username)),line('SNI',sni)
    ].filter(Boolean);
    if(key==='tuic')return[
      line('Server',server),line('Port',port),line('UUID',safeDecode(url.username)),line('Password',safeDecode(url.password)),line('SNI',sni)
    ].filter(Boolean);
    if(key==='anytls')return[
      line('Server',server),line('Port',port),line('Password',safeDecode(url.username)),line('SNI',sni)
    ].filter(Boolean);
    return[];
  }
  function parseSudoku(raw){
    const value=String(raw||'').trim();
    if(!value.toLowerCase().startsWith('sudoku://'))return[];
    let encoded=value.slice('sudoku://'.length).split('#',1)[0];
    encoded=encoded.replace(/-/g,'+').replace(/_/g,'/');
    while(encoded.length%4)encoded+='=';
    try{
      const bytes=atob(encoded);
      const arr=Uint8Array.from(bytes,ch=>ch.charCodeAt(0));
      const doc=JSON.parse(new TextDecoder().decode(arr));
      return[
        line('Server',doc.h),line('Port',doc.p),line('Key',doc.k),line('AEAD',doc.e)
      ].filter(Boolean);
    }catch(_error){return[]}
  }
  function keyForPanel(panel){
    const choice=[...document.querySelectorAll('.protocol-choice')]
      .find(item=>item.dataset.protocol===panel.id);
    return normalize(choice?.dataset.protocolKey||panel.dataset.modernProtocol||'');
  }
  function sourcePanel(key){
    return [...document.querySelectorAll('.protocol-panel')]
      .find(panel=>keyForPanel(panel)===key)||null;
  }
  function patch(){
    if(!window.matchMedia('(max-width:720px)').matches)return;
    document.querySelectorAll('.v17-protocol-card[data-protocol-key]').forEach(card=>{
      const key=normalize(card.dataset.protocolKey||'');
      if(!['hysteria2','tuic','anytls','sudoku'].includes(key))return;
      const panel=sourcePanel(key);if(!panel)return;
      const views=[...panel.querySelectorAll('.server-view')];
      const rows=[...card.querySelectorAll('.v17-server-list>.v17-server-row')];
      views.forEach((view,index)=>{
        const row=rows[index];if(!row)return;
        const raw=canonicalCopy(view);
        const details=key==='sudoku'?parseSudoku(raw):parseStandardUri(raw,key);
        if(!details.length)return;
        let detail=row.querySelector('.v17-details');
        if(!detail){detail=document.createElement('div');detail.className='v17-details';row.appendChild(detail)}
        detail.textContent=details.map(item=>item[0]+': '+item[1]).join('\n');
      });
    });
  }
  window.setTimeout(patch,170);
})();
</script>
"""


def refine_public_connection_protocol_uri_details_v21(source: str) -> str:
    """Parse canonical standard/deeplink payloads for accurate mobile details."""
    if _MARKER in source:
        return source
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
