"use client";

import {useEffect,useMemo,useState} from "react";
import Link from "next/link";
import {PortalShell} from "./portal-shells";
import {Badge,Card,PageHead} from "./ui";
import {customerApi,CustomerConnectionInfo,MySubscription} from "../lib/customer-api";
import {useCustomerSession} from "../lib/customer-session";
import {useI18n} from "../lib/i18n";

const statusFa=(v:string)=>({active:"فعال",pending:"در انتظار",suspended:"تعلیق",expired:"منقضی",canceled:"لغو شده"} as Record<string,string>)[v]||v;
const tone=(v:string):"ok"|"warn"|"bad"|"violet"=>v==="active"?"ok":["expired","canceled"].includes(v)?"bad":"warn";
const pct=(u:number,l:number)=>l>0?Math.min(100,Math.max(0,Math.round(u/l*100))):0;
const protocol=(v:string)=>({cisco:"Cisco / OpenConnect",openvpn:"OpenVPN",wireguard:"WireGuard",l2tp:"L2TP / IPsec",v2ray:"V2Ray / Xray",xray:"V2Ray / Xray"} as Record<string,string>)[v]||v;

function absoluteLink(value:string){
  if(typeof window==="undefined")return value;
  try{return new URL(value,window.location.origin).toString();}catch{return value;}
}

