"use client";

import {useEffect,useId,useState} from "react";
import type {CSSProperties} from "react";
import {createPortal} from "react-dom";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import styles from "./admin-dashboard-server-card.module.css";

type SystemHealth={
  hostname?:string;
  cpu?:{percent?:number;cores?:number;load_1?:number};
  memory?:{percent?:number;used_bytes?:number;total_bytes?:number};
  disk?:{percent?:number;used_bytes?:number;total_bytes?:number};
  network?:{rx_mbps?:number;tx_mbps?:number};
  uptime_seconds?:number;
};

function percent(value:unknown){
  const n=Number(value);
  return Number.isFinite(n)?Math.max(0,Math.min(100,n)):null;
}

function formatUptime(value:number|undefined){
  if(!Number.isFinite(Number(value)))return "—";
  const total=Math.max(0,Math.floor(Number(value)));
  const days=Math.floor(total/86400);
  const hours=Math.floor((total%86400)/3600);
  return days>0?`${days}d ${hours}h`:`${hours}h`;
}

function formatGiB(value:number|undefined){
  const bytes=Number(value);
  if(!Number.isFinite(bytes)||bytes<0)return "—";
  return `${(bytes/1073741824).toFixed(bytes>=10737418240?0:1)} GB`;
}


type Sample={at:number;cpu:number|null;ram:number|null;disk:number|null;rx:number|null;tx:number|null};
type Kind="cpu"|"ram"|"disk"|"rx";
type Pick=(fa:string,en:string)=>string;
const WINDOW_MS=8*60*1000;
const MAX_SAMPLES=33;
const RADIUS=40;
const CIRCUMFERENCE=2*Math.PI*RADIUS;
const usage=(value:unknown)=>value===null||value===undefined||value===""?null:percent(value);
const positive=(value:unknown)=>{
  if(value===null||value===undefined||value==="")return null;
  const n=Number(value);
  return Number.isFinite(n)&&n>=0?n:null;
};
const metricPercent=(value:number|null)=>value==null?"—":Math.round(value).toLocaleString("fa-IR")+"%";
const fmt=(value:number|null)=>value==null?"—":value.toLocaleString("fa-IR",{maximumFractionDigits:2});
const serverSample=(health:SystemHealth):Sample=>({
  at:Date.now(),cpu:usage(health.cpu?.percent),ram:usage(health.memory?.percent),
  disk:usage(health.disk?.percent),rx:positive(health.network?.rx_mbps),
  tx:positive(health.network?.tx_mbps),
});

function smoothPath(points:{x:number;y:number}[]){
  if(points.length<2)return "";
  let result="M "+points[0].x.toFixed(2)+" "+points[0].y.toFixed(2);
  for(let i=1;i<points.length;i++){
    const a=points[i-1],b=points[i],dx=(b.x-a.x)*.34;
    result+=" C "+(a.x+dx).toFixed(2)+" "+a.y.toFixed(2)+
      " "+(b.x-dx).toFixed(2)+" "+b.y.toFixed(2)+
      " "+b.x.toFixed(2)+" "+b.y.toFixed(2);
  }
  return result;
}

function ResourceTrend({samples,kind,pick}:{samples:Sample[];kind:Kind;pick:Pick}){
  const uid=useId().replace(/:/g,"");
  const valid=samples.filter(row=>row[kind]!=null);
  if(!valid.length)return <div className={styles.awaiting}>{pick("در انتظار داده زنده","Waiting for live samples")}</div>;
  const last=valid[valid.length-1];
  const peak=kind==="rx"?Math.max(1,...valid.map(x=>x.rx||0))*1.15:100;
  const points=valid.map(row=>({
    x:10+Math.max(0,Math.min(1,(row.at-(last.at-WINDOW_MS))/WINDOW_MS))*300,
    y:70-((row[kind]||0)/peak)*56,
  }));
  const line=smoothPath(points),end=points[points.length-1],first=points[0];
  const area=line?line+" L "+end.x.toFixed(2)+" 70 L "+first.x.toFixed(2)+" 70 Z":"";
  const gradient="server-area-"+uid;
  return <svg className={styles.trend} viewBox="0 0 320 80" preserveAspectRatio="none"
    role="img" aria-label={pick("روند استفاده؛ "+valid.length.toLocaleString("fa-IR")+" نمونه واقعی",
                           "Usage trend from "+valid.length+" real samples")}>
    <defs><linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--metric)" stopOpacity=".22"/><stop offset="100%" stopColor="var(--metric)" stopOpacity="0"/></linearGradient></defs>
    <path className={styles.grid} d="M 10 42 H 310 M 10 70 H 310"/>
    {area&&<path d={area} fill={"url(#"+gradient+")"} className={styles.area}/>}
    {line&&<path d={line} className={styles.line}/>}
    <circle cx={end.x} cy={end.y} r="9" className={styles.halo}/>
    <circle cx={end.x} cy={end.y} r="4" className={styles.point}/>
  </svg>;
}

