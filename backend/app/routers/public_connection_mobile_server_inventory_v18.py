from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Node, NodeProtocolConfig, NodeType, SubscriptionProtocol
from .account_delivery import _public_payload, _subscription_from_share_token
from .public_connection_modern_delivery_v13 import MODERN_PROTOCOLS, _items, _status_value
from .public_connection_modern_delivery_v16 import router as _modern_delivery_v16_router


_MARKER = "TWINPANEL_PUBLIC_CONNECT_MOBILE_SERVER_INVENTORY_V18"


_inventory_router = APIRouter(tags=["public-connection-mobile-server-inventory-v18"])


_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_MOBILE_SERVER_INVENTORY_V18 */
@media(max-width:720px){
  .v17-server-row.v18-not-ready{opacity:.72}
  .v18-state{
    min-height:30px;
    padding:0 8px;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    border:1px dashed var(--line);
    border-radius:9px;
    color:var(--muted);
    font-size:6.5px;
    font-weight:900;
    white-space:nowrap;
  }
  .v18-copy-action{border-color:color-mix(in srgb,var(--p) 34%,var(--line))}
}
"""


_SCRIPT = r"""
<script id="twinpanelPublicConnectMobileServerInventoryV18">
(function(){
  function normalize(value){
    const key=String(value||'').trim().toLowerCase();
    if(key==='naiveproxy')return'naive';
    if(key==='openconnect'||key==='ocserv'||key==='anyconnect')return'cisco';
    return key;
  }
  function text(el){return String(el?.textContent||'').trim()}
  function choiceFor(panel){
    return [...document.querySelectorAll('.protocol-choice')]
      .find(choice=>choice.dataset.protocol===panel.id)||null;
  }
  function protocolFor(panel){
    return normalize(choiceFor(panel)?.dataset.protocolKey||panel.dataset.modernProtocol||'');
  }
  function originalPanels(){
    const result=[];
    const seen=new Set();
    document.querySelectorAll('.protocol-panel').forEach(panel=>{
      const key=protocolFor(panel);
      if(!key||seen.has(key))return;
      seen.add(key);result.push(panel);
    });
    document.querySelectorAll('.v13-pending-panel[data-modern-protocol]').forEach(panel=>{
      const key=protocolFor(panel);
      if(!key||seen.has(key))return;
      seen.add(key);result.push(panel);
    });
    return result;
  }
  function facts(view){
    return [...view.querySelectorAll('.fact')].map(fact=>{
      const label=text(fact.querySelector('small'));
      const value=text(fact.querySelector('strong'));
      return label&&value?label+': '+value:'';
    }).filter(Boolean).join('\n');
  }
  function valueFromTarget(id){
    const el=document.getElementById(String(id||''));
    if(!el)return'';
    return String('value' in el?el.value:el.textContent||'');
  }
  function copyPayload(view){
    const target=view.querySelector('[data-tp-copy-target]');
    if(target){
      const value=valueFromTarget(target.dataset.tpCopyTarget);
      if(value)return{value,label:'کپی کانفیگ'};
    }
    const direct=view.querySelector('.copy-btn[data-copy]');
    if(direct&&String(direct.dataset.copy||'').trim()){
      return{value:String(direct.dataset.copy||''),label:'کپی کانفیگ'};
    }
    const download=view.querySelector('.download-config[data-target]');
    if(download){
      const value=valueFromTarget(download.dataset.target);
      if(value)return{value,label:'کپی کانفیگ'};
    }
    const open=view.querySelector('a.v13-open-uri[href],a.primary-btn[href]');
    const href=String(open?.getAttribute('href')||'').trim();
    if(/^(vmess|vless|trojan|ss|hysteria2|hy2|tuic|anytls|sudoku|karing):/i.test(href)){
      return{value:href,label:'کپی کانفیگ'};
    }
    const detail=facts(view);
    return detail?{value:detail,label:'کپی اطلاعات'}:null;
  }
  function fallbackCopy(value){
    const area=document.createElement('textarea');
    area.value=String(value||'');
    area.setAttribute('readonly','');
    area.style.position='fixed';area.style.left='-9999px';area.style.top='0';
    document.body.appendChild(area);area.focus();area.select();
    area.setSelectionRange(0,area.value.length);
    let ok=false;try{ok=document.execCommand('copy')}catch(_error){}
    area.remove();return ok;
  }
  async function copy(value){
    const raw=String(value||'');
    if(!raw)return false;
    if(navigator.clipboard&&window.isSecureContext){
      try{await navigator.clipboard.writeText(raw);return true}catch(_error){}
    }
    return fallbackCopy(raw);
  }
  function notify(message){
    const toast=document.getElementById('toast');
    if(!toast)return;
    toast.textContent=message;toast.classList.add('show');
    clearTimeout(window.__tpV18Toast);
    window.__tpV18Toast=setTimeout(()=>toast.classList.remove('show'),1800);
  }
  function modernNodeId(view){
    const modern=view.querySelector('.v13-modern-action');
    if(!modern)return'';
    const source=modern.querySelector('[data-config-path],a[href*="/modern-config"]');
    const raw=String(source?.dataset?.configPath||source?.getAttribute?.('href')||'');
    const match=raw.match(/\/modern-config(?:-v\d+)?\/[^/?#]+\/(\d+)/i);
    return match?match[1]:'';
  }
  function ensureDetails(view,row){
    const detailText=facts(view);
    if(!detailText)return;
    let detail=row.querySelector('.v17-details');
    if(!detail){
      detail=document.createElement('div');
      detail.className='v17-details';detail.textContent=detailText;
      row.appendChild(detail);
    }
    const actions=row.querySelector('.v17-server-actions');
    if(!actions)return;
    let button=[...actions.querySelectorAll('button')].find(item=>text(item)==='جزئیات');
    if(!button){
      button=document.createElement('button');
      button.type='button';button.className='v17-action';button.textContent='جزئیات';
      actions.appendChild(button);
    }
    if(button.dataset.v18Bound!=='1'){
      button.dataset.v18Bound='1';
      button.addEventListener('click',()=>row.classList.toggle('show-details'));
    }
  }
  function ensureCopy(view,row){
    const payload=copyPayload(view);
    if(!payload)return;
    const actions=row.querySelector('.v17-server-actions');
    if(!actions||actions.querySelector('.v18-copy-action'))return;
    const button=document.createElement('button');
    button.type='button';button.className='v17-action v18-copy-action';
    button.textContent=payload.label;
    button.addEventListener('click',async()=>{
      notify(await copy(payload.value)?'کپی شد ✓':'کپی انجام نشد');
    });
    actions.insertBefore(button,actions.firstChild);
  }
  function pendingMessage(status){
    const value=String(status||'').toLowerCase();
    if(value==='online')return'کانفیگ این سرور هنوز آماده نشده';
    if(value)return'این سرور فعلاً آماده اتصال نیست';
    return'پروتکل روی این سرور هنوز آماده نشده';
  }
  function appendMissingModernServers(card,key,inventory){
    const protocol=inventory.protocols?.[key];
    const nodes=Array.isArray(inventory.nodes)?inventory.nodes:[];
    if(!protocol||!nodes.length)return;

    let list=card.querySelector('.v17-server-list');
    if(!list){
      card.querySelector('.v17-pending')?.remove();
      list=document.createElement('div');list.className='v17-server-list';
      card.querySelector('.v17-body')?.appendChild(list);
    }
    const existing=new Set(
      [...list.querySelectorAll('.v17-server-row[data-node-id]')]
        .map(row=>String(row.dataset.nodeId||''))
        .filter(Boolean)
    );
    const ready=new Set((protocol.ready_node_ids||[]).map(String));
    nodes.forEach((node,index)=>{
      const id=String(node.id||'');
      if(!id||existing.has(id))return;
      const row=document.createElement('div');
      row.className='v17-server-row v18-not-ready';row.dataset.nodeId=id;
      const copyBox=document.createElement('div');copyBox.className='v17-server-copy';
      const name=document.createElement('b');name.textContent=String(node.name||('Server '+(index+1)));
      const note=document.createElement('small');note.textContent=pendingMessage(protocol.node_status?.[id]);
      copyBox.append(name,note);
      const state=document.createElement('span');state.className='v18-state';state.textContent='آماده‌سازی';
      row.append(copyBox,state);list.appendChild(row);
    });

    const total=nodes.length;
    const readyCount=ready.size;
    const count=card.querySelector('.v17-count');
    const subtitle=card.querySelector('.v17-title small');
    if(count)count.textContent=readyCount>=total?total+' سرور':readyCount+' آماده از '+total+' سرور';
    if(subtitle){
      subtitle.textContent=readyCount>=total?'آماده اتصال':readyCount?'بخشی از سرورها آماده‌اند':'در حال آماده‌سازی';
    }
  }
  function patch(inventory){
    if(!window.matchMedia('(max-width:720px)').matches)return;
    const cards=[...document.querySelectorAll('.v17-protocol-card')];
    if(!cards.length)return;
    const panels=originalPanels();

    cards.forEach((card,index)=>{
      const panel=panels[index];
      if(!panel)return;
      const key=protocolFor(panel);
      card.dataset.protocolKey=key;
      const views=[...panel.querySelectorAll('.server-view')];
      const rows=[...card.querySelectorAll('.v17-server-list>.v17-server-row:not(.v18-not-ready)')];
      views.forEach((view,rowIndex)=>{
        const row=rows[rowIndex];
        if(!row)return;
        const nodeId=modernNodeId(view);
        if(nodeId)row.dataset.nodeId=nodeId;
        ensureCopy(view,row);
        ensureDetails(view,row);
      });
      if(inventory.modern_protocols?.includes(key))appendMissingModernServers(card,key,inventory);
    });
    document.body.dataset.tpMobileV18='ready';
  }
  async function inventory(){
    const segment=String(location.pathname.split('/')[3]||'');
    if(!segment)return{nodes:[],modern_protocols:[],protocols:{}};
    try{
      const response=await fetch('/v1/connect/'+segment+'/mobile-server-inventory-v18',{
        cache:'no-store',headers:{Accept:'application/json'}
      });
      if(!response.ok)throw new Error('inventory');
      return await response.json();
    }catch(_error){
      return{nodes:[],modern_protocols:[],protocols:{}};
    }
  }

  window.setTimeout(async()=>patch(await inventory()),20);
})();
</script>
"""


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _inventory(token: str, db: Session) -> dict[str, Any]:
    sub = _subscription_from_share_token(token, db)
    nodes = (
        db.query(Node)
        .filter(
            Node.node_type == NodeType.EXIT,
            Node.retired_at.is_(None),
        )
        .order_by(Node.id.asc())
        .all()
    )
    node_ids = [int(node.id) for node in nodes]
    selected = {
        str(row.protocol or "").strip().lower()
        for row in (
            db.query(SubscriptionProtocol)
            .filter(SubscriptionProtocol.subscription_id == int(sub.id))
            .all()
        )
    }
    wanted = [protocol for protocol in MODERN_PROTOCOLS if protocol in selected]

    payload = _public_payload(db, sub) if _status_value(sub) == "active" else {"credentials": []}
    ready: dict[str, set[int]] = {protocol: set() for protocol in wanted}
    credentials = payload.get("credentials") if isinstance(payload, dict) else []
    for cred in credentials if isinstance(credentials, list) else []:
        if not isinstance(cred, dict):
            continue
        protocol = str(cred.get("protocol") or "").strip().lower()
        if protocol not in ready:
            continue
        for item in _items(cred):
            try:
                node_id = int(item.get("node_id") or 0)
            except (TypeError, ValueError):
                node_id = 0
            if node_id > 0:
                ready[protocol].add(node_id)

    status: dict[str, dict[str, str]] = {protocol: {} for protocol in wanted}
    if node_ids and wanted:
        rows = (
            db.query(NodeProtocolConfig)
            .filter(
                NodeProtocolConfig.node_id.in_(node_ids),
                NodeProtocolConfig.protocol.in_(wanted),
            )
            .all()
        )
        for row in rows:
            protocol = str(row.protocol or "").strip().lower()
            if protocol in status:
                status[protocol][str(int(row.node_id))] = _enum_value(row.status)

    return {
        "nodes": [
            {"id": int(node.id), "name": str(node.name or f"Server {node.id}")}
            for node in nodes
        ],
        "modern_protocols": wanted,
        "protocols": {
            protocol: {
                "ready_node_ids": sorted(ready.get(protocol, set())),
                "node_status": status.get(protocol, {}),
            }
            for protocol in wanted
        },
    }


@_inventory_router.get("/{token}/mobile-server-inventory-v18")
def public_mobile_server_inventory_v18(
    token: str,
    db: Session = Depends(get_db),
):
    """Return non-secret all-Exit readiness for the public phone connection page."""
    return _inventory(token, db)


# V16's router is already included by public_connection_hub_live_v5. Registering
# this read-only refinement route here keeps V18 additive and avoids a second
# public router include in the hub.
_modern_delivery_v16_router.include_router(_inventory_router)


def refine_public_connection_mobile_server_inventory_v18(source: str) -> str:
    """Patch V17 phone cards with copy/details and truthful all-Exit readiness."""
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    source = source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
    return source
