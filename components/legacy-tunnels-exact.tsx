"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {AdminNode,AdminTunnel,RuntimeRow} from "../lib/admin-api";
import {legacyControlApi} from "../lib/legacy-control-api";
import {useI18n} from "../lib/i18n";

const s=(value:unknown)=>String(value??"");
const n=(value:unknown)=>{const out=Number(value??0);return Number.isFinite(out)?out:0;};
const online=(value:unknown)=>s(value).toLowerCase()==="online";
const transportLabel=(value:unknown)=>({backhaul:"Backhaul",ssh_tun:"SSH TUN",ssh_relay:"SSH Relay",mtunnel:"MTunnel",wireguard:"WireGuard"} as Record<string,string>)[s(value).toLowerCase()]||s(value)||"—";

function Modal({title,sub,onClose,children,wide=false}:{title:string;sub?:string;onClose:()=>void;children:React.ReactNode;wide?:boolean}){
  return <div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" aria-label="close" onClick={onClose}/><div className={`runtime-modal-card ${wide?"manage-card":""}`}><div className="card-head"><div><b>{title}</b>{sub&&<small>{sub}</small>}</div><button type="button" className="icon-button" onClick={onClose}>×</button></div>{children}</div></div>;
}

type Draft={iran_node_id:number;exit_node_id:number;transport:string;priority:number;is_active:boolean};
const emptyDraft:Draft={iran_node_id:0,exit_node_id:0,transport:"backhaul",priority:100,is_active:true};

