"use client";

import {useState} from "react";
import {createPortal} from "react-dom";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {legacyAdminApi,type ClassicProtocolKey} from "../lib/legacy-admin-api";

type Pick=(fa:string,en:string)=>string;
type NodeChoice={id:number;name:string;status:string;kind:"classic"|"modern"};
type ModernInventory={nodes:Array<{id:number;name:string;status:string;protocols:Array<{protocol:string;status:string;runtime_status?:string;port?:number}>}>};
type RestartResult={ok?:boolean;message?:string;protocol?:{ok?:boolean;error?:string}};
const CLASSIC=new Set(["cisco","openvpn","wireguard","l2tp","v2ray"]);
const STANDALONE=new Set(["mieru","trusttunnel","amneziawg","sudoku"]);

async function protectedRequest<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body)headers.set("Content-Type","application/json");
  const response=await fetch(API_BASE+path,{...init,headers,cache:"no-store"});
  const data:unknown=await response.json().catch(()=>null);
  if(!response.ok){
    const item=data&&typeof data==="object"?data as {detail?:unknown;message?:unknown}:null;
    throw new Error(typeof item?.detail==="string"?item.detail:typeof item?.message==="string"?item.message:`HTTP ${response.status}`);
  }
  return data as T;
}

export function DashboardProtocolRestart({protocol,label,pick,onComplete}:{protocol:string;label:string;pick:Pick;onComplete?:()=>void}){
  const [open,setOpen]=useState(false);
  const [loading,setLoading]=useState(false);
  const [busy,setBusy]=useState(false);
  const [choices,setChoices]=useState<NodeChoice[]>([]);
  const [selected,setSelected]=useState<number|null>(null);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const isClassic=CLASSIC.has(protocol);
  const hasSharedCore=!isClassic&&!STANDALONE.has(protocol);

  const show=async()=>{
    if(busy||loading)return;
    setOpen(true);setLoading(true);setError("");setNotice("");setChoices([]);setSelected(null);
    try{
      let available:NodeChoice[];
      if(isClassic){
        const inventory=await legacyAdminApi.classicProtocols();
        available=(inventory.nodes||[]).filter(node=>
          (node.protocols||[]).some(row=>row.protocol===protocol&&row.enabled)
        ).map(node=>({id:node.id,name:node.name,status:node.status,kind:"classic" as const}));
      }else{
        const inventory=await protectedRequest<ModernInventory>("/v1/settings/vpn/modern-protocols");
        available=(inventory.nodes||[]).filter(node=>
          (node.protocols||[]).some(row=>row.protocol===protocol&&
            !["not_installed","uninstalled","missing"].includes(String(row.status||"").toLowerCase())&&
            Number(row.port||0)>0)
        ).map(node=>({id:node.id,name:node.name,status:node.status,kind:"modern" as const}));
      }
      setChoices(available);
      if(available.length===1)setSelected(available[0].id);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setLoading(false);}
  };
  const close=()=>{if(!busy)setOpen(false);};
  const restart=async()=>{
    const node=choices.find(row=>row.id===selected);
    if(!node||busy)return;
    setBusy(true);setError("");setNotice("");
    try{
      if(node.kind==="classic"){
        const result=await legacyAdminApi.restartProtocol(node.id,protocol as ClassicProtocolKey);
        if(result?.protocol&&typeof result.protocol==="object"&&
          (result.protocol as RestartResult).ok===false){
          throw new Error(String((result.protocol as RestartResult).error||pick("بررسی سلامت ناموفق بود","Health check failed")));
        }
      }else{
        const result=await protectedRequest<RestartResult>(
          `/v1/settings/vpn/modern-protocols/${node.id}/${encodeURIComponent(protocol)}/restart`,
          {method:"POST"}
        );
        if(result.ok===false)throw new Error(result.message||pick("ریستارت یا بررسی سلامت ناموفق بود","Restart or health check failed"));
      }
      setNotice(pick("دستور ریست انجام شد. وضعیت سرویس را بررسی کنید.","Restart request completed. Verify runtime status."));
      onComplete?.();
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };
  return <>
    <button type="button" onClick={()=>void show()} title={pick("ریست سرویس "+label,"Restart "+label)}
      style={{flex:"0 0 auto",font:"inherit",fontSize:10,fontWeight:850,color:"var(--text,#e8edff)",background:"color-mix(in srgb,var(--surface,#1a2440) 85%,transparent)",border:"1px solid var(--line,#394560)",borderRadius:8,padding:"5px 7px",cursor:"pointer",whiteSpace:"nowrap"}}>
      ↻ {pick("ریست","Restart")}
    </button>
    {open&&createPortal(<div role="dialog" aria-modal="true" aria-label={pick("ریست پروتکل","Restart protocol")} dir="rtl"
      style={{position:"fixed",inset:0,zIndex:100010,display:"grid",placeItems:"center",padding:16}}>
      <button aria-label={pick("بستن","Close")} type="button" onClick={close} disabled={busy}
        style={{position:"absolute",inset:0,width:"100%",height:"100%",border:0,background:"rgba(0,0,0,.66)",cursor:"pointer"}}/>
      <div style={{position:"relative",width:"min(470px,100%)",maxHeight:"85vh",overflowY:"auto",borderRadius:18,background:"var(--surface,#131a2c)",color:"var(--text,#edf2ff)",border:"1px solid var(--line,#3c4660)",padding:20,boxShadow:"0 20px 60px #0008",display:"grid",gap:13}}>
        <div style={{display:"flex",justifyContent:"space-between",gap:10,alignItems:"center"}}>
          <strong style={{fontSize:16}}>{pick("ریست پروتکل","Restart protocol")}: {label}</strong>
          <button type="button" onClick={close} disabled={busy} aria-label={pick("بستن","Close")}>✕</button>
        </div>
        <small style={{color:"var(--muted,#9ba9c1)"}}>
          {pick("فقط سرویس انتخاب‌شده در نود مشخص ریست می‌شود؛ حجم کاربران و کانفیگ‌ها تغییر نمی‌کنند.",
            "Only the selected node runtime is restarted; quotas and configurations are unchanged.")}
        </small>
        {hasSharedCore&&<p style={{margin:0,padding:10,borderRadius:10,border:"1px solid #c99a4f",color:"#dfac59",fontSize:12}}>
          {pick("هشدار: این پروتکل روی sing-box مشترک است و ریست آن می‌تواند اتصال سایر پروتکل‌های مدرن همین نود را نیز موقتاً قطع کند.",
            "Warning: the shared sing-box restart can briefly interrupt other modern protocols on this node.")}
        </p>}
        {loading?<span>{pick("در حال بررسی نودهای دارای این پروتکل…","Checking installed nodes…")}</span>:choices.length?
          <label style={{display:"grid",gap:7,fontSize:13}}>{pick("انتخاب نود","Choose node")}
            <select value={selected??""} disabled={busy} onChange={e=>setSelected(e.target.value?Number(e.target.value):null)}
              style={{background:"var(--surface2,#1a2940)",color:"var(--text,#e8edff)",border:"1px solid var(--line,#3c4660)",borderRadius:9,padding:10}}>
              <option value="">{pick("نود را انتخاب کنید","Select a node")}</option>
              {choices.map(node=><option key={node.id} value={node.id}>{node.name} (#{node.id})</option>)}
            </select>
          </label>:!error?<small>{pick("نودی با نصب تأییدشده این پروتکل پیدا نشد.","No node with verified installed protocol was found.")}</small>:null}
        {error&&<div role="alert" style={{color:"#e99aa7",fontSize:12}}>{error}</div>}
        {notice&&<div role="status" style={{color:"#37c7a5",fontSize:12}}>{notice}</div>}
        <div style={{display:"flex",justifyContent:"flex-end",gap:9}}>
          <button type="button" onClick={close} disabled={busy}>{pick("بستن","Close")}</button>
          <button type="button" onClick={()=>void restart()} disabled={busy||loading||selected===null||Boolean(notice)}
            style={{padding:"9px 15px",background:"#7b5be8",color:"white",border:0,borderRadius:9,cursor:"pointer"}}>
            {busy?pick("در حال ریست…","Restarting…"):pick("تأیید ریست پروتکل","Confirm restart")}
          </button>
        </div>
      </div>
    </div>,document.body)}
  </>;
}
