"use client";

import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,AdminTunnel} from "../lib/admin-api";
import {TunnelTransportName,TunnelTransportRow,TunnelTransportState,tunnelTransportApi} from "../lib/tunnel-transport-api";
import {useI18n} from "../lib/i18n";

const transportLabels:Record<string,string>={ssh_tun:"SSH TUN",backhaul:"Backhaul",mtunnel:"MTunnel"};
const text=(value:unknown)=>value===null||value===undefined||value===""?"—":String(value);
const healthy=(value:unknown)=>["online","active","healthy","ok","ready","installed","true"].includes(String(value??"").toLowerCase());
const bad=(value:unknown)=>["offline","failed","error","down","stopped","false"].includes(String(value??"").toLowerCase());
const statusTone=(value:unknown):"ok"|"warn"|"bad"|"violet"=>healthy(value)?"ok":bad(value)?"bad":"warn";
const asRows=(state:TunnelTransportState|null):TunnelTransportRow[]=>state&&Array.isArray(state.transports)?state.transports:[];

export function TunnelTransportRuntimePage(){
  const {pick}=useI18n();
  const [tunnels,setTunnels]=useState<AdminTunnel[]>([]);
  const [selected,setSelected]=useState(0);
  const [state,setState]=useState<TunnelTransportState|null>(null);
  const [health,setHealth]=useState<Record<string,unknown>|null>(null);
  const [mtunnel,setMtunnel]=useState<Record<string,unknown>|null>(null);
  const [backhaul,setBackhaul]=useState<Record<string,unknown>|null>(null);
  const [manualTransport,setManualTransport]=useState<TunnelTransportName>("backhaul");
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const loadTunnels=async()=>{
    setError("");
    try{
      const rows=await adminApi.tunnels();
      setTunnels(rows);
      setSelected(current=>current&&rows.some(row=>row.id===current)?current:(rows[0]?.id||0));
    }catch(e){setError(e instanceof Error?e.message:String(e));}
  };

  const loadSelected=async(id:number,showLoading=true)=>{
    if(!id){setState(null);return;}
    if(showLoading)setLoading(true);
    setError("");
    try{
      const result=await tunnelTransportApi.transports(id);
      setState(result);
      const preferred=String(result.preferred_transport||result.active_transport||"") as TunnelTransportName;
      if(["ssh_tun","backhaul","mtunnel"].includes(preferred))setManualTransport(preferred);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{if(showLoading)setLoading(false);}
  };

  useEffect(()=>{void loadTunnels();},[]);
  useEffect(()=>{if(selected)void loadSelected(selected);else setLoading(false);},[selected]);

  const selectedTunnel=tunnels.find(row=>row.id===selected);
  const transports=useMemo(()=>asRows(state),[state]);
  const onlineCount=transports.filter(row=>healthy(row.status)).length;
  const enabledCount=transports.filter(row=>Boolean(row.enabled)).length;

  const run=async(key:string,label:string,fn:()=>Promise<unknown>,after=true)=>{
    if(busy||!selected)return;
    setBusy(key);setError("");setOk("");
    try{
      const result=await fn();
      if(key==="health")setHealth(result as Record<string,unknown>);
      if(key==="mt-health")setMtunnel(result as Record<string,unknown>);
      if(key==="backhaul-status")setBackhaul(result as Record<string,unknown>);
      setOk(label);
      if(after)await loadSelected(selected,false);
      await loadTunnels();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  const setAuto=()=>void run("mode-auto",pick("حالت انتخاب Transport روی Auto قرار گرفت","Transport selection set to Auto"),()=>tunnelTransportApi.setMode(selected,{mode:"auto"}));
  const setManual=()=>void run("mode-manual",pick("Transport دستی ذخیره شد","Manual transport saved"),()=>tunnelTransportApi.setMode(selected,{mode:"manual",transport:manualTransport}));

  return <Shell active="/admin/tunnel-transports"><div className="page">
    <div className="page-head"><div><h1>{pick("مدیریت Transport تونل","Tunnel Transport Manager")}</h1><small>{pick("مدیریت Transportهای فیزیکی مستقل برای مسیر ایران → خروجی","Manage independent physical transports for Iran → Exit tunnels")}</small></div><button className="ghost" disabled={loading||Boolean(busy)} onClick={()=>{void loadTunnels();if(selected)void loadSelected(selected);}}>{pick("بروزرسانی","Refresh")}</button></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats dashboard-stats">
      <Stat label={pick("تونل‌های منطقی","Logical tunnels")} value={String(tunnels.length)} icon="⤨"/>
      <Stat label={pick("Transport ثبت‌شده","Registered transports")} value={String(transports.length)} icon="⌁"/>
      <Stat label={pick("Transport فعال","Enabled transports")} value={String(enabledCount)} icon="◉"/>
      <Stat label={pick("Transport سالم","Healthy transports")} value={String(onlineCount)} icon="✓"/>
      <Stat label={pick("Transport جاری","Active transport")} value={transportLabels[String(state?.active_transport||"")]||text(state?.active_transport)} icon="⇄"/>
    </div>

    <div className="module-grid two">
      <Card>
        <div className="card-head"><div><b>{pick("انتخاب تونل","Select tunnel")}</b><small>{pick("هر Transport فقط برای همین جفت نود مدیریت می‌شود","Each transport is managed for this node pair only")}</small></div></div>
        <label className="field"><span>{pick("تونل","Tunnel")}</span><select value={selected} onChange={e=>setSelected(Number(e.target.value))}><option value={0}>{pick("انتخاب کنید","Select")}</option>{tunnels.map(t=><option key={t.id} value={t.id}>#{t.id} · Iran #{t.iran_node_id} → Exit #{t.exit_node_id} · {t.status||"—"}</option>)}</select></label>
        {selectedTunnel&&<div className="runtime-info-list"><div><span>ID</span><b>#{selectedTunnel.id}</b></div><div><span>{pick("مسیر","Route")}</span><b>#{selectedTunnel.iran_node_id} → #{selectedTunnel.exit_node_id}</b></div><div><span>{pick("وضعیت","Status")}</span><Badge tone={statusTone(selectedTunnel.status)}>{selectedTunnel.status||"—"}</Badge></div><div><span>{pick("تاخیر","Latency")}</span><b>{selectedTunnel.latency_ms==null?"—":`${selectedTunnel.latency_ms} ms`}</b></div></div>}
      </Card>

      <Card>
        <div className="card-head"><div><b>{pick("سیاست انتخاب Transport","Transport selection policy")}</b><small>{pick("Auto برای Failover خودکار؛ Manual برای قفل روی یک Transport","Auto for failover; Manual to pin one transport")}</small></div><Badge tone={state?.mode==="manual"?"violet":"ok"}>{String(state?.mode||"—")}</Badge></div>
        <div className="action-row"><button className={state?.mode==="auto"?"primary":"ghost"} disabled={!selected||Boolean(busy)} onClick={setAuto}>{busy==="mode-auto"?"…":"Auto"}</button><select value={manualTransport} onChange={e=>setManualTransport(e.target.value as TunnelTransportName)}><option value="backhaul">Backhaul</option><option value="mtunnel">MTunnel</option><option value="ssh_tun">SSH TUN</option></select><button className={state?.mode==="manual"?"primary":"ghost"} disabled={!selected||Boolean(busy)} onClick={setManual}>{busy==="mode-manual"?"…":pick("ذخیره Manual","Save Manual")}</button></div>
        <div className="runtime-info-list"><div><span>{pick("ترجیحی","Preferred")}</span><b>{transportLabels[String(state?.preferred_transport||"")]||text(state?.preferred_transport)}</b></div><div><span>{pick("فعال فعلی","Active")}</span><b>{transportLabels[String(state?.active_transport||"")]||text(state?.active_transport)}</b></div><div><span>{pick("آخرین سوییچ","Last switch")}</span><b>{state?.last_switch_at?new Date(String(state.last_switch_at)).toLocaleString("fa-IR"):"—"}</b></div></div>
      </Card>
    </div>

    <Card>
      <div className="card-head"><div><b>{pick("Transportهای فیزیکی","Physical transports")}</b><small>{pick("وضعیت مستقیماً از tunnel_transports Backend خوانده می‌شود","Status is read directly from backend tunnel transports")}</small></div></div>
      {loading?<div className="runtime-loading">{pick("در حال دریافت Transportها...","Loading transports...")}</div>:transports.length?<div className="module-grid three">{transports.map((row,index)=>{
        const name=String(row.transport||`transport-${index}`);
        return <div className="card transport-runtime-card" key={String(row.id||name)}><div className="card-head"><div><b>{transportLabels[name]||name}</b><small>Priority {text(row.priority)}</small></div><Badge tone={statusTone(row.status)}>{text(row.status)}</Badge></div><div className="runtime-info-list"><div><span>{pick("فعال","Enabled")}</span><b>{row.enabled?pick("بله","Yes"):pick("خیر","No")}</b></div><div><span>{pick("Latency","Latency")}</span><b>{row.latency_ms==null?"—":`${row.latency_ms} ms`}</b></div><div><span>{pick("آخرین سلامت","Last healthy")}</span><b>{row.last_healthy_at?new Date(String(row.last_healthy_at)).toLocaleString("fa-IR"):"—"}</b></div></div>{row.last_error&&<div className="runtime-error compact" dir="ltr">{String(row.last_error)}</div>}</div>;
      })}</div>:<div className="runtime-empty">{pick("برای این تونل هنوز Transport ثبت نشده است.","No transports are registered for this tunnel yet.")}</div>}
    </Card>

    <div className="module-grid two">
      <Card><div className="card-head"><div><b>{pick("نصب Transport","Install transport")}</b><small>{pick("هر Transport مستقل نصب می‌شود؛ نصب یکی دیگری را حذف نمی‌کند","Each transport installs independently; installing one does not remove another")}</small></div></div><div className="action-grid"><button className="ghost" disabled={!selected||Boolean(busy)} onClick={()=>void run("install-ssh",pick("SSH TUN نصب شد","SSH TUN installed"),()=>tunnelTransportApi.installSsh(selected))}>{busy==="install-ssh"?"…":"Install SSH TUN"}</button><button className="ghost" disabled={!selected||Boolean(busy)} onClick={()=>void run("install-backhaul",pick("Backhaul نصب شد","Backhaul installed"),()=>tunnelTransportApi.installBackhaul(selected))}>{busy==="install-backhaul"?"…":"Install Backhaul"}</button><button className="ghost" disabled={!selected||Boolean(busy)} onClick={()=>void run("install-mtunnel",pick("MTunnel نصب شد","MTunnel installed"),()=>tunnelTransportApi.installMtunnel(selected))}>{busy==="install-mtunnel"?"…":"Install MTunnel"}</button><button className="ghost" disabled={!selected||Boolean(busy)} onClick={()=>void run("repair-mtunnel",pick("MTunnel تعمیر شد","MTunnel repaired"),()=>tunnelTransportApi.repairMtunnel(selected))}>{busy==="repair-mtunnel"?"…":"Repair MTunnel"}</button></div></Card>
      <Card><div className="card-head"><div><b>{pick("Health و Status","Health & Status")}</b><small>{pick("بدون تغییر تنظیمات، فقط وضعیت Runtime را می‌خواند","Read-only runtime checks")}</small></div></div><div className="action-grid"><button className="ghost" disabled={!selected||Boolean(busy)} onClick={()=>void run("health",pick("Health تونل دریافت شد","Tunnel health loaded"),()=>tunnelTransportApi.health(selected),false)}>{busy==="health"?"…":pick("Tunnel Health","Tunnel Health")}</button><button className="ghost" disabled={!selected||Boolean(busy)} onClick={()=>void run("mt-health",pick("Health MTunnel دریافت شد","MTunnel health loaded"),()=>tunnelTransportApi.mtunnelHealth(selected),false)}>{busy==="mt-health"?"…":"MTunnel Health"}</button><button className="ghost" disabled={!selected||Boolean(busy)} onClick={()=>void run("backhaul-status",pick("وضعیت Backhaul دریافت شد","Backhaul status loaded"),()=>tunnelTransportApi.backhaulStatus(selected),false)}>{busy==="backhaul-status"?"…":"Backhaul Status"}</button></div></Card>
    </div>

    {(health||mtunnel||backhaul)&&<div className="module-grid three">{health&&<Card><div className="card-head"><b>Tunnel Health</b><button className="mini-btn" onClick={()=>setHealth(null)}>×</button></div><pre className="runtime-log" dir="ltr">{JSON.stringify(health,null,2)}</pre></Card>}{mtunnel&&<Card><div className="card-head"><b>MTunnel Health</b><button className="mini-btn" onClick={()=>setMtunnel(null)}>×</button></div><pre className="runtime-log" dir="ltr">{JSON.stringify(mtunnel,null,2)}</pre></Card>}{backhaul&&<Card><div className="card-head"><b>Backhaul Status</b><button className="mini-btn" onClick={()=>setBackhaul(null)}>×</button></div><pre className="runtime-log" dir="ltr">{JSON.stringify(backhaul,null,2)}</pre></Card>}</div>}
  </div></Shell>;
}
