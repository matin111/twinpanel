"use client";

import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,AdminTunnel} from "../lib/admin-api";
import {TunnelTransportName,TunnelTransportRow,TunnelTransportState,tunnelTransportApi} from "../lib/tunnel-transport-api";
import {useI18n} from "../lib/i18n";

const transportLabels:Record<string,string>={
  kcp_2027:"KCP 2027",
  arq_2027:"ARQ 2027",
  quic_2027:"QUIC 2027",
  tcp_2027:"TCP 2027",
  backhaul:"Backhaul",
  mtunnel:"MTunnel",
  ssh_tun:"SSH TUN",
  ssh_relay:"SSH Relay",
};
const text=(value:unknown)=>value===null||value===undefined||value===""?"—":String(value);
const healthy=(value:unknown)=>["online","active","healthy","ok","ready","installed","true"].includes(String(value??"").toLowerCase());
const bad=(value:unknown)=>["offline","failed","error","down","stopped","false"].includes(String(value??"").toLowerCase());
const statusTone=(value:unknown):"ok"|"warn"|"bad"|"violet"=>healthy(value)?"ok":bad(value)?"bad":"warn";
const asRows=(state:TunnelTransportState|null):TunnelTransportRow[]=>state&&Array.isArray(state.transports)?state.transports:[];
const manualChoices:TunnelTransportName[]=["kcp_2027","arq_2027","quic_2027","tcp_2027","backhaul","mtunnel","ssh_tun"];