export function LegacyTunnelsExactPage(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<AdminTunnel[]>([]);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [query,setQuery]=useState("");
  const [createOpen,setCreateOpen]=useState(false);
  const [manageOpen,setManageOpen]=useState(false);
  const [selected,setSelected]=useState<AdminTunnel|null>(null);
  const [draft,setDraft]=useState<Draft>(emptyDraft);
  const [health,setHealth]=useState<RuntimeRow|null>(null);
  const [transports,setTransports]=useState<RuntimeRow[]>([]);
  const [mode,setMode]=useState("manual");
  const [preferred,setPreferred]=useState("backhaul");

  const load=async(silent=false)=>{
    if(!silent)setLoading(true);setError("");
    try{
      const [tunnelRows,nodeRows]=await Promise.all([legacyControlApi.tunnels(),legacyControlApi.nodes()]);
      setRows(tunnelRows);setNodes(nodeRows);
      setSelected(current=>current?(tunnelRows.find(item=>item.id===current.id)||current):null);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{if(!silent)setLoading(false);}
  };

  useEffect(()=>{void load();const timer=window.setInterval(()=>void load(true),15000);return()=>window.clearInterval(timer);},[]);

  const nodeMap=useMemo(()=>new Map(nodes.map(item=>[item.id,item])),[nodes]);
  const iranNodes=nodes.filter(item=>s(item.node_type).toLowerCase()==="iran");
  const exitNodes=nodes.filter(item=>s(item.node_type).toLowerCase()==="exit");
  const filtered=useMemo(()=>{const q=query.trim().toLowerCase();if(!q)return rows;return rows.filter(item=>{const iran=nodeMap.get(item.iran_node_id);const exit=nodeMap.get(item.exit_node_id);return `${item.id} ${item.transport||""} ${item.status||""} ${iran?.name||""} ${iran?.public_ip||""} ${exit?.name||""} ${exit?.public_ip||""}`.toLowerCase().includes(q);});},[rows,query,nodeMap]);
  const onlineCount=rows.filter(item=>online(item.status)).length;
  const degraded=rows.filter(item=>s(item.status).toLowerCase()==="degraded").length;
  const offlineCount=rows.filter(item=>!online(item.status)&&s(item.status).toLowerCase()!=="degraded").length;

  const act=async(key:string,label:string,fn:()=>Promise<unknown>,refreshDetail=false)=>{
    if(busy)return;setBusy(key);setError("");setOk("");
    try{await fn();setOk(label);await load(true);if(refreshDetail&&selected)await loadDetail(selected.id);}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}
  };

  const openCreate=()=>{
    setDraft({iran_node_id:iranNodes[0]?.id||0,exit_node_id:exitNodes[0]?.id||0,transport:"backhaul",priority:100,is_active:true});setCreateOpen(true);
  };

  const create=(event:FormEvent)=>{
    event.preventDefault();
    if(!draft.iran_node_id||!draft.exit_node_id){setError(pick("نود ایران و خروج را انتخاب کنید","Select Iran and exit nodes"));return;}
    void act("create",pick("تونل ثبت شد","Tunnel registered"),async()=>{const created=await legacyControlApi.registerTunnel(draft);setCreateOpen(false);setSelected(created);},false);
  };

  const loadDetail=async(id:number)=>{
    setHealth(null);setTransports([]);
    const [h,t]=await Promise.allSettled([legacyControlApi.tunnelHealth(id),legacyControlApi.tunnelTransports(id)]);
    if(h.status==="fulfilled")setHealth(h.value);else setError(h.reason instanceof Error?h.reason.message:String(h.reason));
    if(t.status==="fulfilled"){
      setTransports(Array.isArray(t.value.transports)?t.value.transports:[]);
      setMode(s(t.value.mode)||"manual");
      setPreferred(s(t.value.preferred_transport||t.value.active_transport)||"backhaul");
    }
  };

  const openManage=async(item:AdminTunnel)=>{
    setSelected(item);setManageOpen(true);setBusy("detail");setError("");
    try{await loadDetail(item.id);}finally{setBusy("");}
  };

  const toggle=async(item:AdminTunnel)=>{
    const action=item.is_active?pick("غیرفعال","disable"):pick("فعال","enable");
    if(!window.confirm(pick(`تونل #${item.id} ${action} شود؟`,`Change enabled state for tunnel #${item.id}?`)))return;
    await act(`toggle-${item.id}`,pick("وضعیت تونل تغییر کرد","Tunnel state updated"),()=>legacyControlApi.toggleTunnel(item.id),manageOpen);
  };

  const remove=async(item:AdminTunnel)=>{
    if(!window.confirm(pick(`تونل #${item.id} حذف شود؟ Runtime مرتبط نیز پاک‌سازی می‌شود.`,`Delete tunnel #${item.id}? Related runtime will also be cleaned.`)))return;
    await act(`delete-${item.id}`,pick("تونل حذف شد","Tunnel deleted"),()=>legacyControlApi.deleteTunnel(item.id));setManageOpen(false);setSelected(null);
  };

  const saveMode=()=>{if(!selected)return;void act("mode",pick("حالت Transport ذخیره شد","Transport mode saved"),()=>legacyControlApi.setTunnelTransportMode(selected.id,{mode,transport:mode==="manual"?preferred:null}),true);};

  const install=(kind:"ssh"|"mtunnel"|"backhaul")=>{
    if(!selected)return;
    const label=kind==="ssh"?"SSH TUN":kind==="mtunnel"?"MTunnel":"Backhaul";
    if(!window.confirm(pick(`${label} برای تونل #${selected.id} نصب/بازسازی شود؟`,`Install/rebuild ${label} for tunnel #${selected.id}?`)))return;
    const fn=kind==="ssh"?()=>legacyControlApi.installSshTunnel(selected.id):kind==="mtunnel"?()=>legacyControlApi.installMtunnel(selected.id):()=>legacyControlApi.installBackhaul(selected.id);
    void act(`install-${kind}`,pick(`${label} نصب/بازسازی شد.`,`${label} install/rebuild finished.`),fn,true);
  };

  const repairMtunnel=()=>{if(!selected)return;if(!window.confirm(pick(`MTunnel تونل #${selected.id} تعمیر شود؟`,`Repair MTunnel for tunnel #${selected.id}?`)))return;void act("repair-mtunnel",pick("تعمیر MTunnel انجام شد","MTunnel repair finished"),()=>legacyControlApi.repairMtunnel(selected.id),true);};
  const prepare=()=>{if(!selected)return;if(!window.confirm(pick(`آماده‌سازی پایه تونل #${selected.id} اجرا شود؟`,`Run base preparation for tunnel #${selected.id}?`)))return;void act("prepare",pick("آماده‌سازی تونل انجام شد","Tunnel preparation finished"),()=>legacyControlApi.prepareTunnel(selected.id),true);};

  return <Shell active="/admin/tunnels"><div className="page legacy-control-page">
    <div className="page-head"><div><h1>{pick("تانل‌ها","Tunnels")}</h1><small>{pick("مسیر ایران → خروج، Transport، سلامت و Failover","Iran → exit paths, transports, health and failover")}</small></div><div className="action-row"><button className="ghost" disabled={loading} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button><button className="primary" onClick={openCreate}>＋ {pick("تونل جدید","New tunnel")}</button></div></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats dashboard-stats"><Stat label={pick("کل تانل‌ها","Total tunnels")} value={rows.length.toLocaleString("fa-IR")}/><Stat label={pick("آنلاین","Online")} value={onlineCount.toLocaleString("fa-IR")}/><Stat label={pick("Degraded","Degraded")} value={degraded.toLocaleString("fa-IR")}/><Stat label={pick("آفلاین","Offline")} value={offlineCount.toLocaleString("fa-IR")}/></div>

    <Card>
      <div className="runtime-toolbar"><label>⌕ <input value={query} onChange={event=>setQuery(event.target.value)} placeholder={pick("نام نود، IP، Transport یا شناسه…","Node, IP, transport or ID…")}/></label></div>
      <div className="table"><table><thead><tr><th>{pick("مسیر","Path")}</th><th>{pick("Transport","Transport")}</th><th>{pick("Ping","Ping")}</th><th>{pick("اولویت","Priority")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("اجرا","Enabled")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map(item=>{const iran=nodeMap.get(item.iran_node_id);const exit=nodeMap.get(item.exit_node_id);return <tr key={item.id}><td><div className="user-cell"><b>{iran?.name||`#${item.iran_node_id}`} ← {exit?.name||`#${item.exit_node_id}`}</b><small dir="ltr">{iran?.public_ip||"—"} → {exit?.public_ip||"—"}</small></div></td><td><b dir="ltr">{transportLabel(item.transport)}</b></td><td dir="ltr">{item.latency_ms==null?"—":`${item.latency_ms} ms`}</td><td>{n(item.priority).toLocaleString("fa-IR")}</td><td><Badge tone={online(item.status)?"ok":s(item.status).toLowerCase()==="degraded"?"warn":"bad"}>{s(item.status)||"—"}</Badge></td><td><Badge tone={item.is_active?"ok":"warn"}>{item.is_active?pick("فعال","Active"):pick("خاموش","Disabled")}</Badge></td><td><div className="row-actions"><button className="primary-soft" onClick={()=>void openManage(item)}>{pick("مدیریت","Manage")}</button><button disabled={!!busy} onClick={()=>void toggle(item)}>{item.is_active?pick("غیرفعال","Disable"):pick("فعال","Enable")}</button><button className="danger" disabled={!!busy} onClick={()=>void remove(item)}>{pick("حذف","Delete")}</button></div></td></tr>;})}</tbody></table>{!filtered.length&&!loading&&<div className="runtime-empty">{pick("تانلی پیدا نشد","No tunnels found")}</div>}</div>
    </Card>

    {createOpen&&<Modal title={pick("ساخت تونل","Create tunnel")} sub={pick("انتخاب جفت ایران و خروج","Select Iran and exit pair")} onClose={()=>!busy&&setCreateOpen(false)}>
      <form onSubmit={create}><div className="setting-grid"><label className="field"><span>{pick("نود ایران","Iran node")}</span><select value={draft.iran_node_id} onChange={e=>setDraft(d=>({...d,iran_node_id:Number(e.target.value)}))}><option value={0}>{pick("انتخاب","Select")}</option>{iranNodes.map(item=><option key={item.id} value={item.id}>{item.name} · {item.public_ip}</option>)}</select></label><label className="field"><span>{pick("نود خروج","Exit node")}</span><select value={draft.exit_node_id} onChange={e=>setDraft(d=>({...d,exit_node_id:Number(e.target.value)}))}><option value={0}>{pick("انتخاب","Select")}</option>{exitNodes.map(item=><option key={item.id} value={item.id}>{item.name} · {item.public_ip}</option>)}</select></label><label className="field"><span>Transport</span><select value={draft.transport} onChange={e=>setDraft(d=>({...d,transport:e.target.value}))}><option value="backhaul">Backhaul</option><option value="ssh_tun">SSH TUN</option><option value="mtunnel">MTunnel</option></select></label><label className="field"><span>{pick("اولویت","Priority")}</span><input type="number" min={1} value={draft.priority} onChange={e=>setDraft(d=>({...d,priority:Math.max(1,Number(e.target.value)||1)}))}/></label></div><label className="toggle module-toggle compact-toggle"><span>{pick("فعال بعد از ساخت","Enable after creation")}</span><input type="checkbox" checked={draft.is_active} onChange={e=>setDraft(d=>({...d,is_active:e.target.checked}))}/><i/></label><div className="modalActions"><button type="button" className="ghost" onClick={()=>setCreateOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy==="create"||!draft.iran_node_id||!draft.exit_node_id}>{busy==="create"?"…":pick("ثبت تونل","Register tunnel")}</button></div></form>
    </Modal>}

    {manageOpen&&selected&&<Modal title={pick("مدیریت تونل","Manage tunnel")} sub={`#${selected.id} · ${nodeMap.get(selected.iran_node_id)?.name||selected.iran_node_id} → ${nodeMap.get(selected.exit_node_id)?.name||selected.exit_node_id}`} onClose={()=>!busy&&setManageOpen(false)} wide>
      <div className="manage-card-section"><div className="manage-section-head"><div><b>{pick("سلامت مسیر","Path health")}</b><small>{pick("داده Health واقعی Backend","Live backend health")}</small></div><button className="ghost" disabled={!!busy} onClick={()=>void act("health",pick("سلامت بروزرسانی شد","Health refreshed"),async()=>setHealth(await legacyControlApi.tunnelHealth(selected.id)))}>{busy==="health"?"…":pick("بررسی سلامت","Check health")}</button></div><div className="legacy-detail-grid"><div><small>{pick("وضعیت","Status")}</small><b>{s(health?.status||selected.status)||"—"}</b></div><div><small>{pick("Ping","Ping")}</small><b dir="ltr">{n(health?.latency_ms||selected.latency_ms)?`${n(health?.latency_ms||selected.latency_ms)} ms`:"—"}</b></div><div><small>{pick("Transport فعال","Active transport")}</small><b dir="ltr">{transportLabel(health?.active_transport||selected.transport)}</b></div><div><small>{pick("Interface","Interface")}</small><b dir="ltr">{s(health?.interface||health?.interface_name)||"—"}</b></div></div></div>

      <div className="manage-card-section"><div className="manage-section-head"><div><b>{pick("حالت Transport","Transport mode")}</b><small>{pick("Manual یا Auto Failover","Manual or Auto Failover")}</small></div></div><div className="setting-grid"><label className="field"><span>{pick("حالت","Mode")}</span><select value={mode} onChange={e=>setMode(e.target.value)}><option value="manual">Manual</option><option value="auto">Auto</option></select></label><label className="field"><span>{pick("Transport ترجیحی","Preferred transport")}</span><select value={preferred} disabled={mode!=="manual"} onChange={e=>setPreferred(e.target.value)}>{[...new Set(["backhaul","ssh_tun","mtunnel",...transports.map(item=>s(item.transport)).filter(Boolean)])].map(item=><option key={item} value={item}>{transportLabel(item)}</option>)}</select></label></div><button className="primary-soft" disabled={!!busy} onClick={saveMode}>{busy==="mode"?"…":pick("ذخیره حالت","Save mode")}</button></div>

      <div className="manage-card-section"><div className="manage-section-head"><div><b>{pick("Transportها","Transports")}</b><small>{pick("نصب، تعمیر و وضعیت Transportهای همین تونل","Install, repair and inspect transports for this tunnel")}</small></div></div><div className="legacy-transport-list">{transports.map((item,index)=><div className="setting-box" key={`${s(item.transport)}-${index}`}><div className="card-head"><b>{transportLabel(item.transport)}</b><Badge tone={online(item.status)?"ok":s(item.status)==="degraded"?"warn":"bad"}>{s(item.status)||"—"}</Badge></div><div className="legacy-detail-grid compact"><div><small>{pick("اولویت","Priority")}</small><b>{n(item.priority).toLocaleString("fa-IR")}</b></div><div><small>{pick("Ping","Ping")}</small><b dir="ltr">{item.latency_ms==null?"—":`${n(item.latency_ms)} ms`}</b></div></div>{s(item.last_error)&&<small className="runtime-inline-error">{s(item.last_error)}</small>}</div>)}</div><div className="manage-actions"><button className="ghost" disabled={!!busy} onClick={()=>install("backhaul")}>{busy==="install-backhaul"?"…":pick("نصب Backhaul","Install Backhaul")}</button><button className="ghost" disabled={!!busy} onClick={()=>install("ssh")}>{busy==="install-ssh"?"…":pick("نصب SSH TUN","Install SSH TUN")}</button><button className="ghost" disabled={!!busy} onClick={()=>install("mtunnel")}>{busy==="install-mtunnel"?"…":pick("نصب MTunnel","Install MTunnel")}</button><button className="ghost" disabled={!!busy} onClick={repairMtunnel}>{busy==="repair-mtunnel"?"…":pick("تعمیر MTunnel","Repair MTunnel")}</button><button className="ghost" disabled={!!busy} onClick={prepare}>{busy==="prepare"?"…":pick("آماده‌سازی","Prepare")}</button></div></div>

      <div className="modalActions"><button className="ghost" onClick={()=>setManageOpen(false)}>{pick("بستن","Close")}</button><button disabled={!!busy} onClick={()=>void toggle(selected)}>{selected.is_active?pick("غیرفعال کردن","Disable"):pick("فعال کردن","Enable")}</button><button className="danger" disabled={!!busy} onClick={()=>void remove(selected)}>{pick("حذف تونل","Delete tunnel")}</button></div>
    </Modal>}
  </div></Shell>;
}
