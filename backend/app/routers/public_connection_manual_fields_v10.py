from __future__ import annotations


_V10_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MANUAL_FIELDS_V10 */
@media(max-width:720px){
  .v9-server-row.v10-manual-row{
    grid-template-columns:minmax(0,1fr);
    align-items:stretch;
    gap:9px;
    padding:10px;
  }
  .v10-manual-row > .v9-server-main{
    width:100%;
  }
  .v10-credential-grid{
    grid-column:1/-1;
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:7px;
    direction:rtl;
  }
  .v10-grid-head{
    grid-column:1/-1;
    min-height:32px;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:9px;
    padding:0 2px;
  }
  .v10-grid-head b{
    font-size:9px;
    font-weight:900;
    color:var(--text);
  }
  .v10-copy-all,
  .v10-field-copy{
    border:1px solid color-mix(in srgb,var(--p) 28%,var(--line));
    border-radius:9px;
    background:color-mix(in srgb,var(--p) 7%,var(--surface));
    color:var(--p);
    font-family:inherit;
    font-weight:900;
    cursor:pointer;
  }
  .v10-copy-all{
    min-height:29px;
    padding:0 9px;
    display:inline-flex;
    align-items:center;
    gap:5px;
    font-size:7.5px;
  }
  .v10-copy-all svg,
  .v10-field-copy svg{
    width:14px;
    height:14px;
    display:block;
    flex:0 0 14px;
  }
  .v10-field{
    min-width:0;
    min-height:62px;
    padding:9px 10px;
    display:grid;
    grid-template-columns:minmax(0,1fr) auto;
    grid-template-rows:auto 1fr;
    align-items:center;
    gap:5px 7px;
    border:1px solid color-mix(in srgb,var(--p) 13%,var(--line));
    border-radius:12px;
    background:color-mix(in srgb,var(--p) 3%,var(--surface));
  }
  .v10-field.server{
    grid-column:1/-1;
  }
  .v10-field-label{
    grid-column:1/-1;
    color:var(--muted);
    font-size:7.5px;
    font-weight:800;
    line-height:1.5;
  }
  .v10-field-value{
    min-width:0;
    direction:ltr;
    text-align:left;
    color:var(--text);
    font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace;
    font-size:11px;
    font-weight:850;
    line-height:1.55;
    overflow-wrap:anywhere;
    word-break:break-word;
    user-select:text;
  }
  .v10-field-copy{
    min-height:30px;
    padding:0 8px;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    gap:4px;
    font-size:7px;
  }
}

