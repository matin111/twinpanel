"use client";

import {useEffect, useMemo, useState} from "react";

import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge, PageHead, Shell} from "./ui";
import styles from "./dns-emergency-panel.module.css";

type NetModNode={
  node_id:number;
  node_name:string;
  public_ip:string;
  status:string;
  tunnel_domain?:string|null;
  nameserver_host?:string|null;
  public_key?:string|null;
  last_error?:string|null;
  checked_at?:string|null;
  last_applied_at?:string|null;
  client_ready:boolean;
};

type Inventory={
  ok:boolean;
  engine:string;
  default_resolver:string;
  resolver_examples:string[];
  source:{repository:string;commit:string};
  nodes:NetModNode[];
};

type InstallResult=NetModNode&{
  ok:boolean;
  dns_instructions?:{
    tunnel_domain:string;
    nameserver_host?:string|null;
    exit_ip:string;
    records:Array<{type:string;name:string;value:string}>;
  };
};

type NetModConfig={
  ok:boolean;
  node_id:number;
  resolver:string;
  nm_dns:string;
  format:string;
  parameters:{
    name:string;
    resolver:string;
    domain:string;
    public_key:string;
    username:string;
  };
};

async function apiRequest<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  const raw=await response.text();
  let payload:unknown=null;
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
  if(!response.ok){
    if(payload&&typeof payload==="object"&&"detail" in payload){
      const detail=(payload as {detail?:unknown}).detail;
      if(typeof detail==="string")throw new Error(detail);
      if(detail&&typeof detail==="object"){
        const value=detail as {message?:unknown;error?:unknown};
        if(value.message)throw new Error(`${String(value.message)}${value.error?` · ${String(value.error)}`:""}`);
      }
    }
    throw new Error(`API error ${response.status}`);
  }
  return payload as T;
}

function statusTone(status:string):"ok"|"warn"|"bad"|"violet"{
  const value=String(status||"").toLowerCase();
  if(value==="online")return "ok";
  if(value==="error"||value==="failed")return "bad";
  if(value==="installing")return "warn";
  return "violet";
}

