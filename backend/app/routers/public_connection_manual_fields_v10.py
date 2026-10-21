from __future__ import annotations


_V10_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MANUAL_FIELDS_V10 */
@media(max-width:720px){
  .v10-account-summary{
    margin-bottom:8px;
    padding:9px;
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:7px;
    border:1px solid color-mix(in srgb,var(--p) 16%,var(--line));
    border-radius:13px;
    background:color-mix(in srgb,var(--p) 4%,var(--surface));
  }
  .v10-account-title{
    grid-column:1/-1;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:8px;
    padding:0 1px 2px;
  }
  .v10-account-title b{font-size:9px;font-weight:900}
  .v10-account-title small{color:var(--muted);font-size:7px}
  .v10-account-field{
    min-width:0;
    min-height:58px;
    padding:8px 9px;
    display:grid;
    grid-template-columns:minmax(0,1fr) auto;
    grid-template-rows:auto 1fr;
    align-items:center;
    gap:4px 6px;
    border:1px solid var(--line);
    border-radius:11px;
    background:var(--surface);
  }
  .v10-account-field span{
    grid-column:1/-1;
    color:var(--muted);
    font-size:7px;
    font-weight:800;
  }
  .v10-account-field code{
    min-width:0;
    direction:ltr;
    text-align:left;
    color:var(--text);
    font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace;
    font-size:10.5px;
    font-weight:850;
    overflow:hidden;
    text-overflow:ellipsis;
    white-space:nowrap;
    user-select:text;
  }

  .v9-server-row.v10-manual-row{
    grid-template-columns:minmax(0,1fr) 36px;
    align-items:center;
    gap:7px;
    padding:8px 9px;
  }
  .v10-manual-row > .v9-server-main{
    width:100%;
    min-width:0;
    cursor:pointer;
    user-select:none;
  }
  .v10-manual-row .v9-server-copy small{
    direction:ltr;
    text-align:left;
    font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace;
    font-size:7px;
  }
  .v10-expand{
    width:36px;
    height:36px;
    display:grid;
    place-items:center;
    border:1px solid color-mix(in srgb,var(--p) 28%,var(--line));
    border-radius:10px;
    background:color-mix(in srgb,var(--p) 7%,var(--surface));
    color:var(--p);
    cursor:pointer;
  }
  .v10-expand svg{
    width:16px;
    height:16px;
    display:block;
    transition:transform .2s ease;
  }
  .v10-manual-row.open .v10-expand svg{transform:rotate(180deg)}
  .v10-server-details{
    grid-column:1/-1;
    display:none;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:7px;
    padding-top:2px;
    direction:rtl;
  }
  .v10-manual-row.open .v10-server-details{display:grid}
  .v10-server-head{
    grid-column:1/-1;
    min-height:28px;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:8px;
    padding:0 1px;
  }
  .v10-server-head b{font-size:8.5px;font-weight:900}
  .v10-server-head small{color:var(--muted);font-size:7px}
  .v10-field{
    min-width:0;
    min-height:58px;
    padding:8px 9px;
    display:grid;
    grid-template-columns:minmax(0,1fr) auto;
    grid-template-rows:auto 1fr;
    align-items:center;
    gap:4px 6px;
    border:1px solid color-mix(in srgb,var(--p) 13%,var(--line));
    border-radius:11px;
    background:color-mix(in srgb,var(--p) 3%,var(--surface));
  }
  .v10-field.server{grid-column:1/-1}
  .v10-field-label{
    grid-column:1/-1;
    color:var(--muted);
    font-size:7px;
    font-weight:800;
    line-height:1.5;
  }
  .v10-field-value{
    min-width:0;
    direction:ltr;
    text-align:left;
    color:var(--text);
    font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace;
    font-size:10.5px;
    font-weight:850;
    line-height:1.55;
    overflow-wrap:anywhere;
    word-break:break-word;
    user-select:text;
  }
  .v10-field-copy{
    min-height:29px;
    padding:0 8px;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    gap:4px;
    border:1px solid color-mix(in srgb,var(--p) 28%,var(--line));
    border-radius:9px;
    background:color-mix(in srgb,var(--p) 7%,var(--surface));
    color:var(--p);
    font-family:inherit;
    font-size:7px;
    font-weight:900;
    cursor:pointer;
  }
  .v10-field-copy svg{
    width:13px;
    height:13px;
    display:block;
    flex:0 0 13px;
  }
}

