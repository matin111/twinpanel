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

type PerformanceStatus={
  ok:boolean;
  node_id:number;
  mtu:number;
  effective_mtu:string;
  formerr_recent:boolean;
  resolver_presets?:Array<{label:string;resolver:string}>;
  measurement_scope?:string;
  note?:string;
};

type ResolverProfile={
  label:string;
  resolver:string;
  name:string;
  nm_dns:string;
};

type ResolverBundle={
  ok:boolean;
  node_id:number;
  secret:boolean;
  mode:string;
  profiles:ResolverProfile[];
  instructions:string;
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
  const [performance,setPerformance]=useState<PerformanceStatus|null>(null);
  const [profiles,setProfiles]=useState<ResolverProfile[]>([]);
  const [mtu,setMtu]=useState(1232);

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

  const loadPerformance=async(nodeId:number,silent=false)=>{
    if(!nodeId)return;
    if(!silent)setBusy("performance");
    try{
      const result=await apiRequest<PerformanceStatus>(`/v1/settings/vpn/netmod-dns/${nodeId}/performance`);
      setPerformance(result);
      setMtu(result.mtu||1232);
    }catch(reason){
      if(!silent)setError(reason instanceof Error?reason.message:String(reason));
    }finally{if(!silent)setBusy("");}
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
    setProfiles([]);
    setPerformance(null);
    setMtu(1232);
    setError("");
    setNotice("");
    if(selected.client_ready)void loadPerformance(selected.node_id,true);
  },[selectedNodeId,selected?.node_id,selected?.client_ready]);

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
    setBusy("install");setError("");setNotice("");setNetmod(null);setProfiles([]);
    try{
      await apiRequest<InstallResult>(`/v1/settings/vpn/netmod-dns/${selected.node_id}/install`,{
        method:"POST",
        body:JSON.stringify({tunnel_domain:domain.trim(),nameserver_host:nameserver.trim()||null}),
      });
      await load(true);
      const result=await apiRequest<NetModConfig>(`/v1/settings/vpn/netmod-dns/${selected.node_id}/config?resolver=${encodeURIComponent(resolver.trim())}`);
      setNetmod(result);
      await loadPerformance(selected.node_id,true);
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
      if(result.ok)await loadPerformance(selected.node_id,true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const fetchProfiles=async()=>{
    if(!selected?.client_ready||busy)return;
    setBusy("profiles");setError("");setNotice("");
    try{
      const result=await apiRequest<ResolverBundle>(`/v1/settings/vpn/netmod-dns/${selected.node_id}/performance/profiles`);
      setProfiles(result.profiles);
      setNotice(pick("چهار پروفایل Resolver ساخته شد؛ هر بار فقط یکی را در NetMod با VPN Mode تست کنید.","Four resolver profiles are ready; test one at a time in NetMod VPN mode."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const applyMtu=async()=>{
    if(!selected?.client_ready||busy)return;
    setBusy("mtu");setError("");setNotice("");
    try{
      const result=await apiRequest<PerformanceStatus>(`/v1/settings/vpn/netmod-dns/${selected.node_id}/performance/mtu`,{
        method:"POST",
        body:JSON.stringify({mtu}),
      });
      await loadPerformance(selected.node_id,true);
      setNotice(result.formerr_recent
        ? pick("MTU اعمال شد، اما FORMERR در لاگ اخیر دیده شده؛ اگر اتصال افت کرد به 1232 یا 512 برگردید.","MTU applied, but a recent FORMERR was detected; revert to 1232 or 512 if connectivity degrades.")
        : pick("MTU اعمال شد و DNSTT/Listener سالم بالا آمد. حالا با همان پروفایل Speedtest واقعی بگیرید.","MTU applied and DNSTT/listener restarted cleanly. Run a real Speedtest with the same profile now."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const remove=async()=>{
    if(!selected||busy)return;
    setBusy("remove");setError("");setNotice("");setNetmod(null);setProfiles([]);setPerformance(null);
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

      {selected?.client_ready&&<section className={styles.card}>
        <div className={styles.cardHead}>
          <div>
            <h3>{pick("۳. آزمایشگاه سرعت NetMod DNS","3. NetMod DNS Performance Lab")}</h3>
            <p>{pick("کیفیت Resolver باید از مسیر واقعی NetMod روی دستگاه کاربر سنجیده شود؛ TwinPanel عمداً از روی Exit رتبه‌بندی جعلی نمی‌سازد.","Resolver quality must be measured on the real NetMod client path; TwinPanel intentionally does not fabricate an Exit-side ranking.")}</p>
          </div>
          <button className={styles.secondary} type="button" disabled={Boolean(busy)} onClick={()=>selected&&void loadPerformance(selected.node_id)}>{busy==="performance"?pick("در حال دریافت...","Loading..."):pick("وضعیت Performance","Performance status")}</button>
        </div>

        <div className={styles.performanceGrid}>
          <div className={styles.metric}><span>Configured MTU</span><strong>{performance?.mtu??"—"}</strong></div>
          <div className={styles.metric}><span>Effective MTU</span><strong>{performance?.effective_mtu??"—"}</strong></div>
          <div className={styles.metric}><span>Resolver Test</span><strong>{profiles.length?`${profiles.length} profiles`:"—"}</strong></div>
          <div className={styles.metric}><span>FORMERR</span><strong>{performance?.formerr_recent?pick("دیده شده","Detected"):pick("ندیده شده","Clear")}</strong></div>
        </div>

        <div className={styles.performanceControls}>
          <div>
            <h4>{pick("Resolverهای تست","Resolver test profiles")}</h4>
            <p>{pick("۴ لینک با credential یکسان و نام جدا ساخته می‌شود. هر بار یکی را Import کنید، NetMod را روی VPN Mode بگذارید و Ping/Download/Upload را مقایسه کنید.","Four links are generated with the same credential and distinct names. Import one at a time, use NetMod VPN mode, and compare ping/download/upload.")}</p>
            <button className={styles.secondary} type="button" onClick={()=>void fetchProfiles()} disabled={Boolean(busy)}>{busy==="profiles"?pick("در حال ساخت...","Building..."):pick("ساخت ۴ پروفایل Resolver","Build 4 resolver profiles")}</button>
          </div>
          <div>
            <h4>DNSTT MTU</h4>
            <p>{pick("1232 پیش‌فرض رسمی DNSTT است. 512 برای سازگاری و 1400/1452 فقط برای تست Performance هستند؛ اگر Restart یا Listener خراب شود TwinPanel خودکار rollback می‌کند.","1232 is DNSTT's official default. 512 is for compatibility; 1400/1452 are performance experiments. TwinPanel automatically rolls back if restart or listener validation fails.")}</p>
            <div className={styles.mtuControl}>
              <select value={mtu} onChange={event=>setMtu(Number(event.target.value))}>
                <option value={512}>512 · Compatibility</option>
                <option value={1232}>1232 · Default</option>
                <option value={1400}>1400 · Performance test</option>
                <option value={1452}>1452 · Experimental max</option>
              </select>
              <button className={styles.primary} type="button" onClick={()=>void applyMtu()} disabled={Boolean(busy)}>{busy==="mtu"?pick("در حال اعمال...","Applying..."):pick("اعمال MTU","Apply MTU")}</button>
            </div>
          </div>
        </div>

        {profiles.length>0&&<div className={styles.profileList}>
          {profiles.map(profile=><div className={styles.profileRow} key={profile.resolver}>
            <div><b>{profile.label}</b><code>{profile.resolver}</code><span>{profile.name}</span></div>
            <button className={styles.secondary} type="button" onClick={()=>void copy(profile.nm_dns)}>{pick("کپی لینک تست","Copy test link")}</button>
          </div>)}
        </div>}

        {performance?.formerr_recent&&<div className={styles.formerr}>
          {pick("DNSTT در لاگ اخیر محدودیت اندازه پاسخ DNS را گزارش کرده است. برای پایداری ابتدا 1232 و در صورت ادامه خطا 512 را تست کنید.","DNSTT recently reported a DNS response-size limit. Test 1232 first, then 512 if the error persists.")}
        </div>}
      </section>}

      <section className={styles.footerNote}>
        <span>DNSTT: OutlineFoundation/dnstt</span>
        <code>{inventory?.source.commit||"—"}</code>
        <span>{pick("خروجی: nm-dns://","Output: nm-dns://")}</span>
      </section>
    </div>
  </Shell>;
}
