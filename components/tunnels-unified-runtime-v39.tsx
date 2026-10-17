"use client";

import {type FormEvent,useEffect,useMemo,useState} from "react";

import {Badge,Card,Shell,Stat} from "./ui";
import type {AdminNode,AdminTunnel} from "../lib/admin-api";
import {legacyControlApi} from "../lib/legacy-control-api";
import {
  type TunnelTransportName,
  type TunnelTransportRow,
  type TunnelTransportState,
  tunnelTransportApi,
} from "../lib/tunnel-transport-api";
import {TunnelServiceConnectionsPanel} from "./tunnel-service-connections-panel";
import {useI18n} from "../lib/i18n";

type Draft={iran_node_id:number;exit_node_id:number;priority:number};
type AgentMeta={available?:boolean;agent_version?:string|null;age_seconds?:number|null};
type SideDiag={
  ok?:boolean;
  error?:string;
  service?:{ActiveState?:string;SubState?:string};
  interface?:{exists?:boolean;mtu?:number|null;addr?:string};
  listener?:{required?:boolean;present?:boolean|null};
  firewall?:{checked?:boolean;present?:boolean|null};
  ping?:{loss_pct?:number|null;latency_ms?:number|null};
};
type DeepTransport={
  transport?:string;
  root_cause_code?:string;
  summary?:string;
  db?:{status?:string;enabled?:boolean;last_error?:string|null};
  iran?:SideDiag;
  exit?:SideDiag;
};
type DeepDiagnosis={
  ok?:boolean;
  source?:string;
  partial?:boolean;
  active_transport?:string|null;
  preferred_transport?:string|null;
  unhealthy?:string[];
  transports?:DeepTransport[];
  agents?:{iran?:AgentMeta;exit?:AgentMeta};
};

const emptyDraft:Draft={iran_node_id:0,exit_node_id:0,priority:100};

const labels:Record<string,string>={
  quic_2027:"QUIC 2027",
  arq_2027:"ARQ 2027",
  kcp_2027:"KCP 2027",
  tcp_2027:"TCP 2027",
  kernel_gre:"Kernel GRE",
  backhaul:"Backhaul",
  mtunnel:"MTunnel",
  gost_tun:"GOST TUN",
  ssh_tun:"SSH TUN",
  ssh_relay:"SSH Relay",
};

const normalized=(value:unknown)=>String(value??"").trim().toLowerCase();
const transportLabel=(value:unknown)=>labels[String(value??"").trim()]||String(value??"—");
const statusTone=(value:unknown):"ok"|"warn"|"bad"|"violet"=>{
  const status=normalized(value);
  if(["online","active","healthy","ok","ready"].includes(status))return "ok";
  if(["offline","failed","error","down","stopped"].includes(status))return "bad";
  if(status==="manual")return "violet";
  return "warn";
};

function Modal({title,onClose,children}:{title:string;onClose:()=>void;children:React.ReactNode}){
  return <div className="runtime-modal" role="dialog" aria-modal="true">
    <button type="button" className="runtime-modal-bg" aria-label="close" onClick={onClose}/>
    <div className="runtime-modal-card">
      <div className="card-head">
        <b>{title}</b>
        <button type="button" className="icon-button" onClick={onClose}>×</button>
      </div>
      {children}
    </div>
  </div>;
}