function ResourceGauge({kind,label,value,capacity,samples,pick}:{
  kind:"cpu"|"ram"|"disk";label:string;value:number|null;
  capacity:string;samples:Sample[];pick:Pick;
}){
  const danger=value!=null&&value>=90;
  const warning=value!=null&&value>=75&&!danger;
  const color=danger?"#f07483":warning?"#e4ae57":kind==="cpu"?"#9b80ff":kind==="ram"?"#22c8c4":"#63a1ff";
  const status=value==null?pick("بدون داده","No data"):danger?pick("مصرف بحرانی","Critical"):warning?pick("مصرف بالا","Elevated"):pick("مصرف عادی","Normal");
  const dash=(CIRCUMFERENCE*(value||0)/100).toFixed(2)+" "+CIRCUMFERENCE.toFixed(2);
  return <article className={styles.resource} style={{"--metric":color} as CSSProperties}>
    <div className={styles.resourceHeader}><div><span>{pick("میزان استفاده","UTILIZATION")}</span><h3>{label}</h3></div><small className={styles.state}><i/>{status}</small></div>
    <div className={styles.resourceBody}>
      <div className={styles.gauge}>
        <svg viewBox="0 0 112 112" role="img" aria-label={label+" "+metricPercent(value)}>
          <circle className={styles.gaugeTrack} cx="56" cy="56" r={RADIUS}/>
          <circle className={styles.gaugeProgress} cx="56" cy="56" r={RADIUS} strokeDasharray={dash}/>
        </svg>
        <div className={styles.gaugeValue}><strong>{metricPercent(value)}</strong><small>{pick("مصرف‌شده","USED")}</small></div>
      </div>
      <div className={styles.resourceMeta}><b dir="ltr">{capacity}</b><span>{pick("وضعیت فعلی سرور","Current server usage")}</span></div>
    </div>
    <div className={styles.trendHeader}><span>{pick("روند مصرف","USAGE TREND")}</span><span>{pick("۸ دقیقه اخیر","Last 8 min")}</span></div>
    <ResourceTrend samples={samples} kind={kind} pick={pick}/>
  </article>;
}

function NetworkGauge({health,samples,pick}:{health:SystemHealth|null;samples:Sample[];pick:Pick}){
  const rx=positive(health?.network?.rx_mbps);
  const tx=positive(health?.network?.tx_mbps);
  return <article className={styles.resource} style={{"--metric":"#21cda5"} as CSSProperties}>
    <div className={styles.resourceHeader}><div><span>{pick("نرخ انتقال لحظه‌ای","LIVE THROUGHPUT")}</span><h3>{pick("شبکه","Network")}</h3></div><small className={styles.state}><i/>{pick("لحظه‌ای","Live")}</small></div>
    <div className={styles.networkMetrics}>
      <div><i className={styles.download}>↓</i><span>{pick("دریافت","Download")}</span><b>{fmt(rx)} <small>Mbps</small></b></div>
      <div><i className={styles.upload}>↑</i><span>{pick("ارسال","Upload")}</span><b>{fmt(tx)} <small>Mbps</small></b></div>
    </div>
    <div className={styles.trendHeader}><span>{pick("روند دریافت","DOWNLOAD TREND")}</span><span>{pick("۸ دقیقه اخیر","Last 8 min")}</span></div>
    <ResourceTrend samples={samples} kind="rx" pick={pick}/>
  </article>;
}

