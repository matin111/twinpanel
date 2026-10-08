"use client";

import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,AdminTunnel} from "../lib/admin-api";
import {
  ModernTransportName,
  ModernTransportState,
  TunnelTransportRow,
  tunnelTransportApi,
} from "../lib/tunnel-transport-api";
import {useI18n} from "../lib/i18n";

const labels:Record<ModernTransportName,string>={
  kernel_gre:"Kernel GRE",
  gost_tun:"GOST TUN / WSS",
  amneziawg:"AmneziaWG 3.1",
  netrix:"Netrix TUN",
};
const families:Record<ModernTransportName,string>={
  kernel_gre:"Kernel L3 / GRE",
  gost_tun:"TCP + WSS/TLS + TUN",
  amneziawg:"Obfuscated UDP / L3",
  netrix:"Licensed Multi-Path / L3",
};
const order:ModernTransportName[]=["kernel_gre","gost_tun","amneziawg","netrix"];
const value=(v:unknown)=>v===null||v===undefined||v===""?"—":String(v);
const ok=(v:unknown)=>String(v??"").toLowerCase()==="online";
const pending=(v:unknown)=>["installing","testing","pending"].includes(String(v??"").toLowerCase());
const tone=(v:unknown):"ok"|"warn"|"bad"=>ok(v)?"ok":pending(v)?"warn":"bad";