export function TunnelsUnifiedRuntimeV39(){
  const {pick}=useI18n();
  const [tunnels,setTunnels]=useState<AdminTunnel[]>([]);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [success,setSuccess]=useState("");
  const [search,setSearch]=useState("");
  const [createOpen,setCreateOpen]=useState(false);
  const [manageOpen,setManageOpen]=useState(false);
  const [selected,setSelected]=useState<AdminTunnel|null>(null);
  const [draft,setDraft]=useState<Draft>(emptyDraft);
  const [transportState,setTransportState]=useState<TunnelTransportState|null>(null);
  const [manualTransport,setManualTransport]=useState<TunnelTransportName|"">("");
  const [deep,setDeep]=useState<DeepDiagnosis|null>(null);

  const nodeMap=useMemo(()=>new Map(nodes.map(node=>[node.id,node])),[nodes]);
  const iranNodes=useMemo(()=>nodes.filter(node=>normalized(node.node_type)==="iran"),[nodes]);
  const exitNodes=useMemo(()=>nodes.filter(node=>normalized(node.node_type)==="exit"),[nodes]);
  const filtered=useMemo(()=>{
    const q=search.trim().toLowerCase();
    if(!q)return tunnels;
    return tunnels.filter(tunnel=>{
      const iran=nodeMap.get(tunnel.iran_node_id);
      const exit=nodeMap.get(tunnel.exit_node_id);
      return `${tunnel.id} ${tunnel.status||""} ${iran?.name||""} ${iran?.public_ip||""} ${exit?.name||""} ${exit?.public_ip||""}`.toLowerCase().includes(q);
    });
  },[tunnels,search,nodeMap]);

  const onlineCount=tunnels.filter(row=>normalized(row.status)==="online").length;
  const degradedCount=tunnels.filter(row=>normalized(row.status)==="degraded").length;
  const offlineCount=Math.max(0,tunnels.length-onlineCount-degradedCount);

  const usableTransports=useMemo(()=>{
    const rows=Array.isArray(transportState?.transports)?transportState!.transports as TunnelTransportRow[]:[];
    return rows.filter(row=>row.enabled!==false&&normalized(row.status)==="online"&&String(row.transport||"").trim());
  },[transportState]);

  const load=async(silent=false)=>{
    if(!silent)setLoading(true);
    if(!silent)setError("");
    try{
      const [ts,ns]=await Promise.all([legacyControlApi.tunnels(),legacyControlApi.nodes()]);
      setTunnels(ts);setNodes(ns);
      setSelected(current=>current?ts.find(row=>row.id===current.id)||null:null);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{if(!silent)setLoading(false);}
  };

  const loadTransport=async(id:number)=>{
    const state=await tunnelTransportApi.transports(id);
    setTransportState(state);
    const preferred=String(state.active_transport||state.preferred_transport||"") as TunnelTransportName;
    const rows=Array.isArray(state.transports)?state.transports:[];
    const first=rows.find(row=>row.enabled!==false&&normalized(row.status)==="online")?.transport;
    setManualTransport((preferred||String(first||"")) as TunnelTransportName|"");
  };

  useEffect(()=>{void load();const timer=window.setInterval(()=>void load(true),15000);return()=>window.clearInterval(timer);},[]);

  const run=async(key:string,message:string,action:()=>Promise<unknown>,refresh=true)=>{
    if(busy)return null;
    setBusy(key);setError("");setSuccess("");
    try{
      const result=await action();
      setSuccess(message);
      await load(true);
      if(refresh&&selected)await loadTransport(selected.id);
      return result;
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));return null;}
    finally{setBusy("");}
  };

  const openManage=(tunnel:AdminTunnel)=>{
    setSelected(tunnel);setManageOpen(true);setDeep(null);setTransportState(null);setError("");setSuccess("");
    void loadTransport(tunnel.id).catch(reason=>setError(reason instanceof Error?reason.message:String(reason)));
  };

  const createTunnel=async(event:FormEvent)=>{
    event.preventDefault();
    if(busy||!draft.iran_node_id||!draft.exit_node_id)return;
    setBusy("create");setError("");setSuccess("");
    try{
      const result=await legacyControlApi.createManagedTunnel({...draft,transport:"auto",is_active:true});
      if(!result?.tunnel?.id)throw new Error("INVALID_MANAGED_TUNNEL_RESPONSE");
      setCreateOpen(false);setSuccess(pick("تانل ساخته شد.","Tunnel created."));await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const setAuto=async()=>{
    if(!selected)return;
    await run(`auto-${selected.id}`,pick("مدیریت خودکار مسیر فعال شد.","Automatic path management enabled."),()=>tunnelTransportApi.setMode(selected.id,{mode:"auto"}));
  };

  const setManual=async()=>{
    if(!selected||!manualTransport)return;
    await run(`manual-${selected.id}`,pick("مسیر انتخاب‌شده فعال شد.","Selected path activated."),()=>tunnelTransportApi.setMode(selected.id,{mode:"manual",transport:manualTransport as TunnelTransportName}));
  };

  const deepDiagnose=async()=>{
    if(!selected||busy)return;
    setBusy(`deep-${selected.id}`);setError("");setSuccess("");
    try{
      const result=await tunnelTransportApi.managedDeepDiagnose(selected.id) as DeepDiagnosis;
      setDeep(result);setSuccess(pick("تشخیص عمیق بروزرسانی شد.","Deep diagnosis refreshed."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const installAgents=async()=>{
    if(!selected||busy)return;
    setBusy(`agent-${selected.id}`);setError("");
    try{
      await tunnelTransportApi.installDeepDiagnosticsAgent(selected.id);
      await new Promise(resolve=>window.setTimeout(resolve,8000));
      const result=await tunnelTransportApi.managedDeepDiagnose(selected.id) as DeepDiagnosis;
      setDeep(result);setSuccess(pick("Agent تشخیص آماده شد.","Diagnostics agent is ready."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const deepRepair=async()=>{
    if(!selected||busy)return;
    if(!window.confirm(pick(`تعمیر عمیق تانل #${selected.id} اجرا شود؟`,`Run deep repair for tunnel #${selected.id}?`)))return;
    setBusy(`repair-${selected.id}`);setError("");setSuccess("");
    try{
      await tunnelTransportApi.managedDeepRepair(selected.id);
      const result=await tunnelTransportApi.managedDeepDiagnose(selected.id) as DeepDiagnosis;
      setDeep(result);await load(true);await loadTransport(selected.id);
      setSuccess(pick("تعمیر عمیق تمام شد و نتیجه دوباره بررسی شد.","Deep repair completed and was rechecked."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const toggleSelected=async()=>{
    if(!selected)return;
    await run(`toggle-${selected.id}`,pick("وضعیت تانل تغییر کرد.","Tunnel state updated."),()=>legacyControlApi.toggleTunnel(selected.id),false);
  };

  const deleteSelected=async()=>{
    if(!selected||!window.confirm(pick(`تانل #${selected.id} حذف شود؟`,`Delete tunnel #${selected.id}?`)))return;
    const id=selected.id;
    const result=await run(`delete-${id}`,pick("تانل حذف شد.","Tunnel deleted."),()=>legacyControlApi.deleteTunnel(id),false);
    if(result!==null){setManageOpen(false);setSelected(null);setTransportState(null);setDeep(null);}
  };

  const agentsReady=Boolean(deep?.agents?.iran?.available&&deep?.agents?.exit?.available);

  return <Shell active="/admin/tunnels">
    <div className="page legacy-control-page">
      <div className="page-head">
        <div><h1>{pick("تانل‌ها","Tunnels")}</h1><small>{pick("تمام کنترل، سرویس‌ها و تشخیص هر تانل در یک صفحه.","All tunnel control, service routing and diagnostics in one place.")}</small></div>
        <div className="action-row">
          <button type="button" className="ghost" disabled={loading} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button>
          <button type="button" className="primary" onClick={()=>{setDraft({iran_node_id:iranNodes[0]?.id||0,exit_node_id:exitNodes[0]?.id||0,priority:100});setCreateOpen(true);}}>＋ {pick("تانل جدید","New tunnel")}</button>
        </div>
      </div>

      {error&&<div className="runtime-error">{error}</div>}
      {success&&<div className="runtime-success">{success}</div>}

      <div className="stats dashboard-stats">
        <Stat label={pick("کل تانل‌ها","Total tunnels")} value={tunnels.length.toLocaleString("fa-IR")} icon="⤨"/>
        <Stat label={pick("آنلاین","Online")} value={onlineCount.toLocaleString("fa-IR")} icon="✓"/>
        <Stat label="Degraded" value={degradedCount.toLocaleString("fa-IR")} icon="◌"/>
        <Stat label={pick("آفلاین","Offline")} value={offlineCount.toLocaleString("fa-IR")} icon="×"/>
      </div>

      <Card>
        <div className="runtime-toolbar"><label>⌕ <input value={search} onChange={e=>setSearch(e.target.value)} placeholder={pick("نام، IP یا شناسه...","Name, IP or ID...")}/></label></div>
        <div className="table"><table><thead><tr><th>{pick("مسیر","Route")}</th><th>Ping</th><th>{pick("وضعیت","Status")}</th><th>{pick("مسیر فعال","Active path")}</th><th>{pick("عملیات","Actions")}</th></tr></thead>
          <tbody>{filtered.map(tunnel=>{const iran=nodeMap.get(tunnel.iran_node_id);const exit=nodeMap.get(tunnel.exit_node_id);return <tr key={tunnel.id}>
            <td><div className="user-cell"><b>{iran?.name||`#${tunnel.iran_node_id}`} → {exit?.name||`#${tunnel.exit_node_id}`}</b><small dir="ltr">{iran?.public_ip||"—"} → {exit?.public_ip||"—"}</small></div></td>
            <td dir="ltr">{tunnel.latency_ms==null?"—":`${tunnel.latency_ms} ms`}</td>
            <td><Badge tone={statusTone(tunnel.status)}>{String(tunnel.status||"—")}</Badge></td>
            <td dir="ltr">{transportLabel(tunnel.active_transport||tunnel.preferred_transport||tunnel.transport)}</td>
            <td><button type="button" className="primary-soft" onClick={()=>openManage(tunnel)}>{pick("مدیریت","Manage")}</button></td>
          </tr>;})}</tbody>
        </table></div>
      </Card>

      {createOpen&&<Modal title={pick("تانل جدید","New tunnel")} onClose={()=>setCreateOpen(false)}>
        <form className="runtime-form" onSubmit={createTunnel}>
          <label>{pick("نود ایران","Iran node")}<select value={draft.iran_node_id} onChange={e=>setDraft(v=>({...v,iran_node_id:Number(e.target.value)}))}>{iranNodes.map(n=><option key={n.id} value={n.id}>{n.name} · {n.public_ip}</option>)}</select></label>
          <label>{pick("نود خارج","Exit node")}<select value={draft.exit_node_id} onChange={e=>setDraft(v=>({...v,exit_node_id:Number(e.target.value)}))}>{exitNodes.map(n=><option key={n.id} value={n.id}>{n.name} · {n.public_ip}</option>)}</select></label>
          <label>{pick("اولویت","Priority")}<input type="number" value={draft.priority} onChange={e=>setDraft(v=>({...v,priority:Number(e.target.value)||100}))}/></label>
          <div className="action-row"><button type="submit" className="primary" disabled={Boolean(busy)}>{busy==="create"?"…":pick("ساخت تانل","Create tunnel")}</button></div>
        </form>
      </Modal>}

      {manageOpen&&selected&&<Modal title={`${pick("مدیریت تانل","Tunnel management")} #${selected.id}`} onClose={()=>setManageOpen(false)}>
        <div className="runtime-info-list">
          <div><span>{pick("وضعیت","Status")}</span><Badge tone={statusTone(selected.status)}>{String(selected.status||"—")}</Badge></div>
          <div><span>{pick("حالت","Mode")}</span><b dir="ltr">{transportState?.mode||selected.mode||"—"}</b></div>
          <div><span>{pick("مسیر فعال","Active path")}</span><b dir="ltr">{transportLabel(transportState?.active_transport||selected.active_transport)}</b></div>
          <div><span>Ping</span><b dir="ltr">{selected.latency_ms==null?"—":`${selected.latency_ms} ms`}</b></div>
        </div>

        <Card>
          <div className="card-head"><div><b>{pick("انتخاب مسیر","Path selection")}</b><small>{pick("فقط مسیرهایی که واقعاً Online گزارش شده‌اند قابل انتخاب هستند.","Only transports that are actually online can be selected.")}</small></div></div>
          <div className="action-row">
            <button type="button" className="primary-soft" disabled={Boolean(busy)} onClick={()=>void setAuto()}>{pick("خودکار","Auto")}</button>
            <select value={manualTransport} disabled={Boolean(busy)||usableTransports.length===0} onChange={e=>setManualTransport(e.target.value as TunnelTransportName)}>
              {usableTransports.map(row=><option key={String(row.transport)} value={String(row.transport)}>{transportLabel(row.transport)}{row.latency_ms!=null?` · ${row.latency_ms}ms`:""}</option>)}
            </select>
            <button type="button" disabled={Boolean(busy)||!manualTransport} onClick={()=>void setManual()}>{pick("اعمال مسیر","Apply path")}</button>
          </div>
        </Card>

        <TunnelServiceConnectionsPanel tunnelId={selected.id}/>

        <Card>
          <div className="card-head"><div><b>{pick("تشخیص و تعمیر","Diagnostics & repair")}</b><small>{pick("تشخیص عمیق و تعمیر واقعی در همین بخش انجام می‌شود؛ دکمه‌های تکراری حذف شده‌اند.","Deep diagnosis and real repair are handled here; duplicate actions were removed.")}</small></div></div>
          <div className="action-row">
            <button type="button" className="primary-soft" disabled={Boolean(busy)} onClick={()=>void deepDiagnose()}>{busy===`deep-${selected.id}`?"…":pick("تشخیص عمیق","Deep diagnose")}</button>
            <button type="button" className="primary" disabled={Boolean(busy)} onClick={()=>void deepRepair()}>{busy===`repair-${selected.id}`?"…":pick("تعمیر عمیق","Deep repair")}</button>
            {deep&&!agentsReady?<button type="button" className="ghost" disabled={Boolean(busy)} onClick={()=>void installAgents()}>{busy===`agent-${selected.id}`?"…":pick("راه‌اندازی Agent تشخیص","Setup diagnostics agent")}</button>:null}
          </div>
          {deep?<>
            <div className="runtime-info-list">
              <div><span>{pick("منبع تشخیص","Diagnosis source")}</span><b dir="ltr">{deep.source||"—"}</b></div>
              <div><span>{pick("مسیر فعال","Active path")}</span><b dir="ltr">{transportLabel(deep.active_transport)}</b></div>
              <div><span>{pick("Agent ایران","Iran agent")}</span><Badge tone={deep.agents?.iran?.available?"ok":"warn"}>{deep.agents?.iran?.available?"ONLINE":"UNAVAILABLE"}</Badge></div>
              <div><span>{pick("Agent خارج","Exit agent")}</span><Badge tone={deep.agents?.exit?.available?"ok":"warn"}>{deep.agents?.exit?.available?"ONLINE":"UNAVAILABLE"}</Badge></div>
            </div>
            <div className="tunnel-service-compact-grid">{(deep.transports||[]).map((row,index)=><div className="tunnel-service-compact-item" key={`${row.transport||"transport"}-${index}`}>
              <div className="tunnel-service-compact-item-head"><b>{transportLabel(row.transport)}</b><Badge tone={row.root_cause_code==="healthy"?"ok":statusTone(row.db?.status)}>{row.root_cause_code||row.db?.status||"—"}</Badge></div>
              <small>{row.summary||row.db?.last_error||""}</small>
              <div className="runtime-info-list">
                <div><span>Iran loss</span><b>{row.iran?.ping?.loss_pct==null?"—":`${row.iran.ping.loss_pct}%`}</b></div>
                <div><span>Exit loss</span><b>{row.exit?.ping?.loss_pct==null?"—":`${row.exit.ping.loss_pct}%`}</b></div>
              </div>
            </div>)}</div>
          </>:null}
        </Card>

        <div className="action-row">
          <button type="button" className="ghost" disabled={Boolean(busy)} onClick={()=>void toggleSelected()}>{selected.is_active?pick("غیرفعال کردن تانل","Disable tunnel"):pick("فعال کردن تانل","Enable tunnel")}</button>
          <button type="button" className="danger" disabled={Boolean(busy)} onClick={()=>void deleteSelected()}>{pick("حذف تانل","Delete tunnel")}</button>
        </div>
      </Modal>}
    </div>
  </Shell>;
}
