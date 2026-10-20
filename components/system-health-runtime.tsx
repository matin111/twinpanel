"use client";

import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {AnyRow,parityApi} from "../lib/admin-parity-api";
import {adminApi} from "../lib/admin-api";
import {useI18n} from "../lib/i18n";

const asRecord=(value:unknown):AnyRow=>value&&typeof value==="object"&&!Array.isArray(value)?value as AnyRow:{};
const toNumber=(value:unknown)=>{const n=Number(value??0);return Number.isFinite(n)?n:0;};
const asText=(value:unknown)=>value===null||value===undefined?"":String(value);
const statusValue=(value:unknown)=>asText(value).trim().toLowerCase();

function formatBytes(value:unknown){
  const bytes=Math.max(0,toNumber(value));
  if(bytes<1024)return `${Math.round(bytes)} B`;
  const units=["KB","MB","GB","TB"];
  let size=bytes/1024;
  let index=0;
  while(size>=1024&&index<units.length-1){size/=1024;index+=1;}
  const digits=size>=100?0:size>=10?1:2;
  return `${size.toFixed(digits)} ${units[index]}`;
}

function riskTone(value:unknown):"ok"|"warn"|"bad"{
  const risk=statusValue(value);
  if(risk==="high")return "bad";
  if(risk==="medium")return "warn";
  return "ok";
}