export function ModernTransportCanaryPage(){
  const {pick}=useI18n();
  const [tunnels,setTunnels]=useState<AdminTunnel[]>([]);
  const [selected,setSelected]=useState(0);
  const [state,setState]=useState<ModernTransportState|null>(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");

  const loadTunnels=async()=>{
    const rows=await adminApi.tunnels();
    setTunnels(rows);
    setSelected(current=>current&&rows.some(row=>row.id===current)?current:(rows[0]?.id||0));
  };

  const load=async(id:number,spinner=true)=>{
    if(!id){setState(null);if(spinner)setLoading(false);return;}
    if(spinner)setLoading(true);
    try{
      const result=await tunnelTransportApi.modernTransports(id);
      setState(result);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{if(spinner)setLoading(false);}
  };

  useEffect(()=>{
    (async()=>{
      setError("");
      try{await loadTunnels();}
      catch(e){setError(e instanceof Error?e.message:String(e));setLoading(false);}
    })();
  },[]);

  useEffect(()=>{if(selected)void load(selected);},[selected]);

  const rows=useMemo(()=>{
    const source=Array.isArray(state?.transports)?state!.transports!:[];
    const map=new Map(source.map(item=>[String(item.transport),item]));
    return order.map(name=>map.get(name)||({transport:name,status:"not_installed",enabled:false,label:labels[name],family:families[name]} as TunnelTransportRow));
  },[state]);

  const onlineCount=rows.filter(row=>ok(row.status)).length;
  const selectedTunnel=tunnels.find(row=>row.id===selected);

  const run=async(name:ModernTransportName,action:"install"|"remove")=>{
    if(!selected||busy)return;
    const key=`${action}-${name}`;
    const title=labels[name];
    const confirmText=action==="install"
      ?pick(`${title} روی تونل #${selected} به‌صورت Canary نصب و تست شود؟ مسیر فعال فعلی تغییر نمی‌کند.`,`Install and test ${title} as a canary on tunnel #${selected}? The active route will not change.`)
      :pick(`${title} از تونل #${selected} پاک شود؟`, `Remove ${title} from tunnel #${selected}?`);
    if(!window.confirm(confirmText))return;
    setBusy(key);setError("");setMessage("");
    try{
      if(action==="install")await tunnelTransportApi.installModern(selected,name);
      else await tunnelTransportApi.removeModern(selected,name);
      await load(selected,false);
      setMessage(action==="install"
        ?pick(`${title} تست شد. فقط نتیجه Traffic Probe تعیین می‌کند Online باشد.`,`${title} was tested. Only the traffic probe can mark it Online.`)
        :pick(`${title} پاک شد.`,`${title} removed.`));
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
      await load(selected,false);
    }finally{setBusy("");}
  };

  return <Shell active="/admin/tunnels"><div className="page legacy-control-page">
    <div className="page-head"><div><h1>{pick("آزمایش Transportهای جدید","Modern transport canary")}</h1><small>{pick("مسیر فعلی Backhaul دست‌نخورده می‌ماند؛ هر گزینه روی Route آزمایشی مستقل تست می‌شود.","Backhaul stays untouched; every candidate is tested on an isolated route.")}</small></div><div className="action-row"><button className="ghost" disabled={loading||!!busy} onClick={()=>selected&&void load(selected)}>{pick("بروزرسانی","Refresh")}</button><button className="primary-soft" onClick={()=>window.location.href="/admin/tunnels"}>{pick("بازگشت به تونل‌ها","Back to tunnels")}</button></div></div>

    {error&&<div className="runtime-error" dir="auto">{error}</div>}
    {message&&<div className="runtime-success">{message}</div>}

    <div className="stats dashboard-stats">
      <Stat label={pick("کاندیداها","Candidates")} value={String(order.length)}/>
      <Stat label={pick("Traffic PASS","Traffic PASS")} value={String(onlineCount)}/>
      <Stat label={pick("مسیر Production","Production route")} value="Backhaul"/>
      <Stat label={pick("فعال فعلی","Current active")} value={value(state?.active_transport)}/>
    </div>

    <Card>
      <div className="card-head"><div><b>{pick("تونل آزمایشی","Canary tunnel")}</b><small>{pick("فقط جفت نود انتخابی تغییر می‌کند و Route کاربران عوض نمی‌شود.","Only the selected node pair is touched; user routing is not switched.")}</small></div></div>
      <div className="setting-grid">
        <label className="field"><span>{pick("تونل","Tunnel")}</span><select value={selected} onChange={e=>setSelected(Number(e.target.value))}><option value={0}>{pick("انتخاب کنید","Select")}</option>{tunnels.map(item=><option key={item.id} value={item.id}>#{item.id} · Iran #{item.iran_node_id} → Exit #{item.exit_node_id}</option>)}</select></label>
        <div className="field"><span>{pick("وضعیت Production","Production status")}</span><b>{selectedTunnel?.status||"—"}</b></div>
        <div className="field"><span>{pick("Transport فعال","Active transport")}</span><b>{selectedTunnel?.active_transport||selectedTunnel?.transport||"—"}</b></div>
      </div>
    </Card>

    <Card>
      <div className="card-head"><div><b>{pick("Transportهای Canary","Canary transports")}</b><small>{pick("Online یعنی Interface + Peer Ping + TCP Egress + UDP Egress همگی PASS شده‌اند. این گزینه‌ها هنوز قابل انتخاب به‌عنوان Production نیستند.","Online means interface, peer ping, TCP egress and UDP egress all passed. These candidates are not selectable for production yet.")}</small></div><Badge tone="warn">CANARY</Badge></div>
      {loading?<div className="runtime-loading">{pick("در حال خواندن وضعیت…","Loading status…")}</div>:<div className="module-grid two">{rows.map(row=>{
        const name=String(row.transport) as ModernTransportName;
        const status=String(row.status||"not_installed");
        const runtime=(row.runtime&&typeof row.runtime==="object"?row.runtime:{}) as Record<string,unknown>;
        const installed=status!=="not_installed";
        return <div className="card transport-runtime-card" key={name}>
          <div className="card-head"><div><b>{labels[name]}</b><small>{value(row.family||families[name])}</small></div><Badge tone={tone(status)}>{status}</Badge></div>
          <div className="runtime-info-list">
            <div><span>{pick("Priority آزمایشی","Canary priority")}</span><b>{value(row.priority)}</b></div>
            <div><span>{pick("Interface","Interface")}</span><b dir="ltr">{value(runtime.interface)}</b></div>
            <div><span>{pick("Latency","Latency")}</span><b>{row.latency_ms==null?"—":`${row.latency_ms} ms`}</b></div>
            <div><span>{pick("قابل انتخاب Production","Production selectable")}</span><b>{pick("خیر","No")}</b></div>
          </div>
          {row.last_error&&<div className="runtime-error compact" dir="ltr">{String(row.last_error)}</div>}
          <div className="action-row">
            <button className="primary-soft" disabled={!selected||!!busy} onClick={()=>void run(name,"install")}>{busy===`install-${name}`?"…":installed?pick("نصب مجدد و تست","Reinstall & test"):pick("نصب و تست","Install & test")}</button>
            <button className="ghost" disabled={!selected||!!busy||!installed} onClick={()=>void run(name,"remove")}>{busy===`remove-${name}`?"…":pick("پاک‌سازی","Remove")}</button>
          </div>
          {name==="netrix"&&<small className="muted">{pick("نیازمند باینری و لایسنس معتبر Netrix روی سرور TwinPanel است؛ لایسنس دور زده نمی‌شود.","Requires your valid licensed Netrix binary on the TwinPanel server; licensing is never bypassed.")}</small>}
        </div>;
      })}</div>}
    </Card>

    <div className="runtime-warning">{pick("ترتیب تست پیشنهادی: Kernel GRE → GOST TUN/WSS → AmneziaWG 3.1 → Netrix. تا قبل از PASS و مرحله Promotion، Backhaul مسیر Production باقی می‌ماند.","Recommended test order: Kernel GRE → GOST TUN/WSS → AmneziaWG 3.1 → Netrix. Backhaul remains production until a candidate passes and is promoted.")}</div>
  </div></Shell>;
}