export function DnsEmergencyPanel(){
  const {pick}=useI18n();
  const [inventory,setInventory]=useState<Inventory|null>(null);
  const [selectedNodeId,setSelectedNodeId]=useState(0);
  const [domain,setDomain]=useState("");
  const [nameserver,setNameserver]=useState("");
  const [resolver,setResolver]=useState("8.8.8.8");
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [netmod,setNetmod]=useState<NetModConfig|null>(null);

  const load=async(silent=false)=>{
    if(!silent)setBusy("load");
    setError("");
    try{
      const data=await apiRequest<Inventory>("/v1/settings/vpn/netmod-dns");
      setInventory(data);
      setResolver(current=>current||data.default_resolver||"8.8.8.8");
      setSelectedNodeId(current=>data.nodes.some(node=>node.node_id===current)?current:(data.nodes[0]?.node_id||0));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{if(!silent)setBusy("");}
  };

  useEffect(()=>{void load();},[]);

  const selected=useMemo(
    ()=>inventory?.nodes.find(node=>node.node_id===selectedNodeId)||null,
    [inventory,selectedNodeId],
  );

  useEffect(()=>{
    if(!selected)return;
    setDomain(selected.tunnel_domain||"");
    setNameserver(selected.nameserver_host||"");
    setNetmod(null);
    setError("");
    setNotice("");
  },[selectedNodeId,selected?.node_id]);

  const fetchConfig=async(nodeId=selected?.node_id)=>{
    if(!nodeId||busy)return;
    setBusy("config");setError("");setNotice("");
    try{
      const result=await apiRequest<NetModConfig>(`/v1/settings/vpn/netmod-dns/${nodeId}/config?resolver=${encodeURIComponent(resolver.trim())}`);
      setNetmod(result);
      setNotice(pick("لینک NetMod آماده است؛ کپی و داخل NetMod Import کنید.","NetMod link is ready; copy and import it into NetMod."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const install=async()=>{
    if(!selected||busy)return;
    if(!domain.trim()){setError(pick("Tunnel Domain را وارد کنید.","Enter the tunnel domain."));return;}
    setBusy("install");setError("");setNotice("");setNetmod(null);
    try{
      await apiRequest<InstallResult>(`/v1/settings/vpn/netmod-dns/${selected.node_id}/install`,{
        method:"POST",
        body:JSON.stringify({tunnel_domain:domain.trim(),nameserver_host:nameserver.trim()||null}),
      });
      await load(true);
      const result=await apiRequest<NetModConfig>(`/v1/settings/vpn/netmod-dns/${selected.node_id}/config?resolver=${encodeURIComponent(resolver.trim())}`);
      setNetmod(result);
      setNotice(pick("NetMod DNS نصب و تست شد؛ لینک Import آماده است.","NetMod DNS was installed and tested; the import link is ready."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const health=async()=>{
    if(!selected||busy)return;
    setBusy("health");setError("");setNotice("");
    try{
      const result=await apiRequest<NetModNode&{ok:boolean}>(`/v1/settings/vpn/netmod-dns/${selected.node_id}/health`,{method:"POST"});
      setNotice(result.ok?pick("Health Check کامل NetMod DNS موفق بود.","NetMod DNS full health check passed."):pick("Health Check ناموفق بود.","Health check failed."));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const remove=async()=>{
    if(!selected||busy)return;
    setBusy("remove");setError("");setNotice("");setNetmod(null);
    try{
      await apiRequest(`/v1/settings/vpn/netmod-dns/${selected.node_id}`,{method:"DELETE"});
      setNotice(pick("NetMod DNS متوقف و از Boot حذف شد.","NetMod DNS was stopped and disabled at boot."));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const copy=async(value:string)=>{
    try{await navigator.clipboard.writeText(value);setNotice(pick("کپی شد.","Copied."));}
    catch{setError(pick("کپی خودکار در این مرورگر در دسترس نیست.","Clipboard access is unavailable in this browser."));}
  };

  return <Shell active="/admin/dns-emergency">
    <PageHead title="NetMod DNS"/>
    <div className={styles.page}>
      <section className={styles.hero}>
        <div>
          <div className={styles.eyebrow}>NetMod · DNSTT · Managed SSH</div>
          <h2>{pick("یک مسیر DNS، یک لینک، Import مستقیم در NetMod","One DNS path, one link, direct NetMod import")}</h2>
          <p>{pick("TwinPanel خودش DNSTT، SSH داخلی و مسیر UDP/53 را مدیریت می‌کند. کاربر فقط لینک nm-dns را داخل NetMod وارد می‌کند.","TwinPanel manages DNSTT, the internal SSH endpoint and UDP/53. The user only imports the nm-dns link into NetMod.")}</p>
        </div>
        <div className={styles.statusBox}>
          <span>{pick("وضعیت","Status")}</span>
          <Badge tone={statusTone(selected?.status||"not_installed")}>{selected?.status||"not_installed"}</Badge>
        </div>
      </section>

      {error&&<div className={styles.error}>{error}</div>}
      {notice&&<div className={styles.notice}>{notice}</div>}

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <div>
            <h3>{pick("۱. سرور و DNS","1. Server and DNS")}</h3>
            <p>{pick("فقط Exit واقعی نمایش داده می‌شود؛ Local Core عمداً از این بخش حذف شده است.","Only real Exit nodes are shown; Local Core is intentionally excluded.")}</p>
          </div>
          <button className={styles.secondary} type="button" disabled={Boolean(busy)} onClick={()=>void load()}>{busy==="load"?pick("در حال دریافت...","Loading..."):pick("بازخوانی","Refresh")}</button>
        </div>
        <div className={styles.grid}>
          <label>
            <span>Exit Node</span>
            <select value={selectedNodeId} onChange={event=>setSelectedNodeId(Number(event.target.value))}>
              {(inventory?.nodes||[]).map(node=><option key={node.node_id} value={node.node_id}>{node.node_name} · {node.public_ip}</option>)}
            </select>
          </label>
          <label>
            <span>DNS Resolver</span>
            <input list="netmod-resolvers" value={resolver} onChange={event=>setResolver(event.target.value)} dir="ltr" placeholder="8.8.8.8"/>
            <datalist id="netmod-resolvers">{(inventory?.resolver_examples||[]).map(value=><option value={value} key={value}/>)}</datalist>
          </label>
          <label>
            <span>Tunnel Domain</span>
            <input value={domain} onChange={event=>setDomain(event.target.value)} placeholder="t.example.com" dir="ltr"/>
          </label>
          <label>
            <span>{pick("Nameserver Host","Nameserver Host")}</span>
            <input value={nameserver} onChange={event=>setNameserver(event.target.value)} placeholder="dns.example.com" dir="ltr"/>
          </label>
        </div>
        <div className={styles.hint}>
          <b>{pick("رکوردهای DNS","DNS records")}</b>
          <code>A {nameserver||"dns.example.com"} → {selected?.public_ip||"EXIT_IP"}</code>
          <code>NS {domain||"t.example.com"} → {nameserver||"dns.example.com"}</code>
        </div>
      </section>

      <section className={styles.actions}>
        <button className={styles.primary} type="button" onClick={()=>void install()} disabled={Boolean(busy)||!selected}>{busy==="install"?pick("در حال نصب و تست...","Installing and testing..."):pick("نصب / Repair","Install / Repair")}</button>
        <button className={styles.secondary} type="button" onClick={()=>void health()} disabled={Boolean(busy)||!selected||selected.status==="not_installed"}>{busy==="health"?pick("در حال تست...","Checking..."):"Health Check"}</button>
        <button className={styles.secondary} type="button" onClick={()=>void fetchConfig()} disabled={Boolean(busy)||!selected?.client_ready}>{busy==="config"?pick("در حال ساخت لینک...","Building link..."):pick("دریافت لینک NetMod","Get NetMod link")}</button>
        <button className={styles.danger} type="button" onClick={()=>void remove()} disabled={Boolean(busy)||!selected||selected.status==="not_installed"}>{busy==="remove"?pick("در حال حذف...","Removing..."):pick("توقف و حذف سرویس","Stop and remove")}</button>
      </section>

      {netmod&&<section className={styles.card}>
        <h3>{pick("۲. لینک آماده NetMod","2. NetMod import link")}</h3>
        <p>{pick("این لینک محرمانه است. آن را Copy کنید و در NetMod Import کنید؛ تنظیم دستی دیگری لازم نیست.","This link is secret. Copy it and import it into NetMod; no other manual setup is required.")}</p>
        <div className={styles.kv}>
          <span>nm-dns://</span><code>{netmod.nm_dns}</code><button type="button" onClick={()=>void copy(netmod.nm_dns)}>{pick("کپی لینک","Copy link")}</button>
          <span>Resolver</span><code>{netmod.parameters.resolver}</code><button type="button" onClick={()=>void copy(netmod.parameters.resolver)}>{pick("کپی","Copy")}</button>
          <span>Domain</span><code>{netmod.parameters.domain}</code><button type="button" onClick={()=>void copy(netmod.parameters.domain)}>{pick("کپی","Copy")}</button>
        </div>
        <div className={styles.warning}>
          <b>{pick("محرمانه","Secret")}</b>
          <span>{pick("لینک شامل دسترسی داخلی SSH است؛ آن را عمومی منتشر نکنید.","The link contains internal SSH access; do not publish it publicly.")}</span>
        </div>
      </section>}

      <section className={styles.footerNote}>
        <span>DNSTT: OutlineFoundation/dnstt</span>
        <code>{inventory?.source.commit||"—"}</code>
        <span>{pick("خروجی: nm-dns://","Output: nm-dns://")}</span>
      </section>
    </div>
  </Shell>;
}
