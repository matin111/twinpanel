"use client";

import type {CSSProperties} from "react";
import styles from "./admin-overview-visuals.module.css";

type Pick=(fa:string,en:string)=>string;
type KpiKind="users"|"subscriptions"|"online"|"sales"|"nodes";
type ServiceType="nodes"|"tunnels"|"protocols";

function Icon({kind}:{kind:KpiKind}){
  const shared={fill:"none",stroke:"currentColor",strokeWidth:1.8,strokeLinecap:"round" as const,strokeLinejoin:"round" as const};
  return <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" {...shared}>
    {kind==="users"&&<><circle cx="9" cy="8" r="3"/><path d="M3.5 19v-2a5.5 5.5 0 0 1 11 0v2M17 5.4a3.2 3.2 0 0 1 0 6.2M17.7 14a4 4 0 0 1 2.8 4v1"/></>}
    {kind==="subscriptions"&&<><rect x="3.5" y="5" width="17" height="14" rx="3"/><path d="M3.5 10h17M8 14h3M8 17h6"/></>}
    {kind==="online"&&<><path d="M3.7 8a12.7 12.7 0 0 1 16.6 0M6.9 11.4a7.7 7.7 0 0 1 10.2 0M10 14.8a3.2 3.2 0 0 1 4 0"/><circle cx="12" cy="18" r="1" fill="currentColor" stroke="none"/></>}
    {kind==="sales"&&<><path d="M4 19h16M5.2 16.7l5.1-5.1 3.4 2.8 5.6-7.4M14.9 7h4.4v4.4"/></>}
    {kind==="nodes"&&<><rect x="5" y="3.5" width="14" height="7" rx="2"/><rect x="5" y="13.5" width="14" height="7" rx="2"/><path d="M8.5 7h.02M8.5 17h.02M12 7h4M12 17h4"/></>}
  </svg>;
}

const tones:Record<KpiKind,string>={
  users:"#9876ff",subscriptions:"#618eff",online:"#24bfae",sales:"#e7a74d",nodes:"#34b9d9"
};
const num=(value:number)=>value.toLocaleString("fa-IR");
function clampPct(v:number|null):number|null{
  return v!=null&&Number.isFinite(v)?Math.max(0,Math.min(100,v)):null;
}

export function OverviewKpiCard({kind,label,value,meta,ratio,pick}:{
  kind:KpiKind;label:string;value:string;meta:string;ratio?:number|null;pick:Pick;
}){
  const pct=clampPct(ratio??null);
  const theme={"--highlight":tones[kind]} as CSSProperties;
  return <article className={styles.kpi} style={theme}>
    <div className={styles.kpiHeader}>
      <div className={styles.kpiIcon}><Icon kind={kind}/></div>
    </div>
    <span className={styles.kpiLabel}>{label}</span>
    <strong className={styles.kpiValue} dir="auto">{value}</strong>
    {pct!=null?<div className={styles.kpiFooter}><b>{num(Math.round(pct))}%</b></div>:null}
    {pct!=null?<div className={styles.kpiProgress} aria-label={pick("درصد پوشش","Coverage")+" "+num(Math.round(pct))+"%"}><i style={{width:String(pct)+"%"}}/></div>:<div className={styles.kpiSeparator}/>}
  </article>;
}

type HealthLine={type:ServiceType;label:string;online:number|null;total:number|null};
const safeFraction=(online:number|null,total:number|null):number|null=>
  online==null||total==null||total<1?null:Math.max(0,Math.min(100,100*online/total));

function HealthRow({line,pick}:{line:HealthLine;pick:Pick}){
  const pct=safeFraction(line.online,line.total);
  const style={"--rowColor":line.type==="nodes"?"#27c7a8":line.type==="tunnels"?"#a18bfa":"#3db6d8"} as CSSProperties;
  return <div className={styles.healthRow} style={style}>
    <div className={styles.healthRowHead}>
      <div className={styles.healthRowLabel}><i/><span>{line.label}</span></div>
      <div className={styles.healthRowCount} dir="ltr">
        <b>{line.online==null?"—":num(line.online)}</b><span>/</span><b>{line.total==null?"—":num(line.total)}</b>
      </div>
    </div>
    <div className={styles.healthTrack} role="progressbar" aria-label={line.label}
       aria-valuenow={pct==null?undefined:Math.round(pct)} aria-valuemin={0} aria-valuemax={100}
       aria-valuetext={pct==null?pick("بدون گزارش","No reported data"):num(Math.round(pct))+"%"}>
      <i style={{width:(pct??0)+"%"}}/>
    </div>
  </div>;
}

export function OperationalHealthVisual({pick,nodeOnline,nodeTotal,tunnelOnline,tunnelTotal,protocolOnline,protocolTotal}:{
  pick:Pick;
  nodeOnline:number|null;nodeTotal:number|null;
  tunnelOnline:number|null;tunnelTotal:number|null;
  protocolOnline:number|null;protocolTotal:number|null;
}){
  const nodePct=safeFraction(nodeOnline,nodeTotal);
  const tunnelPct=safeFraction(tunnelOnline,tunnelTotal);
  const protocolPct=safeFraction(protocolOnline,protocolTotal);
  const allKnown=[nodePct,tunnelPct,protocolPct].every(v=>v!=null);
  const minimum=Math.min(...[nodePct,tunnelPct,protocolPct].filter((v):v is number=>v!=null));
  const allHealthy=allKnown&&minimum>=99.5;
  const needsReview=[nodePct,tunnelPct,protocolPct].some(v=>v!=null&&v<75);
  const headTitle=allHealthy?pick("سالم","Healthy"):
    needsReview?pick("نیاز به بررسی","Needs review"):
    allKnown?pick("در حال پایش","Monitoring"):
    pick("نامشخص","Unknown");
  const status=allHealthy?"good":needsReview?"warning":"neutral";
  const ringStyle={"--ring":nodePct==null?"0%":String(nodePct)+"%"} as CSSProperties;
  const lines:HealthLine[]=[
    {type:"nodes",label:pick("نودهای آنلاین","Online nodes"),online:nodeOnline,total:nodeTotal},
    {type:"tunnels",label:pick("تانل‌های آنلاین","Online tunnels"),online:tunnelOnline,total:tunnelTotal},
    {type:"protocols",label:pick("پروتکل‌های گزارش‌شده سالم","Healthy reported protocols"),online:protocolOnline,total:protocolTotal},
  ];
  return <div className={styles.healthPanel} dir="rtl">
    <div className={styles.healthTitle}>
      <div><h2>{pick("وضعیت سرویس‌ها","Service health")}</h2></div>
      <div className={styles.healthTag} data-state={status}><i/>{headTitle}</div>
    </div>
    <div className={styles.healthHero}>
      <div className={styles.healthRing} style={ringStyle}>
        <div className={styles.healthRingInner}>
          <strong>{nodePct==null?"—":num(Math.round(nodePct))+"%"}</strong>
          <span>{pick("دسترسی نودها","Node availability")}</span>
        </div>
      </div>
    </div>
    <div className={styles.healthList}>
      {lines.map(item=><HealthRow key={item.type} line={item} pick={pick}/>)}
    </div>
  </div>;
}