@media(max-width:340px){
  .v10-account-summary,
  .v10-server-details{grid-template-columns:1fr}
  .v10-account-title,
  .v10-server-head,
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
  const chevronIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>';
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
  function findField(fields,name){
    return fields.find(field=>field.rawLabel===name)||null;
  }
  function serverField(fields){
    return fields.find(field=>field.rawLabel==='Server & Port'||field.rawLabel==='Server')||null;
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
    button.addEventListener('click',async event=>{
      event.stopPropagation();
      notify(await copyText(value)?label+' کپی شد':'کپی انجام نشد');
    });
    return button;
  }
  function accountBox(field){
    const box=document.createElement('div');
    box.className='v10-account-field';
    const label=document.createElement('span');
    label.textContent=field.label;
    const value=document.createElement('code');
    value.textContent=field.value;
    box.append(label,value,makeCopyButton(field.copyValue,field.label));
    return box;
  }
  function renderAccountSummary(card,fieldSets){
    const username=fieldSets.map(fields=>findField(fields,'Username')).find(Boolean);
    const password=fieldSets.map(fields=>findField(fields,'Password')).find(Boolean);
    if(!username&&!password)return;
    const body=card.querySelector('.v9-card-body');
    const list=card.querySelector('.v9-server-list');
    if(!body||!list||body.querySelector('.v10-account-summary'))return;

    const summary=document.createElement('section');
    summary.className='v10-account-summary';
    const title=document.createElement('div');
    title.className='v10-account-title';
    title.innerHTML='<b>اطلاعات حساب</b><small>برای همه سرورهای زیر</small>';
    summary.appendChild(title);
    if(username)summary.appendChild(accountBox(username));
    if(password)summary.appendChild(accountBox(password));
    body.insertBefore(summary,list);
  }
  function collapseSiblings(row){
    const list=row.closest('.v9-server-list');
    if(!list)return;
    list.querySelectorAll('.v10-manual-row.open').forEach(other=>{
      if(other===row)return;
      other.classList.remove('open');
      other.querySelector('.v10-expand')?.setAttribute('aria-expanded','false');
    });
  }
  function toggleRow(row){
    const willOpen=!row.classList.contains('open');
    if(willOpen)collapseSiblings(row);
    row.classList.toggle('open',willOpen);
    row.querySelector('.v10-expand')?.setAttribute('aria-expanded',willOpen?'true':'false');
  }
  function renderServerRow(row,fields){
    removeLegacyActions(row);
    row.classList.add('v10-manual-row');

    const server=serverField(fields);
    const psk=findField(fields,'IPsec Secret');
    const main=row.querySelector('.v9-server-main');
    if(main){
      const subtitle=main.querySelector('.v9-server-copy small');
      if(subtitle&&server)subtitle.textContent=server.value;
      main.setAttribute('role','button');
      main.setAttribute('tabindex','0');
      main.setAttribute('aria-label','نمایش اطلاعات این سرور');
      main.addEventListener('click',()=>toggleRow(row));
      main.addEventListener('keydown',event=>{
        if(event.key==='Enter'||event.key===' '){
          event.preventDefault();
          toggleRow(row);
        }
      });
    }

    const expand=document.createElement('button');
    expand.type='button';
    expand.className='v10-expand';
    expand.innerHTML=chevronIcon;
    expand.setAttribute('aria-label','نمایش اطلاعات سرور');
    expand.setAttribute('aria-expanded','false');
    expand.addEventListener('click',event=>{
      event.stopPropagation();
      toggleRow(row);
    });
    row.appendChild(expand);

    const details=document.createElement('div');
    details.className='v10-server-details';
    const head=document.createElement('div');
    head.className='v10-server-head';
    head.innerHTML='<b>اطلاعات این سرور</b><small>برای مشاهده و کپی</small>';
    details.appendChild(head);

    [server,psk].filter(Boolean).forEach(field=>{
      const box=document.createElement('div');
      box.className='v10-field'+(field.rawLabel.startsWith('Server')?' server':'');
      const label=document.createElement('span');
      label.className='v10-field-label';
      label.textContent=field.label;
      const value=document.createElement('code');
      value.className='v10-field-value';
      value.textContent=field.value;
      box.append(label,value,makeCopyButton(field.copyValue,field.label));
      details.appendChild(box);
    });
    row.appendChild(details);
  }

  document.querySelectorAll('.protocol-panel').forEach(panel=>{
    const choice=document.querySelector('.protocol-choice[data-protocol="'+CSS.escape(panel.id)+'"]');
    const key=String(choice?.dataset.protocolKey||'').trim().toLowerCase();
    if(key!=='cisco'&&key!=='l2tp')return;
    const card=findCard(titles[key]);
    if(!card)return;
    const views=[...panel.querySelectorAll('.server-view')];
    const rows=[...card.querySelectorAll('.v9-server-row')];
    const fieldSets=views.map(fieldData);
    renderAccountSummary(card,fieldSets);
    fieldSets.forEach((fields,index)=>{
      const row=rows[index];
      if(row&&fields.length)renderServerRow(row,fields);
    });
  });
})();
</script>
"""


def refine_public_connection_manual_fields_v10(source: str) -> str:
    """Keep shared Cisco/L2TP account credentials once, then render compact expandable server rows on phones."""
    if "TWINPANEL_PUBLIC_CONNECT_MANUAL_FIELDS_V10" in source:
        return source
    source = source.replace("</style>", _V10_CSS + "\n</style>", 1)
    source = source.replace("</body>", _V10_SCRIPT + "\n</body>", 1)
    return source
