"use client";

import Link from "next/link";
import {useMemo,useState} from "react";
import type {CSSProperties} from "react";
import type {AdminNode,AdminTunnel} from "../lib/admin-api";
import styles from "./admin-dashboard-network-panels.module.css";

type Pick=(fa:string,en:string)=>string;
export type DashboardProtocol={key:string;label:string;online:boolean;onlineNodes:number;reported:boolean};
type ProtocolGroup="all"|"classic"|"modern";
type NetworkStatus="online"|"offline"|"unknown";
const CLASSIC=new Set(["cisco","openvpn","wireguard","l2tp","v2ray"]);
const initials:Record<string,string>={
  cisco:"OC",openvpn:"OV",wireguard:"WG",l2tp:"L2",v2ray:"XR",
  hysteria2:"HY",tuic:"TU",anytls:"AT",naive:"NV",shadowtls:"ST",
  snell:"SN",mieru:"MI",trusttunnel:"TT",amneziawg:"AW",sudoku:"SD",socks5:"SO"
};
const display=(v:number)=>Math.max(0,v).toLocaleString("fa-IR");
const protocolKind=(key:string):ProtocolGroup=>CLASSIC.has(key)?"classic":"modern";
const classify=(status:unknown):NetworkStatus=>{
  const value=String(status??"").toLowerCase().trim();
  return value==="online"?"online":value==="offline"?"offline":"unknown";
};
const latency=(value:number|null|undefined)=>{
  if(value==null)return null;
  const number=Number(value);
  return Number.isFinite(number)&&number>=0?number:null;
};

export function TunnelMonitor({tunnels,nodes,loaded,pick}:{
  tunnels:AdminTunnel[];nodes:AdminNode[];loaded:boolean;pick:Pick;
}){
  const byId=useMemo(()=>new Map(nodes.map(node=>[node.id,node.name])),[nodes]);
  const online=tunnels.filter(t=>classify(t.status)==="online").length;
  const offline=tunnels.filter(t=>classify(t.status)==="offline").length;
  const unknown=Math.max(0,tunnels.length-online-offline);
  const title=(t:AdminTunnel,kind:"iran"|"exit")=>{
    const id=kind==="iran"?t.iran_node_id:t.exit_node_id;
    const resolved=byId.get(id);
    if(resolved)return resolved;
    return (kind==="iran"?pick("ایران","Iran"):pick("خروجی","Exit"))+" #"+id;
  };
  return <div className={styles.tunnels} dir="rtl">
    <div className={styles.header}>
      <div className={styles.heading}>
        <span className={styles.eyebrow}><i/>{pick("مسیرهای ارتباطی","NETWORK TRANSPORTS")}</span>
        <h2>{pick("مانیتور تانل‌ها","Tunnel monitor")}</h2>
        <p>{pick("مسیرهای ثبت‌شده بین نود ایران و خروجی","Reported links between Iran ingress and exit nodes")}</p>
      </div>
      <Link href="/admin/tunnels" className={styles.more}>{pick("مدیریت","Manage")} <span aria-hidden="true">↗</span></Link>
    </div>
    <div className={styles.stats}>
      <div className={styles.stat} data-kind="online"><span>{pick("آنلاین","Online")}</span><strong>{loaded?display(online):"—"}</strong></div>
      <div className={styles.stat} data-kind="offline"><span>{pick("آفلاین","Offline")}</span><strong>{loaded?display(offline):"—"}</strong></div>
      <div className={styles.stat} data-kind="total"><span>{pick("کل مسیرها","Total")}</span><strong>{loaded?display(tunnels.length):"—"}</strong></div>
    </div>
    <div className={styles.tunnelList}>
      {tunnels.slice(0,6).map(t=>{
        const state=classify(t.status);
        const ms=latency(t.latency_ms);
        const severity=ms==null?"unknown":ms>=220?"high":ms>=100?"elevated":"normal";
        return <article className={styles.tunnel} data-state={state} key={t.id}>
          <div className={styles.tunnelHead}>
            <div className={styles.tunnelIcon} aria-hidden="true">
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2.8" y="4" width="7" height="7" rx="2"/><rect x="14.2" y="13" width="7" height="7" rx="2"/>
                <path d="M9.8 7.5h4.4v9H10M12 13.5l2.3 3-2.3 3"/>
              </svg>
            </div>
            <div className={styles.tunnelName}>
              <strong>{t.active_transport||t.transport||pick("پروتکل نامشخص","Unknown transport")}</strong>
              <small>#{display(t.id)} {t.mode?"· "+t.mode:""}</small>
            </div>
            <span className={styles.status} data-state={state}><i/>{state==="online"?pick("آنلاین","Online"):state==="offline"?pick("آفلاین","Offline"):pick("نامشخص","Unknown")}</span>
          </div>
          <div className={styles.tunnelRoute}>
            <span className={styles.routePoint}><i className={styles.routeOrigin}/><span>{title(t,"iran")}</span></span>
            <span className={styles.routeLine} aria-hidden="true"><i/><span>←</span></span>
            <span className={styles.routePoint}><i className={styles.routeExit}/><span>{title(t,"exit")}</span></span>
          </div>
          <div className={styles.tunnelFoot}>
            <span>{pick("تأخیر گزارش‌شده","Reported latency")}</span>
            <div className={styles.latency} data-severity={severity}>
              <span aria-hidden="true">◷</span>
              <strong dir="ltr">{ms==null?"—":ms.toLocaleString("en-US",{maximumFractionDigits:0})+" ms"}</strong>
            </div>
          </div>
        </article>;
      })}
      {!tunnels.length&&<div className={styles.empty}>{loaded?pick("تانلی گزارش نشده","No tunnels reported"):pick("در حال دریافت وضعیت تانل‌ها","Loading tunnel telemetry")}</div>}
    </div>
    <div className={styles.note}>{pick("آنلاین بودن، وضعیت ثبت‌شده تانل است؛ تست سرعت یا عبور واقعی ترافیک کاربران نیست.","Online reflects the reported tunnel state, not a verified user traffic or throughput test.")}{unknown>0&&loaded?" · "+display(unknown)+" "+pick("مسیر نامشخص","unknown routes"):""}</div>
  </div>;
}

