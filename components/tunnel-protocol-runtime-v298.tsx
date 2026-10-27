"use client";

import {type FormEvent,useEffect,useMemo,useState} from "react";

import {API_BASE} from "../lib/api";
import type {AdminNode,AdminTunnel} from "../lib/admin-api";
import {getCustomerToken} from "../lib/customer-api";
import {legacyControlApi} from "../lib/legacy-control-api";
import {
  legacyAdminApi,
  type ClassicProtocolInventoryNode,
  type ClassicProtocolInventoryRow,
  type ClassicProtocolKey,
} from "../lib/legacy-admin-api";
import {
  modernTransportApi,
  type ModernProtocolInventory,
  type ModernProtocolInventoryItem,
} from "../lib/modern-transport-api";
import {useI18n} from "../lib/i18n";
import {Badge,Card,Shell,Stat} from "./ui";
import {TunnelServerPairSelectorV293} from "./tunnel-server-pair-selector-v293";
import {TunnelServiceConnectionsPanel} from "./tunnel-service-connections-panel";

// TWINPANEL_TUNNEL_PROTOCOL_MANAGEMENT_V299
// /admin/tunnels owns logical pair + service protocol management.
// Dense fleet UX: one selected tunnel, searchable protocol inventory and collapsed service connections.
// Transport installation, manual cutover and failover remain on /admin/tunnel-transports.

type Draft={iran_node_id:number;exit_node_id:number;priority:number};
type ProtocolScope="installed"|"all"|"issues";
type ModernRow=ModernProtocolInventoryItem&{
  preset?:string;
  settings?:Record<string,unknown>;
};
type ProtocolRow={
  id:string;
  kind:"classic"|"modern";
  protocol:string;
  name:string;
  status:string;
  installed:boolean;
  installable:boolean;
  portText:string;
  transport:string;
  classic?:ClassicProtocolInventoryRow;
  modern?:ModernRow;
};

const CLASSIC_LABELS:Record<ClassicProtocolKey,string>={
  cisco:"Cisco / OpenConnect",
  openvpn:"OpenVPN",
  wireguard:"WireGuard",
  l2tp:"L2TP / IPsec",
  v2ray:"V2Ray / Xray",
};

const HEALTHY_STATUSES=new Set(["online","active","healthy","ok","ready","enabled"]);
const normalize=(value:unknown)=>String(value??"").trim().toLowerCase();
const isHealthyStatus=(value:unknown)=>HEALTHY_STATUSES.has(normalize(value));
const tone=(value:unknown):"ok"|"warn"|"bad"|"violet"=>{
  const status=normalize(value);
  if(HEALTHY_STATUSES.has(status))return "ok";
  if(["offline","failed","error","down"].includes(status))return "bad";
  if(["not_installed","disabled","planned"].includes(status))return "warn";
  return "violet";
};

async function modernRequest<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const base=typeof window!=="undefined"?window.location.origin:API_BASE;
  const response=await fetch(`${base}${path}`,{...init,headers,cache:"no-store"});
  const raw=await response.text();
  let payload:unknown=null;
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
  if(!response.ok){
    if(payload&&typeof payload==="object"&&"detail" in payload){
      const detail=(payload as {detail?:unknown}).detail;
      if(typeof detail==="string")throw new Error(detail);
      if(detail&&typeof detail==="object"&&"message" in detail)throw new Error(String((detail as {message?:unknown}).message||`API error ${response.status}`));
    }
    throw new Error(`API error ${response.status}`);
  }
  return payload as T;
}

function Modal({title,onClose,children}:{title:string;onClose:()=>void;children:React.ReactNode}){
  return <div className="runtime-modal" role="dialog" aria-modal="true">
    <button type="button" className="runtime-modal-bg" aria-label="close" onClick={onClose}/>
    <div className="runtime-modal-card">
      <div className="card-head"><b>{title}</b><button type="button" className="icon-button" onClick={onClose}>×</button></div>
      {children}
    </div>
  </div>;
}