@media(max-width:340px){
  .v10-credential-grid{grid-template-columns:1fr}
  .v10-field.server{grid-column:auto}
}
"""


_V10_SCRIPT = r"""
<script id="twinpanelPublicConnectManualFieldsV10">
(function(){
  if(!window.matchMedia('(max-width:720px)').matches)return;
  const mount=document.querySelector('.v9-mobile-stack');
  if(!mount)return;
  const toast=document.getElementById('toast');
  const copyIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M5 16H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v1"/></svg>';
  const titles={cisco:'Cisco / OpenConnect',l2tp:'L2TP / IPsec'};
  const labels={
    'Server & Port':'آدرس سرور',
    'Server':'آدرس سرور',
    'Username':'نام کاربری',
    'Password':'رمز عبور',
    'IPsec Secret':'کلید IPsec'
  };

  function notify(text){
    if(!toast)return;
    toast.textContent=text;
    toast.classList.add('show');
    clearTimeout(window.__v10Toast);
    window.__v10Toast=setTimeout(()=>toast.classList.remove('show'),1700);
  }
  async function copyText(value){
    const text=String(value||'');
    if(!text)return false;
    if(navigator.clipboard&&window.isSecureContext){
      try{await navigator.clipboard.writeText(text);return true}catch(_error){}
    }
    const area=document.createElement('textarea');
    area.value=text;
    area.style.position='fixed';
    area.style.opacity='0';
    area.style.pointerEvents='none';
    document.body.appendChild(area);
    area.select();
    let ok=false;
    try{ok=document.execCommand('copy')}catch(_error){}
    area.remove();
    return ok;
  }
  function fieldData(view){
    return [...view.querySelectorAll('.fact')].map(fact=>{
      const rawLabel=(fact.querySelector('small')?.textContent||'').trim();
      const value=(fact.querySelector('strong')?.textContent||'').trim();
      const copyValue=(fact.querySelector('[data-copy]')?.dataset.copy||value).trim();
      return {rawLabel,label:labels[rawLabel]||rawLabel,value,copyValue};
    }).filter(field=>field.value&&field.value!=='—');
  }
  function findCard(title){
    return [...mount.querySelectorAll('.v9-config-card')].find(card=>
      (card.querySelector('.v9-card-title b')?.textContent||'').trim()===title
    );
  }
  function removeLegacyActions(row){
    [...row.children].forEach(child=>{
      if(child.classList.contains('v9-icon-btn')||child.classList.contains('v9-details'))child.remove();
    });
  }
  function makeCopyButton(value,label){
    const button=document.createElement('button');
    button.type='button';
    button.className='v10-field-copy';
    button.innerHTML=copyIcon+'<span>کپی</span>';
    button.setAttribute('aria-label','کپی '+label);
    button.addEventListener('click',async()=>{
      notify(await copyText(value)?label+' کپی شد':'کپی انجام نشد');
    });
    return button;
  }
  function renderFields(row,fields){
    removeLegacyActions(row);
    row.classList.add('v10-manual-row');
    const grid=document.createElement('div');
    grid.className='v10-credential-grid';

    const head=document.createElement('div');
    head.className='v10-grid-head';
    const heading=document.createElement('b');
    heading.textContent='اطلاعات اتصال';
    const copyAll=document.createElement('button');
    copyAll.type='button';
    copyAll.className='v10-copy-all';
    copyAll.innerHTML=copyIcon+'<span>کپی همه</span>';
    copyAll.addEventListener('click',async()=>{
      const text=fields.map(field=>field.label+': '+field.copyValue).join('\n');
      notify(await copyText(text)?'همه اطلاعات کپی شد':'کپی انجام نشد');
    });
    head.append(heading,copyAll);
    grid.appendChild(head);

    fields.forEach(field=>{
      const box=document.createElement('div');
      box.className='v10-field'+(field.rawLabel.startsWith('Server')?' server':'');
      const label=document.createElement('span');
      label.className='v10-field-label';
      label.textContent=field.label;
      const value=document.createElement('code');
      value.className='v10-field-value';
      value.textContent=field.value;
      box.append(label,value,makeCopyButton(field.copyValue,field.label));
      grid.appendChild(box);
    });
    row.appendChild(grid);
  }

  document.querySelectorAll('.protocol-panel').forEach(panel=>{
    const choice=document.querySelector('.protocol-choice[data-protocol="'+CSS.escape(panel.id)+'"]');
    const key=String(choice?.dataset.protocolKey||'').trim().toLowerCase();
    if(key!=='cisco'&&key!=='l2tp')return;
    const card=findCard(titles[key]);
    if(!card)return;
    const views=[...panel.querySelectorAll('.server-view')];
    const rows=[...card.querySelectorAll('.v9-server-row')];
    views.forEach((view,index)=>{
      const row=rows[index];
      if(!row)return;
      const fields=fieldData(view);
      if(fields.length)renderFields(row,fields);
    });
  });
})();
</script>
"""


def refine_public_connection_manual_fields_v10(source: str) -> str:
    """Make Cisco/OpenConnect and L2TP/IPsec credentials readable and individually copyable on phones."""
    if "TWINPANEL_PUBLIC_CONNECT_MANUAL_FIELDS_V10" in source:
        return source
    source = source.replace("</style>", _V10_CSS + "\n</style>", 1)
    source = source.replace("</body>", _V10_SCRIPT + "\n</body>", 1)
    return source