export function TunnelTransportRuntimePage(){
  const {pick}=useI18n();
  const [tunnels,setTunnels]=useState<AdminTunnel[]>([]);
  const [selected,setSelected]=useState(0);
  const [state,setState]=useState<TunnelTransportState|null>(null);
  const [diagnosis,setDiagnosis]=useState<Record<string,unknown>|null>(null);
  const [health,setHealth]=useState<Record<string,unknown>|null>(null);
  const [manualTransport,setManualTransport]=useState<TunnelTransportName>("kcp_2027");
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const loadTunnels=async()=>{
    setError("");
    try{
      const rows=await adminApi.tunnels();
      setTunnels(rows);
      const queryId=typeof window!=="undefined"?Number(new URLSearchParams(window.location.search).get("tunnel")||0):0;
      setSelected(current=>{
        if(current&&rows.some(row=>row.id===current))return current;
        if(queryId&&rows.some(row=>row.id===queryId))return queryId;
        return rows[0]?.id||0;
      });
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
      if(manualChoices.includes(preferred))setManualTransport(preferred);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{if(showLoading)setLoading(false);}
  };

  useEffect(()=>{void loadTunnels();},[]);
  useEffect(()=>{if(selected)void loadSelected(selected);else setLoading(false);},[selected]);

  const selectedTunnel=tunnels.find(row=>row.id===selected);
  const transports=useMemo(()=>asRows(state),[state]);
  const onlineCount=transports.filter(row=>healthy(row.status)).length;
  const enabledCount=transports.filter(row=>Boolean(row.enabled)).length;
  const modernOnline=transports.filter(row=>String(row.transport||"").endsWith("_2027")&&healthy(row.status)).length;

  const run=async(key:string,label:string,fn:()=>Promise<unknown>,refresh=true)=>{
    if(busy||!selected)return;
    setBusy(key);setError("");setOk("");
    try{
      const result=await fn();
      if(key==="diagnose")setDiagnosis(result as Record<string,unknown>);
      if(key==="health")setHealth(result as Record<string,unknown>);
      setOk(label);
      if(refresh)await loadSelected(selected,false);
      await loadTunnels();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  const setAuto=()=>void run("mode-auto",pick("مدیریت مسیر روی خودکار قرار گرفت","Path management set to Auto"),()=>tunnelTransportApi.setMode(selected,{mode:"auto"}));
  const setManual=()=>void run("mode-manual",pick("مسیر دستی ذخیره شد","Manual path saved"),()=>tunnelTransportApi.setMode(selected,{mode:"manual",transport:manualTransport}));

  return <Shell active="/admin/tunnel-transports"><div className="page">
    <div className="page-head"><div><h1>{pick("ترانسپورت‌ها","Transports")}</h1><small>{pick("صفحه پیشرفته برای مشاهده، عیب‌یابی و Failover مسیرهای داخلی هر تانل","Advanced page for transport visibility, diagnostics and failover")}</small></div><button className="ghost" disabled={loading||Boolean(busy)} onClick={()=>{void loadTunnels();if(selected)void loadSelected(selected);}}>{pick("بروزرسانی","Refresh")}</button></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}

    <div className="stats dashboard-stats">
      <Stat label={pick("تانل‌های منطقی","Logical tunnels")} value={String(tunnels.length)} icon="⤨"/>
      <Stat label={pick("ترانسپورت ثبت‌شده","Registered transports")} value={String(transports.length)} icon="⌁"/>
      <Stat label={pick("ترانسپورت فعال","Enabled transports")} value={String(enabledCount)} icon="◉"/>
      <Stat label={pick("مسیر مدرن سالم","Healthy modern paths")} value={String(modernOnline)} icon="✓"/>
      <Stat label={pick("مسیر جاری","Active path")} value={transportLabels[String(state?.active_transport||"")]||text(state?.active_transport)} icon="⇄"/>
    </div>

    <div className="module-grid two">
      <Card>
        <div className="card-head"><div><b>{pick("انتخاب تانل","Select tunnel")}</b><small>{pick("هر جفت ایران → خارج، ترانسپورت‌های مستقل خودش را دارد","Each Iran → Exit pair owns its own transports")}</small></div></div>
        <label className="field"><span>{pick("تانل","Tunnel")}</span><select value={selected} onChange={e=>setSelected(Number(e.target.value))}><option value={0}>{pick("انتخاب کنید","Select")}</option>{tunnels.map(t=><option key={t.id} value={t.id}>#{t.id} · Iran #{t.iran_node_id} → Exit #{t.exit_node_id} · {t.status||"—"}</option>)}</select></label>
        {selectedTunnel&&<div className="runtime-info-list"><div><span>ID</span><b>#{selectedTunnel.id}</b></div><div><span>{pick("مسیر","Route")}</span><b>#{selectedTunnel.iran_node_id} → #{selectedTunnel.exit_node_id}</b></div><div><span>{pick("وضعیت","Status")}</span><Badge tone={statusTone(selectedTunnel.status)}>{selectedTunnel.status||"—"}</Badge></div><div><span>{pick("تاخیر","Latency")}</span><b>{selectedTunnel.latency_ms==null?"—":`${selectedTunnel.latency_ms} ms`}</b></div></div>}
      </Card>

      <Card>
        <div className="card-head"><div><b>{pick("سیاست انتخاب مسیر","Path selection policy")}</b><small>{pick("Auto پیشنهاد می‌شود؛ Manual فقط برای عیب‌یابی یا تست","Auto is recommended; Manual is for diagnostics/testing")}</small></div><Badge tone={state?.mode==="manual"?"violet":"ok"}>{String(state?.mode||"—")}</Badge></div>
        <div className="action-row"><button className={state?.mode==="auto"?"primary":"ghost"} disabled={!selected||Boolean(busy)} onClick={setAuto}>{busy==="mode-auto"?"…":"Auto"}</button><select value={manualTransport} onChange={e=>setManualTransport(e.target.value as TunnelTransportName)}>{manualChoices.map(name=><option key={name} value={name}>{transportLabels[name]}</option>)}</select><button className={state?.mode==="manual"?"primary":"ghost"} disabled={!selected||Boolean(busy)} onClick={setManual}>{busy==="mode-manual"?"…":pick("ذخیره Manual","Save Manual")}</button></div>
        <div className="runtime-info-list"><div><span>{pick("ترجیحی","Preferred")}</span><b>{transportLabels[String(state?.preferred_transport||"")]||text(state?.preferred_transport)}</b></div><div><span>{pick("فعال فعلی","Active")}</span><b>{transportLabels[String(state?.active_transport||"")]||text(state?.active_transport)}</b></div><div><span>{pick("آخرین سوییچ","Last switch")}</span><b>{state?.last_switch_at?new Date(String(state.last_switch_at)).toLocaleString("fa-IR"):"—"}</b></div></div>
      </Card>
    </div>

    <Card>
      <div className="card-head"><div><b>{pick("وضعیت ترانسپورت‌ها","Transport status")}</b><small>{pick("KCP / ARQ / QUIC / TCP مسیرهای مدرن اصلی هستند؛ موارد Legacy فقط در صورت وجود نمایش داده می‌شوند.","KCP / ARQ / QUIC / TCP are primary modern paths; legacy rows are shown only when present.")}</small></div></div>
      {loading?<div className="runtime-loading">{pick("در حال دریافت…","Loading…")}</div>:transports.length?<div className="module-grid three">{transports.map((row,index)=>{
        const name=String(row.transport||`transport-${index}`);
        const isModern=name.endsWith("_2027");
        return <div className="card transport-runtime-card" key={String(row.id||name)}><div className="card-head"><div><b>{transportLabels[name]||name}</b><small>{isModern?pick("مسیر مدرن","Modern path"):pick("Legacy / fallback","Legacy / fallback")} · Priority {text(row.priority)}</small></div><Badge tone={statusTone(row.status)}>{text(row.status)}</Badge></div><div className="runtime-info-list"><div><span>{pick("فعال","Enabled")}</span><b>{row.enabled?pick("بله","Yes"):pick("خیر","No")}</b></div><div><span>Latency</span><b>{row.latency_ms==null?"—":`${row.latency_ms} ms`}</b></div><div><span>{pick("آخرین سلامت","Last healthy")}</span><b>{row.last_healthy_at?new Date(String(row.last_healthy_at)).toLocaleString("fa-IR"):"—"}</b></div></div>{row.last_error&&<div className="runtime-error compact" dir="ltr">{String(row.last_error)}</div>}</div>;
      })}</div>:<div className="runtime-empty">{pick("برای این تانل هنوز ترانسپورتی ثبت نشده است.","No transports are registered for this tunnel yet.")}</div>}
    </Card>

    <div className="module-grid two">
      <Card><div className="card-head"><div><b>{pick("عیب‌یابی و تعمیر","Diagnostics & repair")}</b><small>{pick("تعمیر مدیریت‌شده فقط مسیرهای مدرن لازم را بازسازی می‌کند و به تانل‌های دیگر همان ایران دست نمی‌زند.","Managed repair rebuilds only the required modern path for this tunnel and does not touch sibling Exit tunnels.")}</small></div></div><div className="action-grid"><button className="primary-soft" disabled={!selected||Boolean(busy)} onClick={()=>void run("repair",pick("تعمیر مدیریت‌شده انجام شد","Managed repair finished"),()=>tunnelTransportApi.managedRepair(selected))}>{busy==="repair"?"…":pick("تعمیر خودکار","Auto repair")}</button><button className="ghost" disabled={!selected||Boolean(busy)} onClick={()=>void run("diagnose",pick("تشخیص دریافت شد","Diagnosis loaded"),()=>tunnelTransportApi.managedDiagnose(selected),false)}>{busy==="diagnose"?"…":pick("تشخیص","Diagnose")}</button><button className="ghost" disabled={!selected||Boolean(busy)} onClick={()=>void run("health",pick("Health دریافت شد","Health loaded"),()=>tunnelTransportApi.health(selected),false)}>{busy==="health"?"…":"Tunnel Health"}</button></div></Card>

      <Card><div className="card-head"><div><b>{pick("ابزار Legacy اختیاری","Optional legacy tools")}</b><small>{pick("این ابزارها به‌صورت خودکار ساخته نمی‌شوند؛ فقط برای مهاجرت یا عیب‌یابی دستی هستند.","These are not auto-provisioned; use only for migration or manual diagnostics.")}</small></div></div><div className="action-grid"><button className="ghost" disabled={!selected||Boolean(busy)} onClick={()=>void run("install-backhaul",pick("Backhaul نصب/بازسازی شد","Backhaul install/rebuild finished"),()=>tunnelTransportApi.installBackhaul(selected))}>{busy==="install-backhaul"?"…":"Backhaul"}</button><button className="ghost" disabled={!selected||Boolean(busy)} onClick={()=>void run("install-mtunnel",pick("MTunnel نصب/بازسازی شد","MTunnel install/rebuild finished"),()=>tunnelTransportApi.installMtunnel(selected))}>{busy==="install-mtunnel"?"…":"MTunnel"}</button><button className="ghost" disabled={!selected||Boolean(busy)} onClick={()=>void run("install-ssh",pick("SSH TUN نصب/بازسازی شد","SSH TUN install/rebuild finished"),()=>tunnelTransportApi.installSsh(selected))}>{busy==="install-ssh"?"…":"SSH TUN"}</button></div></Card>
    </div>

    {(diagnosis||health)&&<div className="module-grid two">{diagnosis&&<Card><div className="card-head"><b>{pick("خروجی تشخیص","Diagnosis")}</b><button className="mini-btn" onClick={()=>setDiagnosis(null)}>×</button></div><pre className="runtime-log" dir="ltr">{JSON.stringify(diagnosis,null,2)}</pre></Card>}{health&&<Card><div className="card-head"><b>Tunnel Health</b><button className="mini-btn" onClick={()=>setHealth(null)}>×</button></div><pre className="runtime-log" dir="ltr">{JSON.stringify(health,null,2)}</pre></Card>}</div>}
  </div></Shell>;
}
