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

type RelayOption={
  tunnel_id:number;
  exit_node_id:number;
  exit_node_name:string;
  exit_public_ip:string;
  exit_tunnel_ip:string;
  tunnel_status:string;
  is_active:boolean;
  active_transport:string;
  upstream_candidates:Candidate[];
};

type ClientInfo={
  engine:string;
  mode:string;
  domain:string;
  public_key:string;
  local_listen:string;
  command_example:string;
  nm_dns:null;
  nm_dns_reason:string;
};

type IranNode={
  node_id:number;
  node_name:string;
  public_ip:string;
  status:string;
  exit_node_id?:number|null;
  tunnel_id?:number|null;
  tunnel_domain?:string|null;
  nameserver_host?:string|null;
  upstream_port?:number|null;
  public_key?:string|null;
  last_error?:string|null;
  checked_at?:string|null;
  last_applied_at?:string|null;
  dnstt_commit:string;
  relay_options:RelayOption[];
  client?:ClientInfo|null;
};

type Inventory={
  ok:boolean;
  engine:string;
  mode:string;
  source:{repository:string;commit:string;go_version?:string};
  nodes:IranNode[];
};

type InstallResult=IranNode&{
  ok:boolean;
  runtime?:{
    exit_tunnel_ip?:string;
    active_transport?:string;
  };
  dns_instructions?:{
    tunnel_domain:string;
    nameserver_host?:string|null;
    iran_ip:string;
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

export function DnsEmergencyIranPanel(){
  const {pick}=useI18n();
  const [inventory,setInventory]=useState<Inventory|null>(null);
  const [selectedNodeId,setSelectedNodeId]=useState(0);
  const [selectedTunnelId,setSelectedTunnelId]=useState(0);
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
      const data=await apiRequest<Inventory>("/v1/settings/vpn/dns-emergency-iran");
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

  const selectedRelay=useMemo(
    ()=>selected?.relay_options.find(item=>item.tunnel_id===selectedTunnelId)||null,
    [selected,selectedTunnelId],
  );

  useEffect(()=>{
    if(!selected)return;
    setDomain(selected.tunnel_domain||"");
    setNameserver(selected.nameserver_host||"");
    const configured=selected.relay_options.find(item=>item.tunnel_id===Number(selected.tunnel_id||0));
    const online=selected.relay_options.find(item=>item.is_active&&item.tunnel_status.toLowerCase()==="online");
    const relay=configured||online||selected.relay_options[0]||null;
    setSelectedTunnelId(relay?.tunnel_id||0);
    setLastInstall(null);
    setError("");
    setNotice("");
  },[selectedNodeId,selected?.node_id]);

  useEffect(()=>{
    if(!selectedRelay){setUpstreamPort(0);return;}
    const configured=Number(selected?.tunnel_id||0)===selectedRelay.tunnel_id?Number(selected?.upstream_port||0):0;
    const preferred=selectedRelay.upstream_candidates.find(item=>item.recommended)||selectedRelay.upstream_candidates[0];
    setUpstreamPort(configured||preferred?.port||0);
  },[selectedTunnelId,selectedRelay?.tunnel_id,selected?.upstream_port]);

  const install=async()=>{
    if(!selected||!selectedRelay||busy)return;
    if(!selectedRelay.is_active||selectedRelay.tunnel_status.toLowerCase()!=="online"){
      setError(pick("Tunnel انتخاب‌شده باید Online باشد.","The selected tunnel must be online."));
      return;
    }
    if(!domain.trim()){setError(pick("دامنه Tunnel را وارد کنید.","Enter the tunnel domain."));return;}
    if(!upstreamPort){setError(pick("سرویس TCP مقصد را انتخاب کنید.","Select a TCP upstream service."));return;}
    setBusy("install");setError("");setNotice("");
    try{
      const result=await apiRequest<InstallResult>(`/v1/settings/vpn/dns-emergency-iran/${selected.node_id}/install`,{
        method:"POST",
        body:JSON.stringify({
          tunnel_id:selectedRelay.tunnel_id,
          exit_node_id:selectedRelay.exit_node_id,
          tunnel_domain:domain.trim(),
          nameserver_host:nameserver.trim()||null,
          upstream_port:Number(upstreamPort),
        }),
      });
      setLastInstall(result);
      setNotice(pick(
        "Iran Relay نصب شد؛ Listener روی نود ایران و مسیر TCP تا Exit از داخل Tunnel سالم است.",
        "Iran Relay was installed; the Iran-side listener and TCP path to the Exit through the tunnel are healthy.",
      ));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const health=async()=>{
    if(!selected||busy)return;
    setBusy("health");setError("");setNotice("");
    try{
      const result=await apiRequest<IranNode&{ok:boolean}>(`/v1/settings/vpn/dns-emergency-iran/${selected.node_id}/health`,{method:"POST"});
      setNotice(result.ok?pick("Health Check مسیر ایران → Tunnel → Exit موفق بود.","Iran → Tunnel → Exit health check passed."):pick("Health Check ناموفق بود؛ وضعیت Tunnel و TCP مقصد را بررسی کنید.","Health check failed; review the tunnel and TCP upstream."));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const remove=async()=>{
    if(!selected||busy)return;
    setBusy("remove");setError("");setNotice("");
    try{
      await apiRequest(`/v1/settings/vpn/dns-emergency-iran/${selected.node_id}`,{method:"DELETE"});
      setNotice(pick("Iran Relay متوقف و از Boot حذف شد؛ کلیدها برای Repair بعدی حفظ شدند.","Iran Relay was stopped and disabled at boot; keys were kept for a later repair."));
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

  return <Shell active="/admin/dns-emergency-iran">
    <PageHead title={pick("DNS اضطراری ایران","DNS Emergency Iran Relay")}/>
    <div className={styles.page}>
      <section className={styles.hero}>
        <div>
          <div className={styles.eyebrow}>DNSTT · IRAN RELAY · LAST RESORT</div>
          <h2>{pick("ورودی DNS داخل ایران، خروجی از Tunnel موجود به Exit","DNS ingress in Iran, egress through the existing tunnel to the Exit")}</h2>
          <p>{pick(
            "برای محدودیت شدید طراحی شده است: DNSTT روی نود ایران UDP/53 را دریافت می‌کند و TCP را با IP داخلی Tunnel به سرویس احراز هویت‌شده روی Exit می‌رساند.",
            "Built for severe restrictions: DNSTT receives UDP/53 on the Iran node and carries TCP through the tunnel's internal IP to an authenticated service on the Exit.",
          )}</p>
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
            <h3>{pick("۱. مسیر Iran → Exit","1. Iran → Exit path")}</h3>
            <p>{pick("نود ایران و Tunnel فعال آن به Exit را انتخاب کنید. Public IP خارج در مسیر DNSTT استفاده نمی‌شود.","Choose the Iran node and its active tunnel to the Exit. The Exit public IP is not used by the DNSTT upstream path.")}</p>
          </div>
          <button className={styles.secondary} type="button" disabled={Boolean(busy)} onClick={()=>void load()}>{busy==="load"?pick("در حال دریافت...","Loading..."):pick("بازخوانی","Refresh")}</button>
        </div>
        <div className={styles.grid}>
          <label>
            <span>{pick("نود ایران","Iran Node")}</span>
            <select value={selectedNodeId} onChange={event=>setSelectedNodeId(Number(event.target.value))}>
              {(inventory?.nodes||[]).map(node=><option key={node.node_id} value={node.node_id}>{node.node_name} · {node.public_ip}</option>)}
            </select>
          </label>
          <label>
            <span>{pick("Tunnel / Exit","Tunnel / Exit")}</span>
            <select value={selectedTunnelId} onChange={event=>setSelectedTunnelId(Number(event.target.value))}>
              {!selected?.relay_options.length&&<option value={0}>{pick("Tunnelای برای این نود پیدا نشد","No tunnel found for this Iran node")}</option>}
              {(selected?.relay_options||[]).map(item=><option key={item.tunnel_id} value={item.tunnel_id}>#{item.tunnel_id} · {item.exit_node_name} · {item.tunnel_status} · {item.active_transport||"—"}</option>)}
            </select>
          </label>
          <label>
            <span>{pick("TCP مقصد روی Exit","TCP upstream on Exit")}</span>
            <select value={upstreamPort} onChange={event=>setUpstreamPort(Number(event.target.value))}>
              {!selectedRelay?.upstream_candidates.length&&<option value={0}>{pick("سرویس TCP شناخته‌شده‌ای پیدا نشد","No known TCP service found")}</option>}
              {(selectedRelay?.upstream_candidates||[]).map(item=><option key={`${item.protocol}:${item.port}`} value={item.port}>{item.protocol} · {item.port} · {item.transport}{item.recommended?" ✓":""}</option>)}
            </select>
          </label>
          <label>
            <span>{pick("IP داخلی Exit در Tunnel","Exit tunnel IP")}</span>
            <input value={selectedRelay?.exit_tunnel_ip||"—"} readOnly dir="ltr"/>
          </label>
        </div>
        <div className={styles.hint}>
          <b>{pick("Flow واقعی","Actual flow")}</b>
          <code>Client DNS → {selected?.public_ip||"IRAN_IP"}:53 → DNSTT → {selectedRelay?.exit_tunnel_ip||"EXIT_TUNNEL_IP"}:{upstreamPort||"PORT"} → Exit</code>
        </div>
      </section>

      <section className={styles.card}>
        <h3>{pick("۲. DNS Delegation داخل ایران","2. Iran-side DNS delegation")}</h3>
        <p>{pick("Nameserver این حالت باید به Public IP نود ایران اشاره کند. برای محدودیت شدید، Resolver سیستم/اپراتور را روی کلاینت تست کنید.","The nameserver for this mode must point to the Iran node public IP. For severe restrictions, test the system/ISP resolver on the client.")}</p>
        <div className={styles.grid}>
          <label>
            <span>Tunnel Domain</span>
            <input value={domain} onChange={event=>setDomain(event.target.value)} placeholder="ir-dns.example.com" dir="ltr"/>
          </label>
          <label>
            <span>{pick("Nameserver Host (اختیاری)","Nameserver Host (optional)")}</span>
            <input value={nameserver} onChange={event=>setNameserver(event.target.value)} placeholder="ns-ir.example.com" dir="ltr"/>
          </label>
        </div>
        <div className={styles.hint}>
          <b>{pick("رکورد پیشنهادی","Suggested records")}</b>
          <code>A/AAAA {nameserver||"ns-ir.example.com"} → {selected?.public_ip||"IRAN_IP"}</code>
          <code>NS {domain||"ir-dns.example.com"} → {nameserver||"ns-ir.example.com"}</code>
        </div>
      </section>

      <section className={styles.actions}>
        <button className={styles.primary} type="button" onClick={()=>void install()} disabled={Boolean(busy)||!selected||!selectedRelay}>{busy==="install"?pick("در حال نصب و تست...","Installing and testing..."):pick("نصب Iran Relay + Health Check","Install Iran Relay + Health Check")}</button>
        <button className={styles.secondary} type="button" onClick={()=>void health()} disabled={Boolean(busy)||!selected||selected.status==="not_installed"}>{busy==="health"?pick("در حال تست...","Checking..."):"Health Check"}</button>
        <button className={styles.danger} type="button" onClick={()=>void remove()} disabled={Boolean(busy)||!selected||selected.status==="not_installed"}>{busy==="remove"?pick("در حال حذف...","Removing..."):pick("توقف Iran Relay","Stop Iran Relay")}</button>
      </section>

      {dnsRecords.length>0&&<section className={styles.card}>
        <h3>{pick("DNS آماده ثبت","DNS records ready to publish")}</h3>
        <div className={styles.records}>{dnsRecords.map(record=><div key={`${record.type}:${record.name}`}><b>{record.type}</b><code>{record.name}</code><span>→</span><code>{record.value}</code></div>)}</div>
      </section>}

      {client&&<section className={styles.card}>
        <h3>{pick("۳. اطلاعات کلاینت","3. Client parameters")}</h3>
        <p>{pick("در محدودیت شدید، به‌جای وابستگی به Resolver خارجی، IP Resolver قابل‌دسترسی اپراتور/سیستم را جایگزین کنید.","During severe restrictions, replace the placeholder with a reachable system/ISP resolver instead of depending on a foreign resolver.")}</p>
        <div className={styles.kv}>
          <span>Domain</span><code>{client.domain}</code><button type="button" onClick={()=>void copy(client.domain)}>{pick("کپی","Copy")}</button>
          <span>Public key</span><code>{client.public_key}</code><button type="button" onClick={()=>void copy(client.public_key)}>{pick("کپی","Copy")}</button>
          <span>Client</span><code>{client.command_example}</code><button type="button" onClick={()=>void copy(client.command_example)}>{pick("کپی","Copy")}</button>
        </div>
        <div className={styles.warning}>
          <b>{pick("محدودیت واقعی","Hard limit")}</b>
          <span>{pick("اگر Tunnel ایران → Exit هم کاملاً قطع باشد، DNS Relay نمی‌تواند مسیر خارجی ایجاد کند. این حالت برای زمانی است که DNS داخل ایران قابل دسترس است و حداقل یک Tunnel خروجی هنوز زنده مانده است.","If the Iran → Exit tunnel is completely unavailable, DNS Relay cannot create an external path. This mode requires reachable Iran-side DNS plus at least one surviving outbound tunnel.")}</span>
        </div>
      </section>}

      <section className={styles.footerNote}>
        <span>Source: OutlineFoundation/dnstt</span>
        <code>{inventory?.source.commit||"—"}</code>
        <span>{pick("ورودی روی Iran Node؛ خروجی از Tunnel داخلی","Ingress on Iran Node; egress through tunnel IP")}</span>
      </section>
    </div>
  </Shell>;
}