export function ProtocolMonitor({protocols,pick}:{
  protocols:DashboardProtocol[];pick:Pick;
}){
  const [group,setGroup]=useState<ProtocolGroup>("all");
  const shown=useMemo(()=>group==="all"?protocols:protocols.filter(p=>protocolKind(p.key)===group),[group,protocols]);
  const classicCount=protocols.filter(p=>protocolKind(p.key)==="classic").length;
  const modernCount=protocols.length-classicCount;
  const reported=protocols.filter(p=>p.reported).length;
  const active=protocols.filter(p=>p.reported&&p.online).length;
  return <div className={styles.protocols} dir="rtl">
    <div className={styles.header}>
      <div className={styles.heading}>
        <span className={styles.eyebrow}><i/>{pick("پوشش سرویس","PROTOCOL COVERAGE")}</span>
        <h2>{pick("پروتکل‌های سرویس","Service protocols")}</h2>
        <p>{pick("وضعیت گزارش‌شده هر پروتکل در نودها","Status reported by the associated server nodes")}</p>
      </div>
      <Link href="/admin/protocols" className={styles.more}>{pick("مدیریت پروتکل‌ها","Manage")} <span aria-hidden="true">↗</span></Link>
    </div>
    <div className={styles.protocolSummary}>
      <div><span>{pick("کل پروتکل‌ها","Protocols")}</span><strong>{display(protocols.length)}</strong></div>
      <div><span>{pick("گزارش فعال","Reported online")}</span><strong>{display(active)}</strong></div>
      <div><span>{pick("دریافت گزارش","Reported")}</span><strong>{display(reported)} / {display(protocols.length)}</strong></div>
    </div>
    <div className={styles.filters} role="group" aria-label={pick("دسته‌بندی پروتکل‌ها","Protocol categories")}>
      {[
        {id:"all" as const,label:pick("همه","All"),count:protocols.length},
        {id:"classic" as const,label:pick("کلاسیک","Classic"),count:classicCount},
        {id:"modern" as const,label:pick("مدرن","Modern"),count:modernCount}
      ].map(option=><button type="button" key={option.id} className={styles.filter}
        aria-pressed={group===option.id} data-selected={group===option.id}
        onClick={()=>setGroup(option.id)}>{option.label}<b>{display(option.count)}</b></button>)}
    </div>
    <div className={styles.protocolGrid}>
      {shown.map(p=>{
        const state:NetworkStatus=!p.reported?"unknown":p.online?"online":"offline";
        return <article key={p.key} className={styles.protocol} data-state={state}>
          <div className={styles.protocolIcon} aria-hidden="true">{initials[p.key]||p.key.slice(0,2).toUpperCase()}</div>
          <div className={styles.protocolText}>
            <strong title={p.label}>{p.label}</strong>
            <small>{p.reported?display(p.onlineNodes)+" "+pick("نود آنلاین گزارش‌شده","reported online nodes"):pick("بدون گزارش سلامت","No health report")}</small>
          </div>
          <span className={styles.protocolState}><i/>{state==="online"?pick("گزارش فعال","Reported online"):state==="offline"?pick("غیرفعال گزارش‌شده","Reported offline"):pick("نامشخص","Unknown")}</span>
        </article>;
      })}
    </div>
    <div className={styles.note}>{pick("نشان سبز به‌معنی گزارش فعال از پنل است، نه تأیید اتصال واقعی کاربر. برای بررسی اتصال، تست جداگانه لازم است.","A green indicator means reported active state, not a verified live client connection.")}</div>
  </div>;
}
