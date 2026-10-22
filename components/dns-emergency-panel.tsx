"use client";

import {useEffect, useMemo, useState} from "react";

import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge, PageHead, Shell} from "./ui";
import styles from "./dns-emergency-panel.module.css";

type Candidate={
  protocol:string;
  port:number;
  transport:string;
  service:string;
  status:string;
  recommended:boolean;
};

type ClientInfo={
  engine:string;
  domain:string;
  public_key:string;
  local_listen:string;
  command_example:string;
  nm_dns:null;
  nm_dns_reason:string;
};

type DnsNode={
  node_id:number;
  node_name:string;
  public_ip:string;
  status:string;
  tunnel_domain?:string|null;
  nameserver_host?:string|null;
  upstream_port?:number|null;
  public_key?:string|null;
  last_error?:string|null;
  checked_at?:string|null;
  last_applied_at?:string|null;
  dnstt_commit:string;
  upstream_candidates:Candidate[];
  client?:ClientInfo|null;
};

type Inventory={
  ok:boolean;
  engine:string;
  source:{repository:string;commit:string};
  nodes:DnsNode[];
};

type InstallResult=DnsNode&{
  ok:boolean;
  dns_instructions?:{
    tunnel_domain:string;
    nameserver_host?:string|null;
    exit_ip:string;
    records:Array<{type:string;name:string;value:string}>;
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
      if(detail&&typeof detail==="object"&&"message" in detail){
        throw new Error(String((detail as {message?:unknown}).message||`API error ${response.status}`));
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
  const [upstreamPort,setUpstreamPort]=useState(0);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [lastInstall,setLastInstall]=useState<InstallResult|null>(null);

  const load=async(silent=false)=>{
    if(!silent)setBusy("load");
    setError("");
    try{
      const data=await apiRequest<Inventory>("/v1/settings/vpn/dns-emergency");
      setInventory(data);
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
    const preferred=selected.upstream_candidates.find(item=>item.recommended)||selected.upstream_candidates[0];
    setUpstreamPort(Number(selected.upstream_port||preferred?.port||0));
    setLastInstall(null);
    setError("");
    setNotice("");
  },[selectedNodeId,selected?.node_id]);

  const install=async()=>{
    if(!selected||busy)return;
    if(!domain.trim()){setError(pick("دامنه Tunnel را وارد کنید.","Enter the tunnel domain."));return;}
    if(!upstreamPort){setError(pick("سرویس TCP مقصد را انتخاب کنید.","Select a TCP upstream service."));return;}
    setBusy("install");setError("");setNotice("");
    try{
      const result=await apiRequest<InstallResult>(`/v1/settings/vpn/dns-emergency/${selected.node_id}/install`,{
        method:"POST",
        body:JSON.stringify({
          tunnel_domain:domain.trim(),
          nameserver_host:nameserver.trim()||null,
          upstream_port:Number(upstreamPort),
        }),
      });
      setLastInstall(result);
      setNotice(pick("DNS Emergency نصب شد و سرویس/Listener/Upstream سالم است.","DNS Emergency was installed and its service/listener/upstream are healthy."));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const health=async()=>{
    if(!selected||busy)return;
    setBusy("health");setError("");setNotice("");
    try{
      const result=await apiRequest<DnsNode&{ok:boolean}>(`/v1/settings/vpn/dns-emergency/${selected.node_id}/health`,{method:"POST"});
      setNotice(result.ok?pick("Health Check موفق بود.","Health check passed."):pick("Health Check ناموفق بود؛ جزئیات وضعیت را بررسی کنید.","Health check failed; review runtime status."));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const remove=async()=>{
    if(!selected||busy)return;
    setBusy("remove");setError("");setNotice("");
    try{
      await apiRequest(`/v1/settings/vpn/dns-emergency/${selected.node_id}`,{method:"DELETE"});
      setNotice(pick("DNS Emergency متوقف و از Boot حذف شد؛ کلیدها برای نصب مجدد حفظ شدند.","DNS Emergency was stopped and disabled at boot; keys were preserved for reinstall."));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const copy=async(value:string)=>{
    try{await navigator.clipboard.writeText(value);setNotice(pick("کپی شد.","Copied."));}
    catch{setError(pick("کپی خودکار در این مرورگر در دسترس نیست.","Clipboard access is unavailable in this browser."));}
  };

  const client=lastInstall?.client||selected?.client||null;
  const dnsRecords=lastInstall?.dns_instructions?.records||[];

  return <Shell active="/admin/dns-emergency">
    <PageHead title={pick("DNS اضطراری","DNS Emergency")}/>
    <div className={styles.page}>
      <section className={styles.hero}>
        <div>
          <div className={styles.eyebrow}>DNSTT · Emergency TCP Transport</div>
          <h2>{pick("مسیر اضطراری برای شرایطی که فقط DNS عبور می‌کند","Emergency path for DNS-only connectivity")}</h2>
          <p>{pick("این لایه یک سرویس TCP موجود روی همان Exit را داخل DNS حمل می‌کند؛ احراز هویت و Quota پروتکل اصلی تغییر نمی‌کند.","This layer carries an existing TCP service on the same Exit through DNS; the original protocol authentication and quota remain unchanged.")}</p>
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
            <h3>{pick("۱. Exit و سرویس مقصد","1. Exit and upstream service")}</h3>
            <p>{pick("DNSTT فقط TCP حمل می‌کند؛ یک سرویس TCP فعال روی همان Exit انتخاب کنید.","DNSTT carries TCP only; choose an active TCP service on the same Exit.")}</p>
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
            <span>{pick("TCP مقصد","TCP upstream")}</span>
            <select value={upstreamPort} onChange={event=>setUpstreamPort(Number(event.target.value))}>
              {!selected?.upstream_candidates.length&&<option value={0}>{pick("سرویس TCP شناخته‌شده‌ای پیدا نشد","No known TCP service found")}</option>}
              {(selected?.upstream_candidates||[]).map(item=><option key={`${item.protocol}:${item.port}`} value={item.port}>{item.protocol} · {item.port} · {item.transport}{item.recommended?" ✓":""}</option>)}
            </select>
          </label>
        </div>
      </section>

      <section className={styles.card}>
        <h3>{pick("۲. DNS Delegation","2. DNS delegation")}</h3>
        <p>{pick("یک Subdomain را به Nameserverای که به IP همین Exit اشاره می‌کند Delegate کنید.","Delegate a subdomain to a nameserver pointing to this Exit IP.")}</p>
        <div className={styles.grid}>
          <label>
            <span>Tunnel Domain</span>
            <input value={domain} onChange={event=>setDomain(event.target.value)} placeholder="t.example.com" dir="ltr"/>
          </label>
          <label>
            <span>{pick("Nameserver Host (اختیاری)","Nameserver Host (optional)")}</span>
            <input value={nameserver} onChange={event=>setNameserver(event.target.value)} placeholder="dns.example.com" dir="ltr"/>
          </label>
        </div>
        <div className={styles.hint}>
          <b>{pick("رکورد پیشنهادی","Suggested records")}</b>
          <code>A/AAAA {nameserver||"dns.example.com"} → {selected?.public_ip||"EXIT_IP"}</code>
          <code>NS {domain||"t.example.com"} → {nameserver||"dns.example.com"}</code>
        </div>
      </section>

      <section className={styles.actions}>
        <button className={styles.primary} type="button" onClick={()=>void install()} disabled={Boolean(busy)||!selected}>{busy==="install"?pick("در حال نصب و تست...","Installing and testing..."):pick("نصب / Repair و Health Check","Install / Repair + Health Check")}</button>
        <button className={styles.secondary} type="button" onClick={()=>void health()} disabled={Boolean(busy)||!selected||selected.status==="not_installed"}>{busy==="health"?pick("در حال تست...","Checking..."):"Health Check"}</button>
        <button className={styles.danger} type="button" onClick={()=>void remove()} disabled={Boolean(busy)||!selected||selected.status==="not_installed"}>{busy==="remove"?pick("در حال حذف...","Removing..."):pick("توقف و حذف سرویس","Stop and remove service")}</button>
      </section>

      {dnsRecords.length>0&&<section className={styles.card}>
        <h3>{pick("DNS آماده ثبت","DNS records ready to publish")}</h3>
        <div className={styles.records}>{dnsRecords.map(record=><div key={`${record.type}:${record.name}`}><b>{record.type}</b><code>{record.name}</code><span>→</span><code>{record.value}</code></div>)}</div>
      </section>}

      {client&&<section className={styles.card}>
        <h3>{pick("۳. اطلاعات کلاینت","3. Client parameters")}</h3>
        <p>{pick("کلید عمومی و دستور استاندارد dnstt. کلید خصوصی فقط روی Exit نگه‌داری می‌شود.","Public key and standard dnstt command. The private key stays only on the Exit.")}</p>
        <div className={styles.kv}>
          <span>Domain</span><code>{client.domain}</code><button type="button" onClick={()=>void copy(client.domain)}>{pick("کپی","Copy")}</button>
          <span>Public key</span><code>{client.public_key}</code><button type="button" onClick={()=>void copy(client.public_key)}>{pick("کپی","Copy")}</button>
          <span>Client</span><code>{client.command_example}</code><button type="button" onClick={()=>void copy(client.command_example)}>{pick("کپی","Copy")}</button>
        </div>
        <div className={styles.warning}>
          <b>nm-dns://</b>
          <span>{pick("TwinPanel فعلاً لینک NetMod را جعل نمی‌کند؛ فرمت nm-dns رمزگذاری‌شده است و Schema عمومی قابل‌اتکایی برای تولید آن پیدا نشد.","TwinPanel does not fabricate NetMod links; nm-dns is opaque/encrypted and no reliable public generation schema was found.")}</span>
        </div>
      </section>}

      <section className={styles.footerNote}>
        <span>Source: OutlineFoundation/dnstt</span>
        <code>{inventory?.source.commit||"—"}</code>
        <span>{pick("Pinned؛ بدون @latest","Pinned; no @latest")}</span>
      </section>
    </div>
  </Shell>;
}