export function TunnelProtocolRuntimeV298(){
  const {pick}=useI18n();
  const [tunnels,setTunnels]=useState<AdminTunnel[]>([]);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [classicNodes,setClassicNodes]=useState<ClassicProtocolInventoryNode[]>([]);
  const [modernInventory,setModernInventory]=useState<ModernProtocolInventory|null>(null);
  const [selectedId,setSelectedId]=useState(0);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [search,setSearch]=useState("");
  const [protocolSearch,setProtocolSearch]=useState("");
  const [protocolScope,setProtocolScope]=useState<ProtocolScope>("installed");
  const [connectionsOpen,setConnectionsOpen]=useState(false);
  const [createOpen,setCreateOpen]=useState(false);
  const [draft,setDraft]=useState<Draft>({iran_node_id:0,exit_node_id:0,priority:100});

  const nodeMap=useMemo(()=>new Map(nodes.map(node=>[node.id,node])),[nodes]);
  const iranNodes=useMemo(()=>nodes.filter(node=>normalize(node.node_type)==="iran"),[nodes]);
  const exitNodes=useMemo(()=>nodes.filter(node=>normalize(node.node_type)==="exit"),[nodes]);
  const selectedTunnel=useMemo(()=>tunnels.find(row=>row.id===selectedId)||null,[tunnels,selectedId]);
  const selectedIran=selectedTunnel?nodeMap.get(selectedTunnel.iran_node_id):undefined;
  const selectedExit=selectedTunnel?nodeMap.get(selectedTunnel.exit_node_id):undefined;

  const filteredTunnels=useMemo(()=>{
    const q=search.trim().toLowerCase();
    if(!q)return tunnels;
    return tunnels.filter(tunnel=>{
      const iran=nodeMap.get(tunnel.iran_node_id);const exit=nodeMap.get(tunnel.exit_node_id);
      return `${tunnel.id} ${tunnel.status||""} ${iran?.name||""} ${iran?.public_ip||""} ${exit?.name||""} ${exit?.public_ip||""}`.toLowerCase().includes(q);
    });
  },[tunnels,nodeMap,search]);

  const protocols=useMemo<ProtocolRow[]>(()=>{
    if(!selectedTunnel)return [];
    const exitId=selectedTunnel.exit_node_id;
    const rows:ProtocolRow[]=[];
    const classic=classicNodes.find(node=>Number(node.id)===Number(exitId));
    for(const item of classic?.protocols||[]){
      rows.push({
        id:`classic:${item.protocol}`,
        kind:"classic",
        protocol:item.protocol,
        name:CLASSIC_LABELS[item.protocol]||item.protocol,
        status:item.enabled?(item.status||"enabled"):"not_installed",
        installed:Boolean(item.enabled),
        installable:true,
        portText:item.port_text||String(item.port??"—"),
        transport:item.transport||"—",
        classic:item,
      });
    }
    const modernNode=(modernInventory?.nodes||[]).find(node=>Number(node.id)===Number(exitId));
    for(const raw of modernNode?.protocols||[]){
      const item=raw as ModernRow;
      rows.push({
        id:`modern:${item.protocol}`,
        kind:"modern",
        protocol:item.protocol,
        name:String(item.name||item.protocol),
        status:String(item.status||item.runtime_status||"not_installed"),
        installed:normalize(item.status)!=="not_installed",
        installable:Boolean(item.installable),
        portText:String(item.port??"—"),
        transport:String(item.transport||"—"),
        modern:item,
      });
    }
    return rows.sort((a,b)=>Number(b.installed)-Number(a.installed)||a.name.localeCompare(b.name));
  },[selectedTunnel,classicNodes,modernInventory]);

  const activeProtocols=protocols.filter(row=>row.installed).length;
  const healthyProtocols=protocols.filter(row=>row.installed&&isHealthyStatus(row.status)).length;
  const issueProtocols=protocols.filter(row=>row.installed&&!isHealthyStatus(row.status)).length;
  const visibleProtocols=useMemo(()=>{
    const q=protocolSearch.trim().toLowerCase();
    return protocols.filter(row=>{
      if(protocolScope==="installed"&&!row.installed)return false;
      if(protocolScope==="issues"&&(!row.installed||isHealthyStatus(row.status)))return false;
      if(!q)return true;
      return `${row.name} ${row.protocol} ${row.status} ${row.portText} ${row.transport}`.toLowerCase().includes(q);
    });
  },[protocols,protocolSearch,protocolScope]);

  const load=async(silent=false,preferredId?:number)=>{
    if(!silent)setLoading(true);
    if(!silent){setError("");setNotice("");}
    const [tunnelResult,nodeResult,classicResult,modernResult]=await Promise.allSettled([
      legacyControlApi.tunnels(),
      legacyControlApi.nodes(),
      legacyAdminApi.classicProtocols(),
      modernTransportApi.protocolInventory(),
    ]);
    if(tunnelResult.status==="fulfilled"){
      setTunnels(tunnelResult.value);
      setSelectedId(current=>{
        if(preferredId&&tunnelResult.value.some(row=>row.id===preferredId))return preferredId;
        if(current&&tunnelResult.value.some(row=>row.id===current))return current;
        return tunnelResult.value[0]?.id||0;
      });
    }
    if(nodeResult.status==="fulfilled")setNodes(nodeResult.value);
    if(classicResult.status==="fulfilled")setClassicNodes(classicResult.value.nodes||[]);
    if(modernResult.status==="fulfilled")setModernInventory(modernResult.value);
    const failures=[tunnelResult,nodeResult,classicResult,modernResult].filter(result=>result.status==="rejected") as PromiseRejectedResult[];
    if(failures.length&&!silent)setError(failures.map(item=>item.reason instanceof Error?item.reason.message:String(item.reason)).join(" · "));
    if(!silent)setLoading(false);
  };

  useEffect(()=>{void load();const timer=window.setInterval(()=>void load(true),15000);return()=>window.clearInterval(timer);},[]);
  useEffect(()=>{setProtocolSearch("");setProtocolScope("installed");setConnectionsOpen(false);},[selectedId]);

  const run=async(key:string,message:string,action:()=>Promise<unknown>)=>{
    if(busy)return;
    setBusy(key);setError("");setNotice("");
    try{await action();setNotice(message);await load(true,selectedId);}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}
  };

  const installClassic=(row:ProtocolRow)=>{
    if(!selectedTunnel||row.kind!=="classic"||!row.classic)return;
    const protocol=row.protocol as ClassicProtocolKey;
    const payload={node_id:selectedTunnel.exit_node_id,protocol,...(protocol==="l2tp"?{}:{port:Number(row.classic.port||0)}),...(protocol==="openvpn"?{transport:(row.classic.transport==="tcp"?"tcp":"udp") as "tcp"|"udp"}:{})};
    void run(`classic-${protocol}`,pick(`${row.name} نصب/Repair و Health Check شد.`,`${row.name} was installed/repaired and health-checked.`),()=>legacyAdminApi.ensureClassicProtocol(payload));
  };

  const installModern=(row:ProtocolRow)=>{
    if(!selectedTunnel||row.kind!=="modern"||!row.modern||!row.installable)return;
    const item=row.modern;
    const protocol=item.protocol;
    const body={
      protocols:[protocol],
      ports:{[protocol]:Number(item.port||0)},
      profiles:{[protocol]:{preset:item.preset||"recommended",settings:{...(item.settings||{})}}},
    };
    void run(`modern-install-${protocol}`,pick(`${row.name} روی Exit همین Tunnel اعمال شد.`,`${row.name} was applied on this tunnel's Exit.`),()=>modernRequest(`/v1/settings/vpn/modern-protocols/${selectedTunnel.exit_node_id}/install`,{method:"POST",body:JSON.stringify(body)}));
  };

  const removeModern=(row:ProtocolRow)=>{
    if(!selectedTunnel||row.kind!=="modern"||!row.modern||!row.installable||!row.installed)return;
    if(!window.confirm(pick(`${row.name} از Exit این Tunnel حذف شود؟`,`Remove ${row.name} from this tunnel's Exit?`)))return;
    void run(`modern-remove-${row.protocol}`,pick(`${row.name} حذف شد.`,`${row.name} was removed.`),()=>modernRequest(`/v1/settings/vpn/modern-protocols/${selectedTunnel.exit_node_id}/${encodeURIComponent(row.protocol)}`,{method:"DELETE"}));
  };

  const createTunnel=async(event:FormEvent)=>{
    event.preventDefault();
    if(busy||!draft.iran_node_id||!draft.exit_node_id)return;
    setBusy("create");setError("");setNotice("");
    try{
      const result=await legacyControlApi.createManagedTunnel({...draft,transport:"auto",is_active:true});
      const id=Number(result?.tunnel?.id||0);if(!id)throw new Error("INVALID_MANAGED_TUNNEL_RESPONSE");
      setCreateOpen(false);await load(true,id);setSelectedId(id);setNotice(pick(`Tunnel #${id} ساخته شد.`,`Tunnel #${id} was created.`));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}
  };

  const toggleTunnel=()=>{if(selectedTunnel)void run(`toggle-${selectedTunnel.id}`,pick("وضعیت Tunnel تغییر کرد.","Tunnel state updated."),()=>legacyControlApi.toggleTunnel(selectedTunnel.id));};
  const deleteTunnel=()=>{
    if(!selectedTunnel||!window.confirm(pick(`Tunnel #${selectedTunnel.id} حذف شود؟`,`Delete tunnel #${selectedTunnel.id}?`)))return;
    const id=selectedTunnel.id;
    void run(`delete-${id}`,pick(`Tunnel #${id} حذف شد.`,`Tunnel #${id} deleted.`),()=>legacyControlApi.deleteTunnel(id)).then(()=>setSelectedId(0));
  };

  const openCreate=()=>{
    const iran=iranNodes.find(node=>normalize(node.status)==="online")||iranNodes[0];
    const exit=exitNodes.find(node=>normalize(node.status)==="online")||exitNodes[0];
    setDraft({iran_node_id:iran?.id||0,exit_node_id:exit?.id||0,priority:100});setCreateOpen(true);
  };

  const openFullProtocolManager=()=>{
    if(!selectedTunnel||typeof window==="undefined")return;
    window.location.href=`/admin/modern-protocols?node=${selectedTunnel.exit_node_id}`;
  };

  return <Shell active="/admin/tunnels">
    <div className="page legacy-control-page">
      <div className="page-head">
        <div><h1>{pick("تانل‌ها و پروتکل‌ها","Tunnels & Protocols")}</h1><small>{pick("یک Tunnel را انتخاب کنید؛ فقط پروتکل‌های همان Exit مدیریت می‌شوند. Transport و Failover در مسیرهای هوشمند باقی می‌ماند.","Select one tunnel; only that Exit's protocols are managed here. Transport/failover remain in Smart Transports.")}</small></div>
        <div className="action-row">
          <button type="button" className="ghost" disabled={loading||Boolean(busy)} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button>
          <TunnelServerPairSelectorV293 disabled={loading||Boolean(busy)} onSelected={tunnel=>{setSelectedId(tunnel.id);void load(true,tunnel.id);}}/>
          <button type="button" className="primary-soft" onClick={()=>{window.location.href="/admin/tunnel-transports";}}>{pick("مسیرهای هوشمند","Smart Transports")}</button>
          <button type="button" className="primary" onClick={openCreate}>＋ {pick("Tunnel جدید","New tunnel")}</button>
        </div>
      </div>

      {error&&<div className="runtime-error">{error}</div>}
      {notice&&<div className="runtime-success">{notice}</div>}

      <div className="stats dashboard-stats">
        <Stat label={pick("کل Tunnelها","Total tunnels")} value={tunnels.length.toLocaleString("fa-IR")} icon="⇄"/>
        <Stat label={pick("نصب‌شده روی Exit انتخابی","Installed on selected Exit")} value={activeProtocols.toLocaleString("fa-IR")} icon="✓"/>
        <Stat label={pick("سالم","Healthy")} value={healthyProtocols.toLocaleString("fa-IR")} icon="●"/>
        <Stat label={pick("نیازمند بررسی","Needs attention")} value={issueProtocols.toLocaleString("fa-IR")} icon="!"/>
      </div>

      <div className="runtime-split-grid">
        <Card>
          <div className="card-head"><div><b>{pick("Tunnelها","Tunnels")}</b><small>{pick("برای ناوگان بزرگ جستجو کنید و فقط یک Pair را مدیریت کنید.","Search large fleets and manage one pair at a time.")}</small></div></div>
          <div className="runtime-toolbar"><label>⌕ <input value={search} onChange={event=>setSearch(event.target.value)} placeholder={pick("نام، IP یا ID...","Name, IP or ID...")}/></label></div>
          <div className="table" style={{maxHeight:"430px",overflow:"auto"}}><table><thead><tr><th>ID</th><th>{pick("مسیر","Pair")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("انتخاب","Select")}</th></tr></thead><tbody>
            {filteredTunnels.map(tunnel=>{const iran=nodeMap.get(tunnel.iran_node_id);const exit=nodeMap.get(tunnel.exit_node_id);return <tr key={tunnel.id}>
              <td>#{tunnel.id}</td><td><div className="user-cell"><b>{iran?.name||`Iran #${tunnel.iran_node_id}`} → {exit?.name||`Exit #${tunnel.exit_node_id}`}</b><small dir="ltr">{iran?.public_ip||"—"} → {exit?.public_ip||"—"}</small></div></td><td><Badge tone={tone(tunnel.status)}>{String(tunnel.status||"—")}</Badge></td><td><button type="button" className={selectedId===tunnel.id?"primary":"primary-soft"} onClick={()=>setSelectedId(tunnel.id)}>{selectedId===tunnel.id?pick("انتخاب‌شده","Selected"):pick("مدیریت","Manage")}</button></td>
            </tr>;})}
            {!loading&&filteredTunnels.length===0&&<tr><td colSpan={4}><div className="runtime-empty">{pick("Tunnel مطابق جستجو پیدا نشد.","No tunnel matches the search.")}</div></td></tr>}
          </tbody></table></div>
        </Card>

        <Card>
          {!selectedTunnel?<div className="runtime-empty">{pick("یک Tunnel را انتخاب کنید.","Select a tunnel.")}</div>:<>
            <div className="card-head"><div><b>Tunnel #{selectedTunnel.id}</b><small>{pick("Pair انتخاب‌شده","Selected pair")}</small></div><Badge tone={tone(selectedTunnel.status)}>{String(selectedTunnel.status||"—")}</Badge></div>
            <div className="runtime-info-list">
              <div><span>Iran</span><b>{selectedIran?.name||`#${selectedTunnel.iran_node_id}`}</b></div>
              <div><span>Exit</span><b>{selectedExit?.name||`#${selectedTunnel.exit_node_id}`}</b></div>
              <div><span>{pick("مسیر فعال","Active transport")}</span><b dir="ltr">{String(selectedTunnel.active_transport||selectedTunnel.preferred_transport||selectedTunnel.transport||"—")}</b></div>
              <div><span>Ping</span><b dir="ltr">{selectedTunnel.latency_ms==null?"—":`${selectedTunnel.latency_ms} ms`}</b></div>
            </div>
            <div className="action-row"><button type="button" className="ghost" disabled={Boolean(busy)} onClick={toggleTunnel}>{selectedTunnel.is_active?pick("غیرفعال کردن","Disable"):pick("فعال کردن","Enable")}</button><button type="button" className="danger" disabled={Boolean(busy)} onClick={deleteTunnel}>{pick("حذف Tunnel","Delete tunnel")}</button></div>
          </>}
        </Card>
      </div>

      {selectedTunnel&&<>
        <Card>
          <div className="card-head">
            <div><b>{pick("پروتکل‌های Tunnel انتخاب‌شده","Selected tunnel protocols")}</b><small>{pick(`Exit ${selectedExit?.name||`#${selectedTunnel.exit_node_id}`} · ${activeProtocols} نصب‌شده از ${protocols.length}`,`Exit ${selectedExit?.name||`#${selectedTunnel.exit_node_id}`} · ${activeProtocols} installed of ${protocols.length}`)}</small></div>
            <div className="action-row"><button type="button" className="primary-soft" onClick={openFullProtocolManager}>{pick("مدیریت کامل","Full manager")}</button></div>
          </div>

          <div className="runtime-toolbar" style={{display:"flex",gap:"10px",alignItems:"center",justifyContent:"space-between",flexWrap:"wrap"}}>
            <label style={{minWidth:"240px",flex:"1 1 280px"}}>⌕ <input value={protocolSearch} onChange={event=>setProtocolSearch(event.target.value)} placeholder={pick("جستجوی پروتکل، پورت یا وضعیت...","Search protocol, port or status...")}/></label>
            <div className="action-row">
              <button type="button" className={protocolScope==="installed"?"primary":"ghost"} onClick={()=>setProtocolScope("installed")}>{pick("نصب‌شده","Installed")} · {activeProtocols}</button>
              <button type="button" className={protocolScope==="issues"?"primary":"ghost"} onClick={()=>setProtocolScope("issues")}>{pick("مشکل‌دار","Issues")} · {issueProtocols}</button>
              <button type="button" className={protocolScope==="all"?"primary":"ghost"} onClick={()=>setProtocolScope("all")}>{pick("همه","All")} · {protocols.length}</button>
            </div>
          </div>

          <div className="table" style={{maxHeight:"520px",overflow:"auto"}}><table><thead><tr><th>{pick("پروتکل","Protocol")}</th><th>{pick("نوع","Type")}</th><th>{pick("پورت","Port")}</th><th>Transport</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>
            {visibleProtocols.map(row=><tr key={row.id}><td><b>{row.name}</b><small style={{display:"block"}} dir="ltr">{row.protocol}</small></td><td>{row.kind==="classic"?pick("کلاسیک","Classic"):pick("مدرن","Modern")}</td><td dir="ltr">{row.portText}</td><td dir="ltr">{row.transport}</td><td><Badge tone={tone(row.status)}>{row.status}</Badge></td><td><div className="action-row">{row.kind==="classic"?<button type="button" className="primary-soft" disabled={Boolean(busy)} onClick={()=>installClassic(row)}>{busy===`classic-${row.protocol}`?"…":row.installed?pick("Repair / Health","Repair / Health"):pick("نصب","Install")}</button>:<><button type="button" className="primary-soft" disabled={Boolean(busy)||!row.installable} onClick={()=>installModern(row)}>{busy===`modern-install-${row.protocol}`?"…":row.installed?pick("اعمال / Repair","Apply / Repair"):pick("افزودن","Add")}</button>{row.installed&&row.installable&&<button type="button" className="danger" disabled={Boolean(busy)} onClick={()=>removeModern(row)}>{pick("حذف","Remove")}</button>}</>}</div></td></tr>)}
            {!loading&&visibleProtocols.length===0&&<tr><td colSpan={6}><div className="runtime-empty">{protocolScope==="issues"?pick("پروتکل نصب‌شده‌ی مشکل‌دار ندارید.","No installed protocol needs attention."):pick("پروتکلی مطابق فیلتر پیدا نشد.","No protocol matches this filter.")}</div></td></tr>}
          </tbody></table></div>
        </Card>

        <Card>
          <div className="card-head">
            <div><b>{pick("اتصال‌های عمومی","Service connections")}</b><small>{pick("برای جلوگیری از شلوغی، فقط هنگام نیاز باز می‌شود.","Collapsed by default to keep large fleets manageable.")}</small></div>
            <button type="button" className={connectionsOpen?"ghost":"primary-soft"} onClick={()=>setConnectionsOpen(value=>!value)}>{connectionsOpen?pick("بستن","Close"):pick("نمایش اتصال‌ها","Show connections")}</button>
          </div>
          {connectionsOpen?<TunnelServiceConnectionsPanel tunnelId={selectedTunnel.id}/>:<div className="runtime-empty">{pick("اتصال‌های این Tunnel مخفی هستند. برای مشاهده روی «نمایش اتصال‌ها» بزنید.","Connections are hidden. Use Show connections when you need them.")}</div>}
        </Card>
      </>}

      {createOpen&&<Modal title={pick("Tunnel جدید","New tunnel")} onClose={()=>!busy&&setCreateOpen(false)}><form className="runtime-form" onSubmit={createTunnel}><label>{pick("نود ایران","Iran node")}<select value={draft.iran_node_id} onChange={event=>setDraft(value=>({...value,iran_node_id:Number(event.target.value)}))}>{iranNodes.map(node=><option key={node.id} value={node.id}>{node.name} · {node.public_ip}</option>)}</select></label><label>{pick("نود خارج","Exit node")}<select value={draft.exit_node_id} onChange={event=>setDraft(value=>({...value,exit_node_id:Number(event.target.value)}))}>{exitNodes.map(node=><option key={node.id} value={node.id}>{node.name} · {node.public_ip}</option>)}</select></label><label>{pick("اولویت","Priority")}<input type="number" value={draft.priority} onChange={event=>setDraft(value=>({...value,priority:Number(event.target.value)||100}))}/></label><div className="action-row"><button type="submit" className="primary" disabled={Boolean(busy)||!draft.iran_node_id||!draft.exit_node_id}>{busy==="create"?"…":pick("ساخت و آماده‌سازی","Create & provision")}</button></div></form></Modal>}
    </div>
  </Shell>;
}