export function SystemHealthRuntimePage(){
  const {pick}=useI18n();
  const [security,setSecurity]=useState<AnyRow>({});
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [query,setQuery]=useState("");
  const [riskFilter,setRiskFilter]=useState("all");
  const [statusFilter,setStatusFilter]=useState("all");

  const load=async()=>{
    setLoading(true);
    setError("");
    try{
      setSecurity(await parityApi.securityOverview());
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }finally{
      setLoading(false);
    }
  };

  useEffect(()=>{void load();},[]);

  const summary=asRecord(security.summary);
  const rules=asRecord(security.rules);
  const rows=useMemo(()=>{
    const items=Array.isArray(security.items)?security.items:[];
    return items.map(asRecord);
  },[security]);

  const filteredRows=useMemo(()=>{
    const needle=query.trim().toLowerCase();
    return rows.filter(row=>{
      const risk=statusValue(row.risk_level||"normal");
      const status=statusValue(row.status);
      if(riskFilter!=="all"&&risk!==riskFilter)return false;
      if(statusFilter!=="all"&&status!==statusFilter)return false;
      if(!needle)return true;
      const haystack=[
        row.subscription_id,
        row.user_id,
        row.user_name,
        row.email,
        row.plan_name,
        row.status,
        row.risk_level,
      ].map(asText).join(" ").toLowerCase();
      return haystack.includes(needle);
    });
  },[rows,query,riskFilter,statusFilter]);

  const changeSubscriptionState=async(row:AnyRow,active:boolean)=>{
    if(busy)return;
    const id=toNumber(row.subscription_id);
    if(!id)return;
    if(!active){
      const accepted=window.confirm(pick("این اشتراک از داخل مرکز امنیت تعلیق شود؟","Suspend this subscription from Security Center?"));
      if(!accepted)return;
    }
    setBusy(String(id));
    setError("");
    setOk("");
    try{
      await adminApi.setSubscriptionActive(id,active);
      setOk(active?pick("اشتراک فعال شد.","Subscription activated."):pick("اشتراک تعلیق شد.","Subscription suspended."));
      await load();
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
    }finally{
      setBusy("");
    }
  };

  const high=toNumber(summary.high_risk);
  const medium=toNumber(summary.medium_risk);
  const total=toNumber(summary.subscriptions);
  const telemetry=toNumber(summary.with_telemetry);
  const openSessions=toNumber(summary.open_sessions);

  return <Shell active="/admin/system-health"><div className="page">
    <div className="page-head">
      <div>
        <h1>{pick("امنیت","Security Center")}</h1>
      </div>
      <div className="action-row"><button className="ghost" disabled={loading} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button></div>
    </div>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}
    {loading&&<div className="runtime-loading">{pick("در حال دریافت وضعیت امنیت...","Loading security status...")}</div>}

    <div className="stats dashboard-stats">
      <Stat label={pick("کل اشتراک‌ها","Subscriptions")} value={String(total)} icon="▱"/>
      <Stat label={pick("دارای داده امنیتی","With telemetry")} value={String(telemetry)} icon="◉"/>
      <Stat label={pick("ریسک بالا","High risk")} value={String(high)} icon="!"/>
      <Stat label={pick("ریسک متوسط","Medium risk")} value={String(medium)} icon="△"/>
      <Stat label={pick("نشست‌های باز","Open sessions")} value={String(openSessions)} icon="⌁"/>
    </div>

    <Card>
      <div className="card-head">
        <div><b>{pick("اشتراک‌های تحت پایش","Monitored subscriptions")}</b><small>{pick(`نمایش ${filteredRows.length} مورد از ${rows.length} اشتراک`,`Showing ${filteredRows.length} of ${rows.length} subscriptions`)}</small></div>
        <Badge tone={high>0?"bad":medium>0?"warn":"ok"}>{high>0?pick("نیاز به بررسی فوری","Review required"):medium>0?pick("دارای هشدار","Warnings present"):pick("وضعیت عادی","Normal")}</Badge>
      </div>

      <div className="toolbar">
        <label>⌕ <input value={query} onChange={e=>setQuery(e.target.value)} placeholder={pick("جستجو نام، ایمیل، پلن یا شناسه اشتراک...","Search name, email, plan or subscription ID...")}/></label>
        <select value={riskFilter} onChange={e=>setRiskFilter(e.target.value)} aria-label={pick("فیلتر ریسک","Risk filter")}>
          <option value="all">{pick("همه ریسک‌ها","All risks")}</option>
          <option value="high">{pick("ریسک بالا","High risk")}</option>
          <option value="medium">{pick("ریسک متوسط","Medium risk")}</option>
          <option value="normal">{pick("عادی","Normal")}</option>
        </select>
        <select value={statusFilter} onChange={e=>setStatusFilter(e.target.value)} aria-label={pick("فیلتر وضعیت","Status filter")}>
          <option value="all">{pick("همه وضعیت‌ها","All statuses")}</option>
          <option value="active">{pick("فعال","Active")}</option>
          <option value="suspended">{pick("تعلیق‌شده","Suspended")}</option>
          <option value="expired">{pick("منقضی","Expired")}</option>
        </select>
      </div>

      <div className="table"><table>
        <thead><tr>
          <th>{pick("کاربر","User")}</th>
          <th>{pick("اشتراک / پلن","Subscription / Plan")}</th>
          <th>{pick("ریسک","Risk")}</th>
          <th>{pick("دستگاه فعال","Active devices")}</th>
          <th>{pick("فعالیت ۲۴ ساعت","24h activity")}</th>
          <th>{pick("مصرف ۲۴ ساعت","24h usage")}</th>
          <th>{pick("وضعیت","Status")}</th>
          <th>{pick("عملیات","Action")}</th>
        </tr></thead>
        <tbody>{filteredRows.map(row=>{
          const id=toNumber(row.subscription_id);
          const risk=statusValue(row.risk_level||"normal");
          const status=statusValue(row.status);
          const activeDevices=toNumber(row.active_devices);
          const deviceLimit=toNumber(row.device_limit);
          const reasons=Array.isArray(row.reasons)?row.reasons.map(asText).filter(Boolean):[];
          const recentIps=Array.isArray(row.recent_ips)?row.recent_ips.map(asText).filter(Boolean):[];
          const canSuspend=status==="active";
          const canActivate=status==="suspended";
          const riskLabel=risk==="high"?pick("بالا","High"):risk==="medium"?pick("متوسط","Medium"):pick("عادی","Normal");
          const statusLabel=status==="active"?pick("فعال","Active"):status==="suspended"?pick("تعلیق‌شده","Suspended"):status==="expired"?pick("منقضی","Expired"):status||"—";
          return <tr key={id||`${asText(row.user_id)}-${asText(row.plan_name)}`}>
            <td><b>{asText(row.user_name)||`User #${asText(row.user_id)}`}</b><small dir="ltr">{asText(row.email)||"—"}</small></td>
            <td><b>#{id||"—"}</b><small>{asText(row.plan_name)||"—"}</small></td>
            <td><Badge tone={riskTone(risk)}>{riskLabel} · {toNumber(row.risk_score)}</Badge>{reasons.length>0&&<details className="runtime-details"><summary>{pick("دلایل","Reasons")} ({reasons.length})</summary><div>{reasons.map((reason,index)=><small key={index}>{reason}{index<reasons.length-1?<br/>:null}</small>)}</div></details>}</td>
            <td><b>{activeDevices} / {deviceLimit||1}</b><small>{pick(`${toNumber(row.active_sessions)} نشست فعال`,`${toNumber(row.active_sessions)} active sessions`)}</small></td>
            <td><b>{pick(`${toNumber(row.recent_devices_24h)} دستگاه`,`${toNumber(row.recent_devices_24h)} devices`)}</b><small>{pick(`${toNumber(row.recent_ips_24h)} آی‌پی`,`${toNumber(row.recent_ips_24h)} IPs`)}{recentIps.length?` · ${recentIps.slice(0,3).join(", ")}`:""}</small></td>
            <td><b dir="ltr">{formatBytes(row.usage_24h_bytes)}</b><small>{row.has_telemetry===false?pick("بدون داده اخیر","No recent telemetry"):pick("داده ۲۴ ساعت اخیر","Last 24 hours")}</small></td>
            <td><Badge tone={status==="active"?"ok":status==="suspended"?"warn":"violet"}>{statusLabel}</Badge></td>
            <td>{canSuspend?<button className="mini-btn" disabled={Boolean(busy)} onClick={()=>void changeSubscriptionState(row,false)}>{busy===String(id)?"…":pick("تعلیق","Suspend")}</button>:canActivate?<button className="mini-btn" disabled={Boolean(busy)} onClick={()=>void changeSubscriptionState(row,true)}>{busy===String(id)?"…":pick("فعال‌سازی","Activate")}</button>:<span>—</span>}</td>
          </tr>;
        })}</tbody>
      </table></div>

      {!loading&&filteredRows.length===0&&<div className="runtime-empty">{pick("اشتراکی با این فیلتر پیدا نشد.","No subscriptions match these filters.")}</div>}
    </Card>

    <Card>
      <div className="card-head"><div><b>{pick("قوانین تشخیص ریسک","Risk detection rules")}</b><small>{pick(`بازه تحلیل: ${toNumber(security.window_hours)||24} ساعت`,`Analysis window: ${toNumber(security.window_hours)||24} hours`)}</small></div><Badge tone="violet">{pick("تعلیق خودکار خاموش است","Auto-suspend is off")}</Badge></div>
      <div className="runtime-info-list">
        <div><span>{pick("عبور از سقف دستگاه هم‌زمان","Concurrent device limit")}</span><b>{asText(rules.device_limit)||"—"}</b></div>
        <div><span>{pick("تغییر زیاد دستگاه","Device churn")}</span><b>{asText(rules.device_churn)||"—"}</b></div>
        <div><span>{pick("تغییر زیاد IP","IP churn")}</span><b>{asText(rules.ip_churn)||"—"}</b></div>
      </div>
    </Card>
  </div></Shell>;
}
