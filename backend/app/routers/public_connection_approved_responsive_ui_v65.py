from __future__ import annotations

# Presentation-only refiner. It must not fetch or transform the customer's
# subscription payload, raw VPN config, credential, endpoint or server address.
_MARKER = "TWINPANEL_PUBLIC_CONNECT_APPROVED_RESPONSIVE_UI_V65"

_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_APPROVED_RESPONSIVE_UI_V65 */
body.tp65-ready{
  --tp65-purple:#7954ff;--tp65-blue:#3478ff;--tp65-edge:#283452;
  --tp65-glow:0 0 0 1px rgba(131,91,255,.5),0 0 22px rgba(114,64,240,.20);
  background:radial-gradient(ellipse 780px 280px at 86% -18%,rgba(110,48,243,.17),transparent 72%),var(--bg);
}
body.tp65-ready .top{background:rgba(9,13,27,.95);border-bottom:1px solid #26304a}
body.tp65-ready .topin{height:65px}
body.tp65-ready .brand .mark{border-radius:12px;box-shadow:0 7px 22px rgba(104,66,244,.34)}
body.tp65-ready .page{max-width:1200px;padding-top:22px}
body.tp65-ready .traffic{border:1px solid #2b3653;border-radius:21px;background:linear-gradient(120deg,#141c35,#131a32 63%,#21164b);box-shadow:0 10px 38px rgba(2,4,17,.14)}
body.tp65-ready .stat{border-color:#333d61}
body.tp65-ready .section-head{margin:22px 2px 12px}
body.tp65-ready .protocols{grid-template-columns:repeat(4,minmax(0,1fr));gap:11px}
body.tp65-ready .protocol-choice{min-height:75px;padding:12px;border:1px solid #2c395a;border-radius:16px;background:linear-gradient(140deg,#141d32,#11182c);grid-template-columns:43px minmax(0,1fr);gap:11px;transition:border-color .15s,transform .15s,box-shadow .15s}
body.tp65-ready .protocol-choice:hover{border-color:#765cff;transform:translateY(-1px)}
body.tp65-ready .protocol-choice.active,
body.tp65-ready .protocol-choice.v36-active{border-color:#8569ff;box-shadow:var(--tp65-glow)}
body.tp65-ready .protocol-icon{height:42px;width:42px;border-radius:14px;background:linear-gradient(135deg,var(--pc,#765bfa),color-mix(in srgb,var(--pc,#765bfa) 55%,#231354));font-size:17px}
body.tp65-ready .protocol-text b{font-size:12px;line-height:1.45}
body.tp65-ready .protocol-text small{font-size:10px;line-height:1.7}
body.tp65-ready .protocol-choice em{display:none}
body.tp65-ready.v51-multilink .protocol-choice[data-v51-filtered="1"]{display:none!important}
body.tp65-ready .protocol-panel{border:1px solid #443b89;border-radius:22px;background:linear-gradient(170deg,#151b32,#0c1121 60%);overflow:hidden}
body.tp65-ready .panel-head{padding:16px 18px;min-height:75px;background:linear-gradient(90deg,rgba(75,39,153,.27),rgba(29,41,74,.19));border-color:#303957}
body.tp65-ready .panel-head h3{font-size:18px}
body.tp65-ready .server-tabs{gap:8px}
body.tp65-ready .server-tab{min-height:36px;height:auto;padding:8px 11px;border-radius:11px;border:1px solid #364260;background:#18213a;color:#bec7e0;font-size:11px}
body.tp65-ready .server-tab.active{border-color:#8b66ff;background:linear-gradient(135deg,#5136c8,#353cbd);color:white;box-shadow:0 0 13px #775aff42}
body.tp65-ready .server-views{padding:14px}
body.tp65-ready .server-view{border:1px solid #303c57;border-radius:16px;background:linear-gradient(130deg,#171f35,#121a2c);padding:12px}
body.tp65-ready .server-view+.server-view{margin-top:9px}
body.tp65-ready .v52-multi-card{border:1px solid #624ac7!important;background:linear-gradient(130deg,#182043,#231747)!important;border-radius:17px!important;margin:14px!important}
body.tp65-ready .v51-multi-actions>a,
body.tp65-ready .v51-multi-actions>button,
body.tp65-ready .tp65-single-action{border-radius:11px;min-height:42px;font-weight:850;letter-spacing:0}
body.tp65-ready .v51-primary,
body.tp65-ready .tp65-single-add{background:linear-gradient(110deg,#7852fa,#385df1)!important;border:1px solid #9577ff!important;color:white!important;box-shadow:0 6px 20px #6652eb28}
body.tp65-ready .tp65-single-actions{display:flex;gap:8px;align-items:stretch;margin-top:10px}
body.tp65-ready .tp65-single-action{display:inline-flex;align-items:center;justify-content:center;flex:1;min-width:0;padding:9px 12px;background:#1b2540;border:1px solid #3b4968;color:#f3f6ff;text-decoration:none;font:inherit;font-size:12px;cursor:pointer}
body.tp65-ready .tp65-single-action:focus-visible,
body.tp65-ready .protocol-choice:focus-visible{outline:2px solid #b9a5ff;outline-offset:3px}
body.tp65-ready .tp65-single-action[disabled]{opacity:.6;cursor:wait}
body.tp65-ready .tp65-server-caption{font-size:12px;font-weight:850;color:#eff3ff;margin:0 0 6px}
body.tp65-ready .tp65-server-caption:before{content:'●';font-size:8px;margin-inline-end:8px;color:#40dc9b}
body.tp65-ready .v34-server-actions.tp65-replaced{display:none!important}
body.tp65-ready .v54-v2ray-profile{border-radius:13px}
body.tp65-ready .v54-v2ray-profile-actions a,
body.tp65-ready .v54-v2ray-profile-actions button{min-height:40px;border-radius:10px}
@media(min-width:721px){
  body.tp65-ready .protocol-panel .server-views{display:grid;gap:8px}
  body.tp65-ready .protocol-panel .server-view{margin:0}
  body.tp65-ready .protocol-panel[data-v34-modern="1"] .server-view{display:block!important}
}
@media(max-width:1000px) and (min-width:721px){
  body.tp65-ready .protocols{grid-template-columns:repeat(3,minmax(0,1fr))}
}
@media(max-width:720px){
  body.tp65-ready .topin{height:56px}
  body.tp65-ready .brand b{font-size:16px}
  body.tp65-ready .page{width:min(94vw,580px);padding-top:12px}
  body.tp65-ready .traffic{padding:13px;border-radius:16px;gap:10px}
  body.tp65-ready .section-head{margin:13px 2px 8px}
  body.tp65-ready .protocols{grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:6px!important}
  body.tp65-ready.v51-multilink .protocol-choice[data-v51-filtered="1"]{display:none!important}
  body.tp65-ready .protocol-choice{min-height:70px;padding:7px 3px;display:flex!important;flex-direction:column;align-items:center;justify-content:center;gap:5px;border-radius:12px;text-align:center;min-width:0}
  body.tp65-ready .protocol-icon{width:32px;height:32px;border-radius:11px;font-size:14px;flex:0 0 32px}
  body.tp65-ready .protocol-text{min-width:0;width:100%;display:block}
  body.tp65-ready .protocol-text b{font-size:9px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  body.tp65-ready .protocol-text small{display:none}
  body.tp65-ready .v51-mobile-categories{gap:6px;margin:6px 0 10px}
  body.tp65-ready .v51-mobile-category{min-height:36px;border-radius:10px}
  body.tp65-ready .protocol-panel{border-radius:17px;margin-top:12px}
  body.tp65-ready .panel-head{padding:12px;gap:9px}
  body.tp65-ready .panel-head h3{font-size:15px}
  body.tp65-ready .server-tabs{display:flex!important;max-width:100%;overflow:auto;flex-wrap:nowrap;padding:3px 0;scrollbar-width:none}
  body.tp65-ready .server-tabs::-webkit-scrollbar{display:none}
  body.tp65-ready .server-tab{flex:0 0 auto;max-width:none;min-height:35px}
  body.tp65-ready .v52-multi-card{margin:9px!important;padding:11px!important}
  body.tp65-ready .v51-multi-actions{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:7px}
  body.tp65-ready .v51-multi-actions>a,
  body.tp65-ready .v51-multi-actions>button{min-height:42px;padding:8px 9px;font-size:10px}
  body.tp65-ready .server-views{padding:8px!important;gap:8px!important}
  body.tp65-ready .server-view{padding:10px!important;border-radius:13px!important}
  body.tp65-ready .tp65-single-actions{gap:7px}
  body.tp65-ready .tp65-single-action{min-height:43px;font-size:11px;padding:8px}
  body.tp65-ready .v34-mobile-servers{margin:8px}
  body.tp65-ready .v54-v2ray-profile-actions{gap:7px}
  body.tp65-ready .v54-v2ray-profile-actions a,
  body.tp65-ready .v54-v2ray-profile-actions button{min-height:42px}
}
@media(max-width:355px){
  body.tp65-ready .protocol-text b{font-size:8px}
  body.tp65-ready .protocols{gap:4px!important}
}
"""

_SCRIPT = r"""
<script id="twinpanelApprovedResponsiveUIV65">
(function(){
  'use strict';
  if(!/^\/v1\/connect\/[^/]+\/?$/.test(location.pathname))return;
  const toast=message=>{
    const node=document.getElementById('toast');
    if(!node)return;
    node.textContent=message;node.classList.add('show');
    clearTimeout(window.__tp65Toast);
    window.__tp65Toast=setTimeout(()=>node.classList.remove('show'),2400);
  };
  async function copy(raw){
    if(!raw)return false;
    if(navigator.clipboard&&isSecureContext){
      try{await navigator.clipboard.writeText(raw);return true}catch(_error){}
    }
    const area=document.createElement('textarea');
    area.value=raw;area.readOnly=true;area.style.cssText='position:fixed;top:-10000px;left:-10000px';
    document.body.appendChild(area);area.select();
    let ok=false;try{ok=document.execCommand('copy')}catch(_error){}
    area.remove();return ok;
  }
  const validDeep=href=>/^(?:karing|hiddify|v2rayng|v2box|sudoku|trusttunnel):\/\//i.test(href);
  const canonical=(view)=>{
    const source=[...view.querySelectorAll('a[href]')].find(a=>
      validDeep(a.getAttribute('href')||'')&&
      !a.closest('.v34-server-actions,.tp65-single-actions')
    );
    if(source)return {kind:'deep',href:source.getAttribute('href'),source};
    const fromActions=[...view.querySelectorAll('.v34-server-actions a[href]')].find(a=>validDeep(a.getAttribute('href')||''));
    if(fromActions)return {kind:'deep',href:fromActions.getAttribute('href'),source:fromActions};
    // A single-action button may have no working app URI. Use only its already
    // supplied canonical /modern-config path, never fabricate a VPN endpoint.
    const config=view.querySelector('button[data-config-path],a[data-config-path]');
    const path=config?.getAttribute('data-config-path')||'';
    const platform=document.body.dataset.tpPlatform||'';
    const protocol=view.closest('.protocol-panel')?.dataset.v34Protocol||'';
    const supportsKaring=new Set(['hysteria2','tuic','anytls','naive','shadowtls','mieru','sudoku']).has(protocol);
    if(path.startsWith('/v1/connect/')&&platform==='android'&&supportsKaring){
      return {kind:'deep',href:'karing://install-config?url='+
        encodeURIComponent(new URL(path,location.origin).href),source:config};
    }
    return null;
  };
  const copyTarget=view=>{
    for(const node of view.querySelectorAll('[data-copy],[data-tp-copy-target]')){
      const direct=node.getAttribute('data-copy');
      if(direct)return direct;
      const id=node.getAttribute('data-tp-copy-target');
      if(id){
        const target=document.getElementById(id);
        if(target)return String('value' in target?target.value:target.textContent||'').trim();
      }
    }
    return '';
  };
  function action(label,cls){
    const a=document.createElement('a');
    a.className='tp65-single-action '+cls;
    a.textContent=label;
    a.setAttribute('role','link');
    return a;
  }
  function enhance(view){
    if(view.querySelector('.tp65-single-actions'))return;
    if(view.closest('.protocol-panel')?.dataset.v34Protocol==='v2ray')return;
    const original=view.querySelector('.v34-server-actions');
    if(!original)return;
    const direct=canonical(view);
    const stored=copyTarget(view);
    const copyLink=[...original.querySelectorAll('a[href]')].find(a=>
      /^(https?:\/\/|(?:vmess|vless|trojan|ss|hysteria2|hy2|tuic|anytls|naive|snell|mieru|sudoku):\/\/)/i.test(a.getAttribute('href')||'')
    );
    const uri=/^(?:vless|vmess|trojan|ss|hysteria2|hy2|tuic|anytls|naive|snell|mieru|sudoku|trusttunnel|wg|wireguard):\/\//i;
    const fallback=(uri.test(stored)?stored:'')||copyLink?.getAttribute('href')||'';
    if(!direct&&!fallback)return; // Show original controls if no safe replacement.
    const row=document.createElement('div');row.className='tp65-single-actions';
    if(direct){
      const add=action('＋ افزودن به برنامه','tp65-single-add');
      add.href=direct.href;
      add.addEventListener('click',()=>{toast('در حال باز کردن برنامه اتصال…')});
      row.appendChild(add);
    }
    if(fallback){
      const button=document.createElement('button');
      button.type='button';button.className='tp65-single-action';
      button.textContent='⧉ کپی';
      button.addEventListener('click',async()=>{
        button.disabled=true;
        const ok=await copy(fallback);
        toast(ok?'کانفیگ کپی شد ✓':'کپی خودکار ممکن نشد');
        button.disabled=false;
      });
      row.appendChild(button);
    }
    original.insertAdjacentElement('afterend',row);
    original.classList.add('tp65-replaced');
  }
  function apply(){
    document.body.classList.add('tp65-ready');
    document.querySelectorAll('.protocol-panel .server-view').forEach(enhance);
    document.querySelectorAll('.protocol-choice').forEach(choice=>{
      choice.setAttribute('aria-label',choice.textContent.trim());
    });
  }
  apply();
  // Existing V51/V52/V54 scripts build some protocol actions after initial paint.
  let attempts=0;
  const timer=setInterval(()=>{apply();if(++attempts>=12)clearInterval(timer)},250);
})();
</script>
"""

def refine_public_connection_approved_responsive_ui_v65(source: str) -> str:
    """Append responsive customer-only styles and existing-link action UI."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace(
        "</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1,
    )