function Body(){
  const {pick}=useI18n();
  const {token}=useCustomerSession();
  const [rows,setRows]=useState<MySubscription[]>([]);
  const [filter,setFilter]=useState<"active"|"all">("active");
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState<number|null>(null);
  const [connectionBusy,setConnectionBusy]=useState<number|null>(null);
  const [connections,setConnections]=useState<Record<number,CustomerConnectionInfo>>({});
  const [visiblePasswords,setVisiblePasswords]=useState<Record<number,boolean>>({});
  const [copied,setCopied]=useState("");

  const load=async()=>{
    if(!token)return;
    setLoading(true);setError("");
    try{
      const data=await customerApi.subscriptions(token);
      setRows(data);
      const active=data.filter(x=>x.status==="active");
      const results=await Promise.allSettled(active.map(x=>customerApi.connectionInfo(token,x.id)));
      const next:Record<number,CustomerConnectionInfo>={};
      results.forEach((result,index)=>{if(result.status==="fulfilled")next[active[index].id]=result.value;});
      setConnections(next);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setLoading(false);}
  };

  useEffect(()=>{void load();},[token]);
  const shown=useMemo(()=>filter==="all"?rows:rows.filter(x=>x.status==="active"),[rows,filter]);

  const renew=async(id:number)=>{
    if(!token)return;
    setBusy(id);setError("");
    try{
      const order=await customerApi.renewSubscription(token,id);
      window.location.href=`/panel/payments?order=${order.id}`;
    }catch(e){setError(e instanceof Error?e.message:String(e));setBusy(null);}
  };

  const ensureConnection=async(id:number)=>{
    if(!token||connections[id])return;
    setConnectionBusy(id);setError("");
    try{
      const result=await customerApi.connectionInfo(token,id);
      setConnections(current=>({...current,[id]:result}));
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setConnectionBusy(null);}
  };

  const copyValue=async(key:string,value:string)=>{
    try{
      await navigator.clipboard.writeText(value);
      setCopied(key);
      window.setTimeout(()=>setCopied(""),1400);
    }catch{setError(pick("کپی انجام نشد.","Could not copy."));}
  };

  return <div className="page customer-runtime customerSubscriptionsParity">
    <PageHead title={pick("اشتراک‌های من","My subscriptions")}/>
    <div className="customerSubToolbar">
      <div>
        <button className={filter==="active"?"active":""} onClick={()=>setFilter("active")}>{pick("فعال","Active")} <b>{rows.filter(x=>x.status==="active").length.toLocaleString("fa-IR")}</b></button>
        <button className={filter==="all"?"active":""} onClick={()=>setFilter("all")}>{pick("همه","All")} <b>{rows.length.toLocaleString("fa-IR")}</b></button>
      </div>
      <Link className="primary" href="/panel/buy">＋ {pick("خرید اشتراک","Buy subscription")}</Link>
    </div>

    {error&&<div className="runtime-error">{error}</div>}

    {loading?<div className="customer-loading"><span className="customer-loader"/></div>:shown.length===0?<Card className="customer-empty"><p>{pick("اشتراکی برای نمایش وجود ندارد.","No subscriptions to show.")}</p></Card>:<div className="customerSubGrid">{shown.map(row=>{
      const usage=pct(row.traffic_used_gb,row.traffic_limit_gb);
      const connection=connections[row.id];
      const link=connection?.subscription_link||"";
      const username=connection?.account?.username||"";
      const password=connection?.account?.password||"";
      const showPassword=Boolean(visiblePasswords[row.id]);
      return <Card key={row.id} className={`customerSubCard ${row.status==="active"?"active":""}`}>
        <div className="card-head"><div><small>#{row.id}</small><h3>{row.plan_name||`Plan #${row.plan_id}`}</h3></div><Badge tone={tone(row.status)}>{statusFa(row.status)}</Badge></div>

        <div className="customerSubStats">
          <span><small>{pick("روز باقی‌مانده","Days left")}</small><b>{row.days_remaining.toLocaleString("fa-IR")}</b></span>
          <span><small>{pick("دستگاه","Devices")}</small><b>{row.device_limit.toLocaleString("fa-IR")}</b></span>
          <span><small>{pick("حجم باقی‌مانده","Traffic left")}</small><b>{row.traffic_remaining_gb.toLocaleString("fa-IR")} GB</b></span>
        </div>

        <div className="customerSubTraffic"><div><span>{pick("مصرف","Usage")}</span><b>{usage}%</b></div><div className="progress"><i style={{width:`${usage}%`}}/></div><small>{row.traffic_used_gb.toLocaleString("fa-IR")} / {row.traffic_limit_gb.toLocaleString("fa-IR")} GB</small></div>

        <div className="customerSubProtocols">{row.protocols.map(p=><span key={p}>{protocol(p)}</span>)}</div>

        {row.status==="active"&&<section className="customerSubCredentials">
          <div className="customerSubCredentialsHead"><b>{pick("اطلاعات اتصال","Connection info")}</b>{!connection&&<button type="button" className="ghost" disabled={connectionBusy===row.id} onClick={()=>void ensureConnection(row.id)}>{connectionBusy===row.id?"…":pick("دریافت اطلاعات","Load")}</button>}</div>

          {connection&&<>
            <div className="customerSubSecretRow">
              <span>{pick("نام کاربری","Username")}</span>
              <code dir="ltr">{username||"—"}</code>
              {username&&<button type="button" onClick={()=>void copyValue(`user-${row.id}`,username)}>{copied===`user-${row.id}`?"✓":pick("کپی","Copy")}</button>}
            </div>

            <div className="customerSubSecretRow">
              <span>{pick("رمز عبور","Password")}</span>
              <code dir="ltr">{password?(showPassword?password:"••••••••••"):"—"}</code>
              {password&&<button type="button" onClick={()=>setVisiblePasswords(current=>({...current,[row.id]:!current[row.id]}))}>{showPassword?pick("مخفی","Hide"):pick("نمایش","Show")}</button>}
              {password&&<button type="button" onClick={()=>void copyValue(`pass-${row.id}`,password)}>{copied===`pass-${row.id}`?"✓":pick("کپی","Copy")}</button>}
            </div>

            <div className="customerSubSecretRow link">
              <span>{pick("لینک اتصال","Connection link")}</span>
              <code dir="ltr">{link?absoluteLink(link):"—"}</code>
              {link&&<button type="button" onClick={()=>void copyValue(`link-${row.id}`,absoluteLink(link))}>{copied===`link-${row.id}`?"✓":pick("کپی","Copy")}</button>}
              {link&&<button type="button" onClick={()=>window.open(absoluteLink(link),"_blank","noopener,noreferrer")}>{pick("باز کردن","Open")}</button>}
            </div>
          </>}
        </section>}

        <div className="customerSubActions">
          <button className="primary" disabled={busy===row.id} onClick={()=>void renew(row.id)}>{busy===row.id?"…":pick("تمدید","Renew")}</button>
        </div>
      </Card>;
    })}</div>}
  </div>;
}

export function CustomerSubscriptionsRuntime(){return <PortalShell type="customer" active="/panel/subscription"><Body/></PortalShell>;}
