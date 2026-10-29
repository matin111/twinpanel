from __future__ import annotations


_MARKER = "TWINPANEL_PUBLIC_CONNECT_MANUAL_CREDENTIALS_V35"


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MANUAL_CREDENTIALS_V35 */
body.v35-ready .v35-manual-credentials{
  margin:12px;
  padding:13px;
  border:1px solid color-mix(in srgb,var(--p) 28%,var(--line));
  border-radius:14px;
  background:var(--surface2);
}
body.v35-ready .v35-manual-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  margin-bottom:10px;
}
body.v35-ready .v35-manual-head b{
  font-size:14px;
  line-height:1.5;
}
body.v35-ready .v35-manual-head span{
  color:var(--muted);
  font-size:11px;
  font-weight:800;
}
body.v35-ready .v35-manual-grid{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
  gap:8px;
}
body.v35-ready .v35-manual-item{
  min-width:0;
  padding:10px;
  border:1px solid var(--line);
  border-radius:11px;
  background:var(--surface);
}
body.v35-ready .v35-manual-item small{
  display:block;
  margin-bottom:6px;
  color:var(--muted);
  font-size:11px;
  font-weight:800;
}
body.v35-ready .v35-manual-item strong{
  display:block;
  overflow-wrap:anywhere;
  color:var(--text);
  font-size:14px;
  line-height:1.55;
}
body.v35-ready .v35-manual-item button{
  width:100%;
  min-height:36px;
  margin-top:8px;
  padding:7px 10px;
  border:1px solid color-mix(in srgb,var(--p) 42%,var(--line));
  border-radius:9px;
  background:var(--surface2);
  color:var(--p);
  font:inherit;
  font-size:11px;
  font-weight:900;
  cursor:pointer;
}
body.v35-ready .protocol-panel[data-v35-manual-shared="1"]
.server-view .fact[data-v35-shared-credential="1"]{
  display:none!important;
}
body.v35-ready .protocol-panel[data-v35-manual-shared="1"] .server-view .facts{
  grid-template-columns:repeat(auto-fit,minmax(180px,1fr))!important;
}
@media(max-width:720px){
  body.v35-ready[data-tp-platform="android"] .v35-manual-credentials,
  body.v35-ready[data-tp-platform="ios"] .v35-manual-credentials{
    margin:10px;
    padding:11px;
  }
  body.v35-ready[data-tp-platform="android"] .v35-manual-grid,
  body.v35-ready[data-tp-platform="ios"] .v35-manual-grid{
    grid-template-columns:1fr;
  }
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectManualCredentialsV35">
(function(){
  const MANUAL=new Set(['cisco','l2tp']);
  const EXPECTED={
    cisco:['username','password'],
    l2tp:['username','password','secret']
  };
  const LABELS={
    username:'نام کاربری',
    password:'رمز عبور',
    secret:'IPsec Secret'
  };
  const COPY_LABELS={
    username:'کپی نام کاربری',
    password:'کپی رمز عبور',
    secret:'کپی Secret'
  };
  const text=el=>String(el?.textContent||'').trim();

  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='openconnect'||key==='ocserv'||key==='anyconnect')return'cisco';
    return key;
  }

  function panelKey(panel){
    const choice=[...document.querySelectorAll('.protocol-choice')]
      .find(item=>String(item.dataset.protocol||'')===String(panel?.id||''));
    return normalize(choice?.dataset?.protocolKey||choice?.dataset?.protocol||'');
  }

  function credentialKey(label){
    const value=String(label||'').trim().toLowerCase();
    if(value.includes('username')||value.includes('نام کاربری'))return'username';
    if(value.includes('password')||value.includes('رمز عبور'))return'password';
    if(value.includes('secret'))return'secret';
    return'';
  }

  function factRecord(view,key){
    for(const fact of view.querySelectorAll('.fact')){
      if(credentialKey(text(fact.querySelector('small')))!==key)continue;
      const value=text(fact.querySelector('strong'));
      if(!value||value==='—')return null;
      return {fact,value};
    }
    return null;
  }

  function sharedRows(views,protocol){
    const rows=[];
    for(const key of EXPECTED[protocol]||[]){
      const records=views.map(view=>factRecord(view,key));
      if(!records.length||records.some(record=>!record))continue;
      const first=records[0].value;
      if(!records.every(record=>record.value===first))continue;
      rows.push({key,value:first,records});
    }
    return rows;
  }

  function notify(message){
    const toast=document.getElementById('toast');
    if(!toast)return;
    toast.textContent=message;
    toast.classList.add('show');
    clearTimeout(window.__tpV35Toast);
    window.__tpV35Toast=setTimeout(()=>toast.classList.remove('show'),1700);
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

  function credentialItem(row){
    const item=document.createElement('div');
    item.className='v35-manual-item';
    const label=document.createElement('small');
    label.textContent=LABELS[row.key]||row.key;
    const value=document.createElement('strong');
    value.textContent=row.value;
    const copyButton=document.createElement('button');
    copyButton.type='button';
    copyButton.textContent=COPY_LABELS[row.key]||'کپی';
    copyButton.addEventListener('click',async()=>{
      notify(await copy(row.value)?'کپی شد ✓':'کپی انجام نشد');
    });
    item.append(label,value,copyButton);
    return item;
  }

  function buildPanel(panel){
    panel.querySelectorAll('.v35-manual-credentials').forEach(node=>node.remove());
    panel.querySelectorAll('[data-v35-shared-credential="1"]').forEach(node=>{
      delete node.dataset.v35SharedCredential;
    });
    delete panel.dataset.v35ManualShared;

    const protocol=panelKey(panel);
    if(!MANUAL.has(protocol))return;
    const views=[...panel.querySelectorAll('.server-view')];
    if(!views.length)return;

    const rows=sharedRows(views,protocol);
    if(!rows.length)return;

    rows.forEach(row=>row.records.forEach(record=>{
      record.fact.dataset.v35SharedCredential='1';
    }));

    const card=document.createElement('section');
    card.className='v35-manual-credentials';
    const head=document.createElement('div');
    head.className='v35-manual-head';
    const title=document.createElement('b');
    title.textContent='اطلاعات ورود';
    const note=document.createElement('span');
    note.textContent='مشترک برای همه سرورها';
    head.append(title,note);
    const grid=document.createElement('div');
    grid.className='v35-manual-grid';
    rows.forEach(row=>grid.appendChild(credentialItem(row)));
    card.append(head,grid);

    const panelHead=panel.querySelector('.panel-head');
    if(panelHead)panelHead.insertAdjacentElement('afterend',card);
    else panel.insertAdjacentElement('afterbegin',card);
    panel.dataset.v35ManualShared='1';
  }

  function apply(){
    document.body.classList.add('v35-ready');
    document.body.dataset.tpManualCredentials='v35';
    document.querySelectorAll('.protocol-panel').forEach(buildPanel);
  }

  apply();
  window.setTimeout(apply,0);
  window.setTimeout(apply,220);
  window.setTimeout(apply,700);
})();
</script>
"""


def refine_public_connection_manual_credentials_v35(source: str) -> str:
    """Hoist only truly shared Cisco/L2TP credentials above their server list."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
