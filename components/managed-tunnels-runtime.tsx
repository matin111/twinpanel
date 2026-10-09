"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import type {AdminNode,AdminTunnel,RuntimeRow} from "../lib/admin-api";
import {legacyControlApi} from "../lib/legacy-control-api";
import {useI18n} from "../lib/i18n";

const s=(value:unknown)=>String(value??"");
const n=(value:unknown)=>{const out=Number(value??0);return Number.isFinite(out)?out:0;};
const lower=(value:unknown)=>s(value).trim().toLowerCase();
const online=(value:unknown)=>lower(value)==="online";

type TransportName=
  |"quic_2027"
  |"arq_2027"
  |"kcp_2027"
  |"tcp_2027"
  |"mtunnel"
  |"backhaul"
  |"ssh_tun";

const transportOrder:TransportName[]=[
  "quic_2027","arq_2027","kcp_2027","tcp_2027","mtunnel","backhaul","ssh_tun",
];

const transportPriority:Record<TransportName,number>={
  quic_2027:10,
  arq_2027:20,
  kcp_2027:30,
  tcp_2027:40,
  mtunnel:90,
  backhaul:100,
  ssh_tun:200,
};

const transportLabels:Record<TransportName,string>={
  quic_2027:"QUIC 2027",
  arq_2027:"ARQ 2027",
  kcp_2027:"KCP 2027",
  tcp_2027:"TCP 2027",
  mtunnel:"MTunnel",
  backhaul:"Backhaul",
  ssh_tun:"SSH TUN",
};

const transportLabel=(value:unknown)=>{
  const key=lower(value) as TransportName;
  return transportLabels[key]||s(value)||"—";
};

const statusTone=(value:unknown):"ok"|"warn"|"bad"|"violet"=>{
  const valueLower=lower(value);
  if(valueLower==="online")return "ok";
  if(valueLower==="degraded"||valueLower==="installing"||valueLower==="pending")return "warn";
  if(valueLower==="missing"||valueLower==="not_installed")return "violet";
  return "bad";
};

const issueLabel=(value:unknown,fa:boolean)=>{
  const code=lower(value);
  if(!code)return "";
  const labels:Record<string,[string,string]>={
    carrier_down:["Carrier بک‌هال در دسترس نیست","Backhaul carrier unavailable"],
    not_installed:["نصب نشده","Not installed"],
    disabled:["غیرفعال","Disabled"],
    unhealthy:["ناسالم؛ نیازمند تعمیر","Unhealthy; repair needed"],
  };
  const item=labels[code];
  return item?(fa?item[0]:item[1]):code;
};

function Modal({title,sub,onClose,children,wide=false}:{title:string;sub?:string;onClose:()=>void;children:React.ReactNode;wide?:boolean}){
  return <div className="runtime-modal" role="dialog" aria-modal="true">
    <button className="runtime-modal-bg" aria-label="close" onClick={onClose}/>
    <div className={`runtime-modal-card ${wide?"manage-card":""}`}>
      <div className="card-head"><div><b>{title}</b>{sub&&<small>{sub}</small>}</div><button type="button" className="icon-button" onClick={onClose}>×</button></div>
      {children}
    </div>
  </div>;
}

type Draft={iran_node_id:number;exit_node_id:number;priority:number};
const emptyDraft:Draft={iran_node_id:0,exit_node_id:0,priority:100};

