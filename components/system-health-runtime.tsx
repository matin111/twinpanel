"use client";

import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {AnyRow,parityApi} from "../lib/admin-parity-api";
import {useI18n} from "../lib/i18n";

const asRecord=(value:unknown):AnyRow=>value&&typeof value==="object"&&!Array.isArray(value)?value as AnyRow:{};
const text=(value:unknown)=>value===null||value===undefined?"—":typeof value==="boolean"?(value?"true":"false"):typeof value==="object"?JSON.stringify(value):String(value);
const isHealthy=(value:unknown)=>{
  if(typeof value==="boolean")return value;
  const s=String(value??"").toLowerCase();
  return ["ok","healthy","online","active","running","ready","success","true","up"].includes(s);
};
const tone=(value:unknown):"ok"|"warn"|"bad"|"violet"=>{
  const s=String(value??"").toLowerCase();
  if(isHealthy(value))return "ok";
  if(["false","failed","error","offline","down","critical","inactive","stopped"].includes(s))return "bad";
  return "warn";
};
const protocolName=(key:string)=>({cisco:"Cisco / OpenConnect",ocserv:"Cisco / OpenConnect",openvpn:"OpenVPN",wireguard:"WireGuard",wg:"WireGuard",l2tp:"L2TP / IPsec",ipsec:"L2TP / IPsec",v2ray:"V2Ray / Xray",xray:"V2Ray / Xray"} as Record<string,string>)[key.toLowerCase()]||key;

function RecordGrid({data}:{data:AnyRow}){
  const entries=Object.entries(data).filter(([,value])=>typeof value!=="object"||value===null);
  if(!entries.length)return null;
  return <div className="runtime-info-list">{entries.slice(0,16).map(([key,value])=><div key={key}><span>{key.replaceAll("_"," ")}</span><b dir="auto">{text(value)}</b></div>)}</div>;
}

export function SystemHealthRuntimePage(){
  const {pick}=useI18n();
  const [health,setHealth]=useState<AnyRow>({});
  const [security,setSecurity]=useState<AnyRow>({});
  const [core,setCore]=useState<AnyRow>({});
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    const result=await Promise.allSettled([parityApi.systemHealth(),parityApi.securityOverview(),parityApi.coreProtocols()]);
    if(result[0].status==="fulfilled")setHealth(result[0].value);
    if(result[1].status==="fulfilled")setSecurity(result[1].value);
    if(result[2].status==="fulfilled")setCore(result[2].value);
    const failed=result.find(item=>item.status==="rejected");
    if(failed&&failed.status==="rejected")setError(failed.reason instanceof Error?failed.reason.message:String(failed.reason));
    setLoading(false);
  };
  useEffect(()=>{void load();},[]);

  const protocols=useMemo(()=>{
    const root=asRecord(core.protocols??core.services??core);
    return Object.entries(root).filter(([key])=>!["ok","generated_at","timestamp"].includes(key));
  },[core]);

  const healthStatus=health.ok??health.healthy??health.status??health.overall_status;
  const securityStatus=security.ok??security.secure??security.status??security.level;
  const warningCount=Number(security.warnings??security.warning_count??security.alerts_count??0)||0;
  const criticalCount=Number(security.critical??security.critical_count??security.errors??0)||0;

  const run=async(key:string,label:string,fn:()=>Promise<unknown>)=>{
    if(busy)return;setBusy(key);setError("");setOk("");
    try{await fn();setOk(label);await load();}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  return <Shell active="/admin/system-health"><div className="page">
    <div className="page-head"><div><h1>{pick("سلامت و امنیت سیستم","System Health & Security")}</h1></div><div className="action-row"><button className="ghost" disabled={loading} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button><button className="primary" disabled={Boolean(busy)} onClick={()=>void run("all",pick("همه پروتکل‌های هسته ری‌استارت شدند","All core protocols restarted"),parityApi.restartAllCoreProtocols)}>{busy==="all"?"…":pick("Restart همه پروتکل‌ها","Restart all protocols")}</button></div></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}{loading&&<div className="runtime-loading">{pick("در حال دریافت سلامت سیستم...","Loading system health...")}</div>}

    <div className="stats dashboard-stats">
      <Stat label={pick("سلامت کلی","Overall health")} value={healthStatus===undefined?"—":isHealthy(healthStatus)?pick("سالم","Healthy"):text(healthStatus)} icon="◉"/>
      <Stat label={pick("وضعیت امنیت","Security") } value={securityStatus===undefined?"—":text(securityStatus)} icon="⌾"/>
      <Stat label={pick("هشدارها","Warnings")} value={String(warningCount)} icon="!"/>
      <Stat label={pick("بحرانی","Critical") } value={String(criticalCount)} icon="×"/>
      <Stat label={pick("پروتکل هسته","Core protocols")} value={String(protocols.length)} icon="⌁"/>
    </div>

    <div className="module-grid two">
      <Card><div className="card-head"><div><b>{pick("System Health","System Health")}</b><small>{pick("خروجی زنده Backend","Live backend response")}</small></div><Badge tone={tone(healthStatus)}>{healthStatus===undefined?pick("دریافت شد","Loaded"):text(healthStatus)}</Badge></div><RecordGrid data={health}/><details className="runtime-details"><summary>{pick("JSON کامل","Full JSON")}</summary><pre className="runtime-log" dir="ltr">{JSON.stringify(health,null,2)}</pre></details></Card>
      <Card><div className="card-head"><div><b>{pick("Security Overview","Security Overview")}</b><small>{pick("وضعیت واقعی کنترل‌های امنیتی","Live security controls")}</small></div><Badge tone={criticalCount>0?"bad":warningCount>0?"warn":"ok"}>{criticalCount>0?pick("نیاز به اقدام","Action required"):warningCount>0?pick("هشدار","Warning"):pick("عادی","Normal")}</Badge></div><RecordGrid data={security}/><details className="runtime-details"><summary>{pick("JSON کامل","Full JSON")}</summary><pre className="runtime-log" dir="ltr">{JSON.stringify(security,null,2)}</pre></details></Card>
    </div>

    <Card><div className="card-head"><div><b>{pick("پروتکل‌های هسته","Core Protocols")}</b><small>{pick("وضعیت سرویس و Restart مستقیم","Live service status and direct restart")}</small></div></div>{protocols.length?<div className="system-protocol-grid">{protocols.map(([key,raw])=>{const row=asRecord(raw);const state=row.status??row.state??row.service_state??row.active??row.online??raw;const healthy=isHealthy(row.ok??row.healthy??row.online??row.active??state);return <div className="module-row" key={key}><span className={`status-dot ${healthy?"online":"offline"}`}/><div className="grow"><b>{protocolName(key)}</b><small dir="ltr">{text(state)}</small></div><Badge tone={healthy?"ok":"warn"}>{healthy?pick("آنلاین","Online"):pick("نیاز به بررسی","Attention")}</Badge><button className="mini-btn" disabled={Boolean(busy)} onClick={()=>void run(key,`${protocolName(key)} ${pick("ری‌استارت شد","restarted")}`,()=>parityApi.restartCoreProtocol(key))}>{busy===key?"…":pick("Restart","Restart")}</button></div>})}</div>:<div className="runtime-empty">{pick("پروتکلی در پاسخ Backend نبود.","No protocol entries were returned.")}</div>}<details className="runtime-details"><summary>{pick("پاسخ کامل Core Protocols","Full core-protocol response")}</summary><pre className="runtime-log" dir="ltr">{JSON.stringify(core,null,2)}</pre></details></Card>
  </div></Shell>;
}
