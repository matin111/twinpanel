"use client";

import {type FormEvent,type ReactNode,useEffect,useMemo,useState} from "react";

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
import styles from "./tunnel-protocol-runtime-v307.module.css";

// TWINPANEL_TUNNEL_MANAGEMENT_POPUP_V307
// Keep /admin/tunnels compact: tunnel cards stay on the page while detailed
// protocol/service management lives in a dedicated modal for the selected pair.

type Draft={iran_node_id:number;exit_node_id:number;priority:number};
type ModernRow=ModernProtocolInventoryItem&{preset?:string;settings?:Record<string,unknown>};
type ProtocolRow={
  id:string;kind:"classic"|"modern";protocol:string;name:string;status:string;
  installed:boolean;installable:boolean;portText:string;transport:string;
  classic?:ClassicProtocolInventoryRow;modern?:ModernRow;
};

const CLASSIC_LABELS:Record<ClassicProtocolKey,string>={
  cisco:"Cisco / OpenConnect",openvpn:"OpenVPN",wireguard:"WireGuard",l2tp:"L2TP / IPsec",v2ray:"V2Ray / Xray",
};
const normalize=(value:unknown)=>String(value??"").trim().toLowerCase();
const tone=(value:unknown):"ok"|"warn"|"bad"|"violet"=>{
  const status=normalize(value);
  if(["online","active","healthy","ok","ready","enabled"].includes(status))return "ok";
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

function Modal({title,onClose,children,wide=false}:{title:string;onClose:()=>void;children:ReactNode;wide?:boolean}){
  return <div className="runtime-modal" role="dialog" aria-modal="true" aria-label={title}>
    <button type="button" className="runtime-modal-bg" aria-label="close" onClick={onClose}/>
    <div className={wide?`runtime-modal-card ${styles.modalCard}`:"runtime-modal-card"}>
      {wide?children:<><div className="card-head"><b>{title}</b><button type="button" className="icon-button" onClick={onClose}>×</button></div>{children}</>}
    </div>
  </div>;
}

export function TunnelProtocolRuntimeV307(){
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
  const [createOpen,setCreateOpen]=useState(false);
  const [manageOpen,setManageOpen]=useState(false);
  const [draft,setDraft]=useState<Draft>({iran_node_id:0,exit_node_id:0,priority:100});

  const nodeMap=useMemo(()=>new Map(nodes.map(node=>[node.id,node])),[nodes]);
  const iranNodes=useMemo(()=>nodes.filter(node=>normalize(node.node_type)==="iran"),[nodes]);
  const exitNodes=useMemo(()=>nodes.filter(node=>normalize(node.node_type)==="exit"),[nodes]);
  // TWINPANEL_NEW_NODE_TUNNEL_READINESS_V357
  // Online is the UI eligibility gate; backend SSH/Agent/Fabric preflight remains authoritative.
  const readyIranNodes=useMemo(()=>iranNodes.filter(node=>normalize(node.status)==="online"),[iranNodes]);
  const readyExitNodes=useMemo(()=>exitNodes.filter(node=>normalize(node.status)==="online"),[exitNodes]);
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
    const rows:ProtocolRow[]=[];
    const classic=classicNodes.find(node=>Number(node.id)===Number(selectedTunnel.exit_node_id));
    for(const item of classic?.protocols||[]){
      rows.push({id:`classic:${item.protocol}`,kind:"classic",protocol:item.protocol,name:CLASSIC_LABELS[item.protocol]||item.protocol,status:item.enabled?(item.status||"enabled"):"not_installed",installed:Boolean(item.enabled),installable:true,portText:item.port_text||String(item.port??"—"),transport:item.transport||"—",classic:item});
    }
    const modernNode=(modernInventory?.nodes||[]).find(node=>Number(node.id)===Number(selectedTunnel.exit_node_id));
    for(const raw of modernNode?.protocols||[]){
      const item=raw as ModernRow;
      rows.push({id:`modern:${item.protocol}`,kind:"modern",protocol:item.protocol,name:String(item.name||item.protocol),status:String(item.status||item.runtime_status||"not_installed"),installed:normalize(item.status)!=="not_installed",installable:Boolean(item.installable),portText:String(item.port??"—"),transport:String(item.transport||"—"),modern:item});
    }
    return rows.sort((a,b)=>Number(b.installed)-Number(a.installed)||a.name.localeCompare(b.name));
  },[selectedTunnel,classicNodes,modernInventory]);

  const activeProtocols=protocols.filter(row=>row.installed).length;
  const healthyProtocols=protocols.filter(row=>["online","active","healthy","ok","enabled"].includes(normalize(row.status))).length;

  const load=async(silent=false,preferredId?:number)=>{
    if(!silent)setLoading(true);
    if(!silent){setError("");setNotice("");}
    const [tunnelResult,nodeResult,classicResult,modernResult]=await Promise.allSettled([
      legacyControlApi.tunnels(),legacyControlApi.nodes(),legacyAdminApi.classicProtocols(),modernTransportApi.protocolInventory(),
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
  useEffect(()=>{
    if(!manageOpen&&!createOpen)return;
    const previous=document.body.style.overflow;document.body.style.overflow="hidden";
    const onKey=(event:KeyboardEvent)=>{if(event.key!=="Escape"||busy)return;if(manageOpen)setManageOpen(false);else setCreateOpen(false);};
    window.addEventListener("keydown",onKey);
    return()=>{document.body.style.overflow=previous;window.removeEventListener("keydown",onKey);};
  },[manageOpen,createOpen,busy]);
  useEffect(()=>{if(manageOpen&&!selectedTunnel)setManageOpen(false);},[manageOpen,selectedTunnel]);

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
    const item=row.modern;const protocol=item.protocol;
    const body={protocols:[protocol],ports:{[protocol]:Number(item.port||0)},profiles:{[protocol]:{preset:item.preset||"recommended",settings:{...(item.settings||{})}}}};
    void run(`modern-install-${protocol}`,pick(`${row.name} روی Exit همین Tunnel اعمال شد.`,`${row.name} was applied on this tunnel's Exit.`),()=>modernRequest(`/v1/settings/vpn/modern-protocols/${selectedTunnel.exit_node_id}/install`,{method:"POST",body:JSON.stringify(body)}));
  };
  const removeModern=(row:ProtocolRow)=>{
    if(!selectedTunnel||row.kind!=="modern"||!row.modern||!row.installable||!row.installed)return;
    if(!window.confirm(pick(`${row.name} از Exit این Tunnel حذف شود؟`,`Remove ${row.name} from this tunnel's Exit?`)))return;
    void run(`modern-remove-${row.protocol}`,pick(`${row.name} حذف شد.`,`${row.name} was removed.`),()=>modernRequest(`/v1/settings/vpn/modern-protocols/${selectedTunnel.exit_node_id}/${encodeURIComponent(row.protocol)}`,{method:"DELETE"}));
  };

  const createTunnel=async(event:FormEvent)=>{
    event.preventDefault();if(busy||!draft.iran_node_id||!draft.exit_node_id)return;
    if(!readyIranNodes.some(node=>node.id===draft.iran_node_id)||!readyExitNodes.some(node=>node.id===draft.exit_node_id)){
      setError(pick("برای ساخت Tunnel هر دو نود ایران و خارج باید Online و آماده باشند.","Both Iran and Exit nodes must be online and ready before creating a tunnel."));
      return;
    }
    setBusy("create");setError("");setNotice("");
    try{
      const result=await legacyControlApi.createManagedTunnel({...draft,transport:"auto",is_active:true});
      const id=Number(result?.tunnel?.id||0);if(!id)throw new Error("INVALID_MANAGED_TUNNEL_RESPONSE");
      setCreateOpen(false);await load(true,id);setSelectedId(id);setManageOpen(true);setNotice(pick(`Tunnel #${id} ساخته شد.`,`Tunnel #${id} was created.`));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}
  };
  const toggleTunnel=()=>{if(selectedTunnel)void run(`toggle-${selectedTunnel.id}`,pick("وضعیت Tunnel تغییر کرد.","Tunnel state updated."),()=>legacyControlApi.toggleTunnel(selectedTunnel.id));};
  const deleteTunnel=()=>{
    if(!selectedTunnel||!window.confirm(pick(`Tunnel #${selectedTunnel.id} حذف شود؟`,`Delete tunnel #${selectedTunnel.id}?`)))return;
    const id=selectedTunnel.id;
    void run(`delete-${id}`,pick(`Tunnel #${id} حذف شد.`,`Tunnel #${id} deleted.`),()=>legacyControlApi.deleteTunnel(id)).then(()=>{setManageOpen(false);setSelectedId(0);});
  };
  const openCreate=()=>{
    const iran=readyIranNodes[0];
    const exit=readyExitNodes[0];
    if(!iran||!exit){
      setError(pick("برای ساخت Tunnel حداقل یک نود ایران و یک نود خارج Online لازم است.","At least one online Iran node and one online Exit node are required to create a tunnel."));
      return;
    }
    setDraft({iran_node_id:iran.id,exit_node_id:exit.id,priority:100});setCreateOpen(true);
  };
  const openManage=(id:number)=>{setSelectedId(id);setManageOpen(true);};
  const openFullProtocolManager=()=>{if(selectedTunnel&&typeof window!=="undefined")window.location.href=`/admin/modern-protocols?node=${selectedTunnel.exit_node_id}`;};

  return <Shell active="/admin/tunnels">
    <div className="page legacy-control-page">
      <div className="page-head">
        <div><h1>{pick("تانل‌ها و پروتکل‌ها","Tunnels & Protocols")}</h1><small>{pick("نمای اصلی فقط وضعیت Pairها را نشان می‌دهد؛ مدیریت کامل هر Tunnel داخل پنجره جدا باز می‌شود.","The main view stays compact; full tunnel management opens in a dedicated dialog.")}</small></div>
        <div className="action-row">
          <button type="button" className="ghost" disabled={loading||Boolean(busy)} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button>
          <TunnelServerPairSelectorV293 disabled={loading||Boolean(busy)} onSelected={tunnel=>{setSelectedId(tunnel.id);setManageOpen(true);void load(true,tunnel.id);}}/>
          <button type="button" className="primary-soft" onClick={()=>{window.location.href="/admin/tunnel-transports";}}>{pick("مسیرهای هوشمند","Smart Transports")}</button>
          <button type="button" className="primary" disabled={loading||Boolean(busy)||readyIranNodes.length===0||readyExitNodes.length===0} title={readyIranNodes.length===0||readyExitNodes.length===0?pick("ابتدا یک نود ایران و یک نود خارج را Online کنید.","Bring one Iran node and one Exit node online first."):undefined} onClick={openCreate}>＋ {pick("Tunnel جدید","New tunnel")}</button>
        </div>
      </div>

      {error&&<div className="runtime-error">{error}</div>}
      {notice&&<div className="runtime-success">{notice}</div>}

      <div className="stats dashboard-stats">
        <Stat label={pick("کل Tunnelها","Total tunnels")} value={tunnels.length.toLocaleString("fa-IR")} icon="⇄"/>
        <Stat label={pick("پروتکل‌های انتخاب‌شده","Selected protocols")} value={protocols.length.toLocaleString("fa-IR")} icon="◫"/>
        <Stat label={pick("نصب‌شده","Installed")} value={activeProtocols.toLocaleString("fa-IR")} icon="✓"/>
        <Stat label={pick("سالم","Healthy")} value={healthyProtocols.toLocaleString("fa-IR")} icon="●"/>
      </div>

      <Card>
        <div className={styles.tunnelListCard}>
          <div className="card-head"><div><b>{pick("Tunnelها","Tunnels")}</b><small>{pick("برای جزئیات و مدیریت روی دکمه مدیریت بزنید.","Open Manage for details and protocol controls.")}</small></div><Badge tone="violet">Iran → Exit</Badge></div>
          <div className={styles.searchRow}><div className="runtime-toolbar"><label>⌕ <input value={search} onChange={event=>setSearch(event.target.value)} placeholder={pick("نام، IP یا ID...","Name, IP or ID...")}/></label></div></div>
          <div className={styles.tunnelGrid}>
            {filteredTunnels.map(tunnel=>{
              const iran=nodeMap.get(tunnel.iran_node_id);const exit=nodeMap.get(tunnel.exit_node_id);const transport=String(tunnel.active_transport||tunnel.preferred_transport||tunnel.transport||"—");
              return <article key={tunnel.id} className={`${styles.tunnelCard} ${selectedId===tunnel.id?styles.selected:""}`}>
                <div className={styles.cardTop}><div className={styles.cardTitle}><b>Tunnel #{tunnel.id}</b><small>{pick("مسیر سرویس","Service pair")}</small></div><Badge tone={tone(tunnel.status)}>{String(tunnel.status||"—")}</Badge></div>
                <div className={styles.pairFlow}>
                  <div className={styles.nodeBox}><span className={styles.nodeRole}>Iran</span><b className={styles.nodeName}>{iran?.name||`#${tunnel.iran_node_id}`}</b><span className={styles.nodeIp} dir="ltr">{iran?.public_ip||"—"}</span></div>
                  <div className={styles.routeArrow}>→</div>
                  <div className={styles.nodeBox}><span className={styles.nodeRole}>Exit</span><b className={styles.nodeName}>{exit?.name||`#${tunnel.exit_node_id}`}</b><span className={styles.nodeIp} dir="ltr">{exit?.public_ip||"—"}</span></div>
                </div>
                <div className={styles.metrics}><span className={styles.metric}>{pick("مسیر فعال","Transport")}: <strong dir="ltr">{transport}</strong></span><span className={styles.metric}>Ping: <strong dir="ltr">{tunnel.latency_ms==null?"—":`${tunnel.latency_ms} ms`}</strong></span><span className={styles.metric}>{tunnel.is_active?pick("فعال","Enabled"):pick("غیرفعال","Disabled")}</span></div>
                <div className={styles.cardActions}><button type="button" className={`primary ${styles.manageButton}`} onClick={()=>openManage(tunnel.id)}>{pick("مدیریت","Manage")}</button></div>
              </article>;
            })}
            {!loading&&filteredTunnels.length===0&&<div className={styles.empty}>{pick("Tunnelی با این جستجو پیدا نشد.","No tunnel matched this search.")}</div>}
          </div>
        </div>
      </Card>

      {manageOpen&&selectedTunnel&&<Modal wide title={`Tunnel #${selectedTunnel.id}`} onClose={()=>!busy&&setManageOpen(false)}>
        <div className={styles.modalHead}>
          <div className={styles.modalTitle}><div className={styles.modalTitleRow}><b>Tunnel #{selectedTunnel.id}</b><Badge tone={tone(selectedTunnel.status)}>{String(selectedTunnel.status||"—")}</Badge></div><small>{pick("مدیریت Pair، پروتکل‌ها و اتصال‌های عمومی","Pair, protocols and public connections management")}</small></div>
          <button type="button" className="icon-button" disabled={Boolean(busy)} onClick={()=>setManageOpen(false)}>×</button>
        </div>
        <div className={styles.modalBody}>
          {error&&<div className="runtime-error">{error}</div>}{notice&&<div className="runtime-success">{notice}</div>}
          <div className={styles.summaryGrid}>
            <div className={styles.summaryItem}><span>Iran</span><b>{selectedIran?.name||`#${selectedTunnel.iran_node_id}`}</b><small dir="ltr">{selectedIran?.public_ip||"—"}</small></div>
            <div className={styles.summaryItem}><span>Exit</span><b>{selectedExit?.name||`#${selectedTunnel.exit_node_id}`}</b><small dir="ltr">{selectedExit?.public_ip||"—"}</small></div>
            <div className={styles.summaryItem}><span>{pick("مسیر فعال","Active transport")}</span><b dir="ltr">{String(selectedTunnel.active_transport||selectedTunnel.preferred_transport||selectedTunnel.transport||"—")}</b></div>
            <div className={styles.summaryItem}><span>Ping</span><b dir="ltr">{selectedTunnel.latency_ms==null?"—":`${selectedTunnel.latency_ms} ms`}</b></div>
          </div>

          <div className={styles.managementActions}>
            <button type="button" className="ghost" disabled={Boolean(busy)} onClick={toggleTunnel}>{selectedTunnel.is_active?pick("غیرفعال کردن","Disable"):pick("فعال کردن","Enable")}</button>
            <button type="button" className="primary-soft" disabled={Boolean(busy)} onClick={()=>{window.location.href="/admin/tunnel-transports";}}>{pick("مسیرهای هوشمند","Smart Transports")}</button>
            <button type="button" className="primary-soft" disabled={Boolean(busy)} onClick={openFullProtocolManager}>{pick("مدیریت کامل پروتکل‌ها","Full protocol manager")}</button>
            <button type="button" className="danger" disabled={Boolean(busy)} onClick={deleteTunnel}>{pick("حذف Tunnel","Delete tunnel")}</button>
          </div>

          <section className={styles.section}>
            <div className={styles.sectionHead}><div><b>{pick("پروتکل‌های این Tunnel","Protocols on this tunnel")}</b><small>{pick(`Inventory واقعی Exit ${selectedExit?.name||`#${selectedTunnel.exit_node_id}`}`,`Live inventory from Exit ${selectedExit?.name||`#${selectedTunnel.exit_node_id}`}`)}</small></div><Badge tone={healthyProtocols===activeProtocols&&activeProtocols>0?"ok":"violet"}>{healthyProtocols}/{activeProtocols}</Badge></div>
            <div className={styles.tableWrap}><div className="table"><table><thead><tr><th>{pick("پروتکل","Protocol")}</th><th>{pick("نوع","Type")}</th><th>{pick("پورت","Port")}</th><th>Transport</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>
              {protocols.map(row=><tr key={row.id}><td><b>{row.name}</b><small style={{display:"block"}} dir="ltr">{row.protocol}</small></td><td>{row.kind==="classic"?pick("کلاسیک","Classic"):pick("مدرن","Modern")}</td><td dir="ltr">{row.portText}</td><td dir="ltr">{row.transport}</td><td><Badge tone={tone(row.status)}>{row.status}</Badge></td><td><div className="action-row">{row.kind==="classic"?<button type="button" className="primary-soft" disabled={Boolean(busy)} onClick={()=>installClassic(row)}>{busy===`classic-${row.protocol}`?"…":row.installed?pick("Repair / Health","Repair / Health"):pick("نصب","Install")}</button>:<><button type="button" className="primary-soft" disabled={Boolean(busy)||!row.installable} onClick={()=>installModern(row)}>{busy===`modern-install-${row.protocol}`?"…":row.installed?pick("اعمال / Repair","Apply / Repair"):pick("افزودن","Add")}</button>{row.installed&&row.installable&&<button type="button" className="danger" disabled={Boolean(busy)} onClick={()=>removeModern(row)}>{pick("حذف","Remove")}</button>}</>}</div></td></tr>)}
              {!loading&&protocols.length===0&&<tr><td colSpan={6}><div className="runtime-empty">{pick("Inventory پروتکل برای Exit این Tunnel خالی است.","Protocol inventory for this tunnel Exit is empty.")}</div></td></tr>}
            </tbody></table></div></div>
          </section>

          <section className={styles.section}><TunnelServiceConnectionsPanel tunnelId={selectedTunnel.id}/></section>
        </div>
      </Modal>}

      {createOpen&&<Modal title={pick("Tunnel جدید","New tunnel")} onClose={()=>!busy&&setCreateOpen(false)}><form className="runtime-form" onSubmit={createTunnel}><label>{pick("نود ایران","Iran node")}<select value={draft.iran_node_id} onChange={event=>setDraft(value=>({...value,iran_node_id:Number(event.target.value)}))}>{readyIranNodes.map(node=><option key={node.id} value={node.id}>{node.name} · {node.public_ip}</option>)}</select></label><label>{pick("نود خارج","Exit node")}<select value={draft.exit_node_id} onChange={event=>setDraft(value=>({...value,exit_node_id:Number(event.target.value)}))}>{readyExitNodes.map(node=><option key={node.id} value={node.id}>{node.name} · {node.public_ip}</option>)}</select></label><label>{pick("اولویت","Priority")}<input type="number" value={draft.priority} onChange={event=>setDraft(value=>({...value,priority:Number(event.target.value)||100}))}/></label><div className="action-row"><button type="submit" className="primary" disabled={Boolean(busy)||!draft.iran_node_id||!draft.exit_node_id}>{busy==="create"?"…":pick("ساخت و آماده‌سازی","Create & provision")}</button></div></form></Modal>}
    </div>
  </Shell>;
}
