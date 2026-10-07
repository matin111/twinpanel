"use client";

import {useEffect,useMemo,useState} from "react";
import {Badge,Card,Shell} from "./ui";
import {adminApi,RuntimeRow} from "../lib/admin-api";
import {useI18n} from "../lib/i18n";

type Kind="subscriptions"|"plans"|"nodes"|"tunnels"|"payments";

const configs:Record<Kind,{fa:string;en:string;loader:()=>Promise<RuntimeRow[]>;fields:[string,string,string][]}>={
  subscriptions:{fa:"اشتراک‌ها",en:"Subscriptions",loader:adminApi.subscriptions,fields:[["id","شناسه","ID"],["user_id","کاربر","User"],["plan_id","پلن","Plan"],["status","وضعیت","Status"],["expires_at","انقضا","Expires"]]},
  plans:{fa:"پلن‌ها",en:"Plans",loader:adminApi.plans,fields:[["id","شناسه","ID"],["name","پلن","Plan"],["duration_days","مدت","Duration"],["traffic_gb","حجم","Traffic"],["price_toman","قیمت","Price"],["is_active","وضعیت","Status"]]},
  nodes:{fa:"نودها",en:"Nodes",loader:async()=>adminApi.nodes() as unknown as RuntimeRow[],fields:[["id","شناسه","ID"],["name","نام","Name"],["node_type","نوع","Type"],["country_code","کشور","Country"],["public_ip","IP","IP"],["status","وضعیت","Status"]]},
  tunnels:{fa:"تانل‌ها",en:"Tunnels",loader:async()=>adminApi.tunnels() as unknown as RuntimeRow[],fields:[["id","شناسه","ID"],["iran_node_id","نود ایران","Iran node"],["exit_node_id","نود خروج","Exit node"],["transport","Transport","Transport"],["latency_ms","Ping","Ping"],["status","وضعیت","Status"]]},
  payments:{fa:"پرداخت‌ها",en:"Payments",loader:adminApi.payments,fields:[["id","شناسه","ID"],["user_id","کاربر","User"],["amount_toman","مبلغ","Amount"],["method","روش","Method"],["status","وضعیت","Status"],["created_at","تاریخ","Date"]]}
};

function renderValue(key:string,value:unknown,pick:(fa:string,en:string)=>string){
  if(key==="status")return <Badge tone={["active","online","paid","approved"].includes(String(value).toLowerCase())?"ok":["failed","rejected","expired","offline"].includes(String(value).toLowerCase())?"bad":"warn"}>{String(value??"—")}</Badge>;
  if(key==="is_active")return <Badge tone={value?"ok":"bad"}>{value?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge>;
  if(key.includes("price")||key.includes("amount"))return `${Number(value||0).toLocaleString("fa-IR")} ${pick("تومان","Toman")}`;
  if(key.includes("date")||key.endsWith("_at")){if(!value)return "—";try{return new Date(String(value)).toLocaleString("fa-IR");}catch{return String(value)}}
  if(typeof value==="boolean")return value?"✓":"—";
  if(Array.isArray(value))return value.join("، ");
  if(value&&typeof value==="object")return JSON.stringify(value);
  return String(value??"—");
}

export function AdminCollectionRuntime({kind}:{kind:Kind}){
  const {pick}=useI18n();const cfg=configs[kind];
  const [rows,setRows]=useState<RuntimeRow[]>([]);const [loading,setLoading]=useState(true);const [error,setError]=useState("");const [q,setQ]=useState("");
  const load=async()=>{setLoading(true);setError("");try{setRows(await cfg.loader());}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setLoading(false)}};
  useEffect(()=>{void load();},[kind]);
  const filtered=useMemo(()=>{const n=q.trim().toLowerCase();if(!n)return rows;return rows.filter(r=>Object.values(r).some(v=>String(v??"").toLowerCase().includes(n)));},[rows,q]);
  return <Shell active={`/admin/${kind}`}><div className="page admin-runtime-list"><div className="page-head"><div><h1>{pick(cfg.fa,cfg.en)}</h1></div><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div><Card><div className="runtime-toolbar"><label>⌕ <input value={q} onChange={e=>setQ(e.target.value)} placeholder={pick("جستجو...","Search...")}/></label><span>{filtered.length.toLocaleString("fa-IR")}</span></div>{error&&<div className="runtime-error">{error}</div>}{loading?<div className="runtime-loading">{pick("در حال دریافت اطلاعات...","Loading...")}</div>:<div className="table"><table><thead><tr>{cfg.fields.map(([key,fa,en])=><th key={key}>{pick(fa,en)}</th>)}</tr></thead><tbody>{filtered.map((row,i)=><tr key={String(row.id??i)}>{cfg.fields.map(([key])=><td key={key}>{renderValue(key,row[key],pick)}</td>)}</tr>)}</tbody></table></div>}</Card></div></Shell>;
}