export function AdminDashboardServerCard(){
  const {pick}=useI18n();
  const [health,setHealth]=useState<SystemHealth|null>(null);
  const [mount,setMount]=useState<HTMLElement|null>(null);
  const [samples,setSamples]=useState<Sample[]>([]);
  const [telemetryState,setTelemetryState]=useState<"waiting"|"online"|"stale">("waiting");

  useEffect(()=>{
    let created:HTMLElement|null=null;
    const attach=()=>{
      const kpis=document.querySelector<HTMLElement>(".dash27 .dash27-kpis");
      if(!kpis||!kpis.parentElement)return false;
      const existing=document.querySelector<HTMLElement>(".dash27-server-host");
      if(existing){setMount(existing);return true;}
      created=document.createElement("section");
      created.className="dash27-server-host";
      kpis.insertAdjacentElement("afterend",created);
      setMount(created);
      return true;
    };
    if(!attach()){
      const observer=new MutationObserver(()=>{if(attach())observer.disconnect();});
      observer.observe(document.body,{childList:true,subtree:true});
      return ()=>{observer.disconnect();if(created?.isConnected)created.remove();};
    }
    return ()=>{if(created?.isConnected)created.remove();};
  },[]);

  useEffect(()=>{
    const token=getCustomerToken();
    if(!token){setTelemetryState("stale");return;}
    let active=true;
    const load=async()=>{
      try{
        const response=await fetch(`${API_BASE}/v1/admin/system-health`,{
          headers:{Authorization:`Bearer ${token}`},cache:"no-store"
        });
        if(!response.ok)throw new Error("Telemetry temporarily unavailable");
        const payload=await response.json() as SystemHealth;
        if(!active)return;
        const sample=serverSample(payload);
        setHealth(payload);
        setSamples(before=>[...before.filter(item=>item.at>=sample.at-WINDOW_MS),sample].slice(-MAX_SAMPLES));
        setTelemetryState("online");
      }catch{if(active)setTelemetryState("stale");}
    };
    void load();
    const timer=window.setInterval(()=>void load(),15000);
    return ()=>{active=false;window.clearInterval(timer);};
  },[]);

  if(!mount)return null;
  const cpu=usage(health?.cpu?.percent);
  const ram=usage(health?.memory?.percent);
  const disk=usage(health?.disk?.percent);
  const cores=positive(health?.cpu?.cores);
  const cpuCapacity=cores==null?"—":Math.round(cores).toLocaleString("en-US")+" vCPU";
  const ramCapacity=formatGiB(health?.memory?.used_bytes)+" / "+formatGiB(health?.memory?.total_bytes);
  const diskCapacity=formatGiB(health?.disk?.used_bytes)+" / "+formatGiB(health?.disk?.total_bytes);
  const last=samples.length?samples[samples.length-1].at:null;

  return createPortal(
    <section className={styles.panel} aria-label={pick("مانیتور منابع سرور","Server resources monitor")}>
      <div className={styles.header}>
        <div className={styles.heading}>
          <span className={styles.eyebrow}><i/>{pick("مانیتورینگ زیرساخت","INFRASTRUCTURE MONITOR")}</span>
          <h2>{pick("نبض سرور","Server pulse")}</h2>
          <p>{pick("مصرف لحظه‌ای منابع سرور اصلی پنل","Live utilization on the main panel server")}</p>
        </div>
        <div className={styles.headerInfo}>
          <div className={telemetryState==="online"?styles.online:styles.stale}><i/>{telemetryState==="online"?pick("داده زنده","Live data"):telemetryState==="waiting"?pick("در حال دریافت","Fetching data"):pick("داده قدیمی / قطع دریافت","Telemetry unavailable")}</div>
          <div className={styles.infoPill}><span>{pick("نام سرور","Hostname")}</span><b dir="ltr">{health?.hostname||"—"}</b></div>
          <div className={styles.infoPill}><span>{pick("مدت فعالیت","Uptime")}</span><b dir="ltr">{formatUptime(health?.uptime_seconds)}</b></div>
        </div>
      </div>
      <div className={styles.cards}>
        <ResourceGauge kind="cpu" label="CPU" value={cpu} capacity={cpuCapacity} samples={samples} pick={pick}/>
        <ResourceGauge kind="ram" label="RAM" value={ram} capacity={ramCapacity} samples={samples} pick={pick}/>
        <ResourceGauge kind="disk" label={pick("دیسک","Disk")} value={disk} capacity={diskCapacity} samples={samples} pick={pick}/>
        <NetworkGauge health={health} samples={samples} pick={pick}/>
      </div>
      <footer className={styles.footer}>
        <span><i/>{pick("نمودارها فقط از نمونه‌های واقعی ثبت‌شده بعد از بازشدن صفحه تشکیل می‌شوند.","Charts include real samples collected since opening this page only.")}</span>
        <span>{last?pick("آخرین نمونه","Last reading")+": "+new Date(last).toLocaleTimeString(pick("fa-IR","en-US"),{hour:"2-digit",minute:"2-digit",second:"2-digit"}):pick("منتظر اولین نمونه","Awaiting first reading")} · {pick("هر ۱۵ ثانیه","Every 15s")}</span>
      </footer>
    </section>,
    mount
  );
}