export function ManagedTunnelsRuntimePage(){
  const {pick,language}=useI18n();
  const fa=language!=="en";
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
  const [transports,setTransports]=useState<RuntimeRow[]>([]);
  const [diagnosis,setDiagnosis]=useState<RuntimeRow|null>(null);
  const [mode,setMode]=useState("auto");
  const [preferred,setPreferred]=useState<TransportName>("quic_2027");
  const [createStep,setCreateStep]=useState("");

  const load=async(silent=false)=>{
    if(!silent)setLoading(true);
    try{
      const [tunnelRows,nodeRows]=await Promise.all([legacyControlApi.tunnels(),legacyControlApi.nodes()]);
      setRows(tunnelRows);
      setNodes(nodeRows);
      setSelected(current=>current?(tunnelRows.find(item=>item.id===current.id)||current):null);
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      if(!silent)setLoading(false);
    }
  };

  useEffect(()=>{
    void load();
    const timer=window.setInterval(()=>void load(true),15000);
    return()=>window.clearInterval(timer);
  },[]);

  const nodeMap=useMemo(()=>new Map(nodes.map(item=>[item.id,item])),[nodes]);
  const iranNodes=useMemo(()=>nodes.filter(item=>lower(item.node_type)==="iran"&&online(item.status)),[nodes]);
  const exitNodes=useMemo(()=>nodes.filter(item=>lower(item.node_type)==="exit"&&online(item.status)),[nodes]);
  const usedPairs=useMemo(()=>new Set(rows.map(item=>`${item.iran_node_id}:${item.exit_node_id}`)),[rows]);
  const availableExits=useMemo(()=>exitNodes.filter(item=>!draft.iran_node_id||!usedPairs.has(`${draft.iran_node_id}:${item.id}`)),[exitNodes,draft.iran_node_id,usedPairs]);

  const filtered=useMemo(()=>{
    const q=query.trim().toLowerCase();
    if(!q)return rows;
    return rows.filter(item=>{
      const iran=nodeMap.get(item.iran_node_id);
      const exit=nodeMap.get(item.exit_node_id);
      return `${item.id} ${item.active_transport||""} ${item.status||""} ${iran?.name||""} ${iran?.public_ip||""} ${exit?.name||""} ${exit?.public_ip||""}`.toLowerCase().includes(q);
    });
  },[rows,query,nodeMap]);

  const onlineCount=rows.filter(item=>online(item.status)).length;
  const degradedCount=rows.filter(item=>lower(item.status)==="degraded").length;
  const offlineCount=rows.filter(item=>!online(item.status)&&lower(item.status)!=="degraded").length;

  const loadDetail=async(id:number)=>{
    setError("");
    const [transportResult,diagnosisResult]=await Promise.allSettled([
      legacyControlApi.tunnelTransports(id),
      legacyControlApi.managedDiagnose(id),
    ]);

    if(diagnosisResult.status==="fulfilled"){
      const value=diagnosisResult.value as RuntimeRow;
      setDiagnosis(value);
      const items=Array.isArray(value.transports)?value.transports as RuntimeRow[]:[];
      setTransports(items);
      setMode(s(value.mode)||"auto");
      const current=lower(value.preferred_transport||value.active_transport||"quic_2027") as TransportName;
      setPreferred(transportOrder.includes(current)?current:"quic_2027");
      return;
    }

    setDiagnosis(null);
    if(transportResult.status==="fulfilled"){
      const value=transportResult.value;
      setTransports(Array.isArray(value.transports)?value.transports:[]);
      setMode(s(value.mode)||"auto");
      const current=lower(value.preferred_transport||value.active_transport||"quic_2027") as TransportName;
      setPreferred(transportOrder.includes(current)?current:"quic_2027");
    }else{
      setTransports([]);
      setError(diagnosisResult.reason instanceof Error?diagnosisResult.reason.message:String(diagnosisResult.reason));
    }
  };

  const openCreate=()=>{
    setError("");setOk("");setCreateStep("");
    const iranId=iranNodes[0]?.id||0;
    const exitId=exitNodes.find(item=>!usedPairs.has(`${iranId}:${item.id}`))?.id||0;
    setDraft({iran_node_id:iranId,exit_node_id:exitId,priority:100});
    setCreateOpen(true);
  };

  const create=async(event:FormEvent)=>{
    event.preventDefault();
    if(busy)return;
    if(!draft.iran_node_id||!draft.exit_node_id){
      setError(pick("یک Pair آزاد ایران و خروج انتخاب کنید.","Select an unused Iran/exit pair."));
      return;
    }

    setBusy("create");setError("");setOk("");
    setCreateStep(pick("در حال نصب خودکار مسیرهای پایه و TP2027 و انتخاب بهترین مسیر…","Automatically installing base and TP2027 transports and selecting the best path…"));

    try{
      const managed=await legacyControlApi.createManagedTunnel({
        iran_node_id:draft.iran_node_id,
        exit_node_id:draft.exit_node_id,
        transport:"ssh_tun",
        priority:draft.priority,
        is_active:true,
      });

      const tunnelId=Number(managed.tunnel?.id||0);
      if(!tunnelId)throw new Error(pick("شناسه تونل از Backend دریافت نشد.","Backend did not return a tunnel ID."));

      setCreateStep(pick("در حال عیب‌یابی نهایی و دریافت وضعیت Manager…","Running final diagnosis and reading Manager state…"));
      await load(true);
      const latest=(await legacyControlApi.tunnels()).find(item=>item.id===tunnelId)||managed.tunnel;
      setSelected(latest);
      setCreateOpen(false);
      setManageOpen(true);
      await loadDetail(tunnelId);

      const failed=Object.entries(managed.errors||{});
      if(failed.length){
        setError(pick(`تونل ساخته شد ولی بعضی مسیرها نیاز به تعمیر دارند: ${failed.map(([key])=>transportLabel(key)).join("، ")}`,`Tunnel was created, but some transports need repair: ${failed.map(([key])=>transportLabel(key)).join(", ")}`));
      }else{
        setOk(pick("تونل به‌صورت کامل و خودکار ساخته شد.","Tunnel was created automatically."));
      }
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setCreateStep("");setBusy("");
    }
  };

  const openManage=async(item:AdminTunnel)=>{
    setSelected(item);setManageOpen(true);setBusy("detail");setError("");setOk("");
    try{await loadDetail(item.id);}finally{setBusy("");}
  };

  const autoRepair=async()=>{
    if(!selected||busy)return;
    setBusy("auto-repair");setError("");setOk("");
    try{
      const result=await legacyControlApi.managedRepair(selected.id);
      await load(true);
      await loadDetail(selected.id);
      const errors=result.errors&&typeof result.errors==="object"?Object.entries(result.errors):[];
      if(errors.length){
        setError(pick(`تعمیر خودکار اجرا شد؛ موارد باقی‌مانده: ${errors.map(([key])=>transportLabel(key)).join("، ")}`,`Auto repair finished; remaining issues: ${errors.map(([key])=>transportLabel(key)).join(", ")}`));
      }else{
        setOk(pick("عیب‌یابی و تعمیر خودکار با موفقیت انجام شد.","Automatic diagnosis and repair completed."));
      }
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy("");
    }
  };

  const saveMode=async()=>{
    if(!selected||busy)return;
    setBusy("mode");setError("");setOk("");
    try{
      await legacyControlApi.setTunnelTransportMode(selected.id,{mode,transport:mode==="manual"?preferred:null});
      await load(true);await loadDetail(selected.id);
      setOk(pick("حالت مسیر ذخیره شد.","Transport mode saved."));
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{setBusy("");}
  };

  const toggle=async(item:AdminTunnel)=>{
    if(busy)return;
    setBusy(`toggle-${item.id}`);setError("");setOk("");
    try{await legacyControlApi.toggleTunnel(item.id);await load(true);setOk(pick("وضعیت تونل تغییر کرد.","Tunnel state updated."));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const remove=async(item:AdminTunnel)=>{
    if(!window.confirm(pick(`تونل #${item.id} حذف شود؟`,`Delete tunnel #${item.id}?`)))return;
    setBusy(`delete-${item.id}`);setError("");setOk("");
    try{await legacyControlApi.deleteTunnel(item.id);setManageOpen(false);setSelected(null);await load(true);setOk(pick("تونل حذف شد.","Tunnel deleted."));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const normalizedTransports=transportOrder.map(name=>{
    const found=transports.find(item=>lower(item.transport)===name);
    return found||({transport:name,priority:transportPriority[name],enabled:false,status:"missing",latency_ms:null,last_error:null,issue_code:"not_installed",dependency:name.endsWith("_2027")?"backhaul":null} as RuntimeRow);
  });

  const activeTransport=lower(diagnosis?.active_transport||selected?.active_transport||selected?.transport||"");
  const repairNeeded=Array.isArray(diagnosis?.repair_needed)?diagnosis?.repair_needed as string[]:[];

  return <Shell active="/admin/tunnels"><div className="page legacy-control-page">
    <div className="page-head">
      <div><h1>{pick("تانل‌ها","Tunnels")}</h1><small>{pick("ساخت، عیب‌یابی، تعمیر و Failover به‌صورت مدیریت‌شده و خودکار","Managed automatic provisioning, diagnosis, repair and failover")}</small></div>
      <button className="primary" type="button" onClick={openCreate}>＋ {pick("تونل جدید","New tunnel")}</button>
    </div>

    <div className="stats-grid">
      <Stat label={pick("کل تونل‌ها","Total tunnels")} value={String(rows.length)} icon="⤨"/>
      <Stat label={pick("آنلاین","Online")} value={String(onlineCount)} icon="●"/>
      <Stat label={pick("Degraded","Degraded")} value={String(degradedCount)} icon="◐"/>
      <Stat label={pick("آفلاین","Offline")} value={String(offlineCount)} icon="○"/>
    </div>

    {(error||ok)&&<div className={error?"alert error":"alert success"}>{error||ok}</div>}

    <Card>
      <div className="card-head"><div><b>{pick("مسیرهای ایران → خروج","Iran → Exit paths")}</b><small>{pick("فقط Pairهای آزاد و نودهای آنلاین برای ساخت نمایش داده می‌شوند","Only online nodes and unused pairs are offered for creation")}</small></div><label className="search">⌕ <input value={query} onChange={event=>setQuery(event.target.value)} placeholder={pick("جستجو…","Search…")}/></label></div>
      <div className="table-wrap"><table><thead><tr><th>#</th><th>{pick("ایران","Iran")}</th><th>{pick("خروج","Exit")}</th><th>{pick("حالت","Mode")}</th><th>{pick("مسیر فعال","Active")}</th><th>{pick("تاخیر","Latency")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>
        {loading?<tr><td colSpan={8}>{pick("در حال بارگذاری…","Loading…")}</td></tr>:filtered.length===0?<tr><td colSpan={8}>{pick("تونلی پیدا نشد.","No tunnels found.")}</td></tr>:filtered.map(item=>{
          const iran=nodeMap.get(item.iran_node_id);const exit=nodeMap.get(item.exit_node_id);
          return <tr key={item.id}><td><b>#{item.id}</b></td><td>{iran?.name||`#${item.iran_node_id}`}<small>{iran?.public_ip||""}</small></td><td>{exit?.name||`#${item.exit_node_id}`}<small>{exit?.public_ip||""}</small></td><td><Badge tone={lower(item.mode)==="auto"?"violet":"warn"}>{s(item.mode||"auto").toUpperCase()}</Badge></td><td>{transportLabel(item.active_transport||item.transport)}</td><td>{item.latency_ms!=null?`${item.latency_ms} ms`:"—"}</td><td><Badge tone={statusTone(item.status)}>{s(item.status||"offline")}</Badge></td><td><div className="actions"><button type="button" onClick={()=>void openManage(item)}>{pick("مدیریت","Manage")}</button><button type="button" onClick={()=>void toggle(item)} disabled={Boolean(busy)}>{item.is_active?pick("غیرفعال","Disable"):pick("فعال","Enable")}</button></div></td></tr>;
        })}
      </tbody></table></div>
    </Card>

    {createOpen&&<Modal title={pick("ساخت تونل خودکار","Automatic tunnel creation")} sub={pick("Backend تمام مسیرها را نصب و Manager بهترین مسیر را انتخاب می‌کند","Backend installs all paths and Manager selects the best one")} onClose={()=>!busy&&setCreateOpen(false)}>
      <form onSubmit={create} className="form-grid">
        <label>{pick("نود ایران","Iran node")}<select value={draft.iran_node_id} onChange={event=>{const iranId=Number(event.target.value);const exitId=exitNodes.find(item=>!usedPairs.has(`${iranId}:${item.id}`))?.id||0;setDraft(current=>({...current,iran_node_id:iranId,exit_node_id:exitId}));}}>{iranNodes.map(item=><option key={item.id} value={item.id}>{item.name} — {item.public_ip}</option>)}</select></label>
        <label>{pick("نود خروج آزاد","Available exit node")}<select value={draft.exit_node_id} onChange={event=>setDraft(current=>({...current,exit_node_id:Number(event.target.value)}))}><option value={0}>{pick("انتخاب کنید","Select")}</option>{availableExits.map(item=><option key={item.id} value={item.id}>{item.name} — {item.public_ip}</option>)}</select></label>
        <div className="form-note">{pick("نصب خودکار: MTunnel + Backhaul + SSH TUN، سپس QUIC/ARQ/KCP/TCP 2027 در صورت سالم بودن Carrier. حالت نهایی AUTO است.","Automatic install: MTunnel + Backhaul + SSH TUN, then QUIC/ARQ/KCP/TCP 2027 when the carrier is healthy. Final mode is AUTO.")}</div>
        {createStep&&<div className="alert">{createStep}</div>}
        <div className="modal-actions"><button type="button" onClick={()=>setCreateOpen(false)} disabled={Boolean(busy)}>{pick("انصراف","Cancel")}</button><button className="primary" type="submit" disabled={Boolean(busy)||!draft.iran_node_id||!draft.exit_node_id}>{busy==="create"?pick("در حال ساخت…","Creating…"):pick("ساخت و نصب خودکار","Create & auto install")}</button></div>
      </form>
    </Modal>}

    {manageOpen&&selected&&<Modal wide title={`${pick("مدیریت تونل","Manage tunnel")} #${selected.id}`} sub={`${nodeMap.get(selected.iran_node_id)?.name||selected.iran_node_id} → ${nodeMap.get(selected.exit_node_id)?.name||selected.exit_node_id}`} onClose={()=>!busy&&setManageOpen(false)}>
      <div className="stats-grid compact">
        <Stat label={pick("وضعیت","Status")} value={s(diagnosis?.status||selected.status||"offline")} icon="●"/>
        <Stat label={pick("مسیر فعال","Active transport")} value={transportLabel(activeTransport)} icon="⇄"/>
        <Stat label={pick("حالت","Mode")} value={s(diagnosis?.mode||mode||"auto").toUpperCase()} icon="A"/>
        <Stat label={pick("نیاز به تعمیر","Needs repair")} value={String(repairNeeded.length)} icon="⚙"/>
      </div>

      <div className="card-head"><div><b>{pick("Transportهای مدیریت‌شده","Managed transports")}</b><small>{pick("TP2027 به Backhaul وابسته است؛ خرابی Carrier جداگانه مشخص می‌شود","TP2027 depends on Backhaul; carrier failures are shown separately")}</small></div><button className="primary" type="button" onClick={()=>void autoRepair()} disabled={Boolean(busy)}>{busy==="auto-repair"?pick("در حال عیب‌یابی و تعمیر…","Diagnosing & repairing…"):pick("عیب‌یابی و تعمیر خودکار","Auto diagnose & repair")}</button></div>

      <div className="table-wrap"><table><thead><tr><th>{pick("اولویت","Priority")}</th><th>Transport</th><th>{pick("وضعیت","Status")}</th><th>{pick("وابستگی","Dependency")}</th><th>{pick("تاخیر","Latency")}</th><th>{pick("تشخیص","Diagnosis")}</th></tr></thead><tbody>
        {normalizedTransports.map(item=>{
          const name=lower(item.transport) as TransportName;
          return <tr key={name}><td>{n(item.priority)||transportPriority[name]}</td><td><b>{transportLabel(name)}</b>{activeTransport===name&&<small> ✓ {pick("فعال","Active")}</small>}</td><td><Badge tone={statusTone(item.status)}>{s(item.status||"missing")}</Badge></td><td>{name.endsWith("_2027")?"Backhaul":"—"}</td><td>{item.latency_ms!=null?`${n(item.latency_ms)} ms`:"—"}</td><td>{issueLabel(item.issue_code,fa)||s(item.last_error)||"—"}</td></tr>;
        })}
      </tbody></table></div>

      <div className="form-grid two">
        <label>{pick("حالت انتخاب مسیر","Transport selection mode")}<select value={mode} onChange={event=>setMode(event.target.value)}><option value="auto">AUTO</option><option value="manual">MANUAL</option></select></label>
        <label>{pick("مسیر دستی","Manual transport")}<select value={preferred} disabled={mode!=="manual"} onChange={event=>setPreferred(event.target.value as TransportName)}>{transportOrder.map(name=><option key={name} value={name}>{transportLabel(name)}</option>)}</select></label>
      </div>

      <div className="modal-actions"><button type="button" onClick={()=>void remove(selected)} disabled={Boolean(busy)}>{pick("حذف تونل","Delete tunnel")}</button><button type="button" onClick={()=>void loadDetail(selected.id)} disabled={Boolean(busy)}>{pick("تازه‌سازی وضعیت","Refresh")}</button><button className="primary" type="button" onClick={()=>void saveMode()} disabled={Boolean(busy)}>{pick("ذخیره حالت","Save mode")}</button></div>
    </Modal>}
  </div></Shell>;
}
