"use client";

import {useEffect,useMemo,useState} from "react";

import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge,PageHead,Shell} from "./ui";
import styles from "./masterdnsvpn-panel.module.css";

type MasterNode={
  node_id:number;
  node_name:string;
  public_ip:string;
  status:string;
  tunnel_domain?:string|null;
  nameserver_host?:string|null;
  protocol_type:string;
  forward_ip?:string|null;
  forward_port?:number|null;
  data_encryption_method:number;
  source_commit:string;
  last_error?:string|null;
  checked_at?:string|null;
  last_applied_at?:string|null;
  client_config_available:boolean;
};

type Inventory={
  ok:boolean;
  engine:string;
  mode:string;
  source:{repository:string;commit:string;go_version:string};
  security:{udp53_conflict_policy:string;secret_in_inventory:boolean;supported_encryption_methods:number[]};
  nodes:MasterNode[];
};

type InstallResult=MasterNode&{
  ok:boolean;
  dns_instructions?:{
    tunnel_domain:string;
    nameserver_host?:string|null;
    exit_ip:string;
    records:Array<{type:string;name:string;value:string}>;
  };
};

type ClientConfig={
  ok:boolean;
  secret:boolean;
  domain:string;
  protocol_type:string;
  encryption_method:number;
  encryption_key:string;
  client_config_toml:string;
  client_resolvers_txt:string;
  command_example:string;
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
        const message=String(value.message||`API error ${response.status}`);
        const error=value.error?` — ${String(value.error)}`:"";
        throw new Error(`${message}${error}`);
      }
    }
    throw new Error(`API error ${response.status}`);
  }
  return payload as T;
}

function tone(status:string):"ok"|"warn"|"bad"|"violet"{
  const value=String(status||"").toLowerCase();
  if(value==="online")return "ok";
  if(value==="installing")return "warn";
  if(value==="error"||value==="failed")return "bad";
  return "violet";
}

function methodName(value:number){
  return ({2:"ChaCha20",3:"AES-128-GCM",4:"AES-192-GCM",5:"AES-256-GCM"} as Record<number,string>)[value]||String(value);
}

export function MasterDnsVpnPanel(){
  const {pick}=useI18n();
  const [inventory,setInventory]=useState<Inventory|null>(null);
  const [selectedNodeId,setSelectedNodeId]=useState(0);
  const [domain,setDomain]=useState("");
  const [nameserver,setNameserver]=useState("");
  const [protocolType,setProtocolType]=useState("SOCKS5");
  const [forwardIp,setForwardIp]=useState("");
  const [forwardPort,setForwardPort]=useState(0);
  const [encryptionMethod,setEncryptionMethod]=useState(2);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [lastInstall,setLastInstall]=useState<InstallResult|null>(null);
  const [client,setClient]=useState<ClientConfig|null>(null);

  const load=async(silent=false)=>{
    if(!silent)setBusy("load");
    setError("");
    try{
      const data=await apiRequest<Inventory>("/v1/settings/vpn/dns-emergency-masterdnsvpn");
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
    setProtocolType(selected.protocol_type||"SOCKS5");
    setForwardIp(selected.forward_ip||"");
    setForwardPort(Number(selected.forward_port||0));
    setEncryptionMethod(Number(selected.data_encryption_method||2));
    setLastInstall(null);
    setClient(null);
    setError("");
    setNotice("");
  },[selectedNodeId,selected?.node_id]);

  const install=async()=>{
    if(!selected||busy)return;
    if(!domain.trim()){setError(pick("دامنه Tunnel را وارد کنید.","Enter the tunnel domain."));return;}
    if(protocolType==="TCP"&&(!forwardIp.trim()||!forwardPort)){
      setError(pick("در حالت TCP، Host و Port مقصد الزامی است.","TCP mode requires a forward host and port."));return;
    }
    setBusy("install");setError("");setNotice("");setClient(null);
    try{
      const result=await apiRequest<InstallResult>(`/v1/settings/vpn/dns-emergency-masterdnsvpn/${selected.node_id}/install`,{
        method:"POST",
        body:JSON.stringify({
          tunnel_domain:domain.trim(),
          nameserver_host:nameserver.trim()||null,
          protocol_type:protocolType,
          forward_ip:protocolType==="TCP"?forwardIp.trim():null,
          forward_port:protocolType==="TCP"?Number(forwardPort):null,
          data_encryption_method:Number(encryptionMethod),
        }),
      });
      setLastInstall(result);
      setNotice(pick("MasterDnsVPN نصب شد و Listener روی UDP/53 سالم است.","MasterDnsVPN was installed and its UDP/53 listener is healthy."));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const health=async()=>{
    if(!selected||busy)return;
    setBusy("health");setError("");setNotice("");
    try{
      const result=await apiRequest<MasterNode&{ok:boolean}>(`/v1/settings/vpn/dns-emergency-masterdnsvpn/${selected.node_id}/health`,{method:"POST"});
      setNotice(result.ok?pick("Health Check موفق بود.","Health check passed."):pick("Health Check ناموفق بود؛ جزئیات وضعیت را بررسی کنید.","Health check failed; review runtime details."));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const revealClient=async()=>{
    if(!selected||busy)return;
    setBusy("client");setError("");setNotice("");
    try{
      const result=await apiRequest<ClientConfig>(`/v1/settings/vpn/dns-emergency-masterdnsvpn/${selected.node_id}/client-config`);
      setClient(result);
      setNotice(pick("Client Config دریافت شد. این بخش شامل کلید محرمانه است.","Client config loaded. This section contains a secret key."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const remove=async()=>{
    if(!selected||busy)return;
    setBusy("remove");setError("");setNotice("");setClient(null);
    try{
      await apiRequest(`/v1/settings/vpn/dns-emergency-masterdnsvpn/${selected.node_id}`,{method:"DELETE"});
      setNotice(pick("سرویس متوقف و از Boot حذف شد؛ کلید برای Repair بعدی حفظ شد.","The service was stopped and disabled at boot; the key was preserved for future repair."));
      await load(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const copy=async(value:string)=>{
    try{await navigator.clipboard.writeText(value);setNotice(pick("کپی شد.","Copied."));}
    catch{setError(pick("کپی خودکار در این مرورگر در دسترس نیست.","Clipboard access is unavailable in this browser."));}
  };

  const records=lastInstall?.dns_instructions?.records||[];

  return <Shell active="/admin/dns-emergency-masterdnsvpn">
    <PageHead title={pick("DNS اضطراری · MasterDnsVPN","DNS Emergency · MasterDnsVPN")}/>
    <div className={styles.page}>
      <nav className={styles.engineNav} aria-label={pick("موتورهای DNS اضطراری","DNS emergency engines")}>
        <a href="/admin/dns-emergency">DNSTT · Direct Exit</a>
        <a href="/admin/dns-emergency-iran">DNSTT · Iran Relay</a>
        <a className={styles.activeEngine} href="/admin/dns-emergency-masterdnsvpn">MasterDnsVPN · Direct Exit</a>
      </nav>

      <section className={styles.hero}>
        <div>
          <div className={styles.eyebrow}>MasterDnsVPN · Direct Exit · UDP/53</div>
          <h2>{pick("موتور مستقل DNS برای اتصال مستقیم به Exit","Independent DNS engine for direct Exit connectivity")}</h2>
          <p>{pick("این مسیر به Tunnel ایران وابسته نیست. MasterDnsVPN مستقیم روی Exit نصب می‌شود و در حالت پیشنهادی SOCKS5 مقصد هر اتصال را از کلاینت دریافت می‌کند.","This path does not depend on the Iran tunnel. MasterDnsVPN is installed directly on the Exit and, in the recommended SOCKS5 mode, accepts each stream destination from the client.")}</p>
        </div>
        <div className={styles.statusBox}>
          <span>{pick("وضعیت","Status")}</span>
          <Badge tone={tone(selected?.status||"not_installed")}>{selected?.status||"not_installed"}</Badge>
        </div>
      </section>

      {error&&<div className={styles.error}>{error}</div>}
      {notice&&<div className={styles.notice}>{notice}</div>}

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <div>
            <h3>{pick("۱. Exit و حالت اتصال","1. Exit and connection mode")}</h3>
            <p>{pick("SOCKS5 برای استفاده عمومی پیشنهاد می‌شود. TCP فقط همه Streamها را به یک مقصد ثابت می‌فرستد.","SOCKS5 is recommended for general use. TCP forwards every stream to one fixed target.")}</p>
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
            <span>{pick("حالت","Mode")}</span>
            <select value={protocolType} onChange={event=>setProtocolType(event.target.value)}>
              <option value="SOCKS5">SOCKS5 · {pick("پیشنهادی","Recommended")}</option>
              <option value="TCP">TCP · Fixed Target</option>
            </select>
          </label>
          <label>
            <span>{pick("رمزنگاری Payload","Payload encryption")}</span>
            <select value={encryptionMethod} onChange={event=>setEncryptionMethod(Number(event.target.value))}>
              {[2,3,4,5].map(value=><option key={value} value={value}>{methodName(value)}{value===2?` · ${pick("پیشنهادی","Recommended")}`:""}</option>)}
            </select>
          </label>
        </div>
        {protocolType==="TCP"&&<div className={styles.grid}>
          <label>
            <span>Forward Host</span>
            <input dir="ltr" value={forwardIp} onChange={event=>setForwardIp(event.target.value)} placeholder="127.0.0.1"/>
          </label>
          <label>
            <span>Forward Port</span>
            <input dir="ltr" type="number" min={1} max={65535} value={forwardPort||""} onChange={event=>setForwardPort(Number(event.target.value))} placeholder="443"/>
          </label>
        </div>}
      </section>

      <section className={styles.card}>
        <h3>{pick("۲. DNS Delegation","2. DNS delegation")}</h3>
        <p>{pick("Subdomain را به Nameserverای Delegate کنید که به Public IP همین Exit اشاره می‌کند.","Delegate the subdomain to a nameserver that points to this Exit public IP.")}</p>
        <div className={styles.grid}>
          <label>
            <span>Tunnel Domain</span>
            <input dir="ltr" value={domain} onChange={event=>setDomain(event.target.value)} placeholder="m.example.com"/>
          </label>
          <label>
            <span>{pick("Nameserver Host (اختیاری)","Nameserver Host (optional)")}</span>
            <input dir="ltr" value={nameserver} onChange={event=>setNameserver(event.target.value)} placeholder="ns.example.com"/>
          </label>
        </div>
        <div className={styles.hint}>
          <b>{pick("رکورد پیشنهادی","Suggested records")}</b>
          <code>A/AAAA {nameserver||"ns.example.com"} → {selected?.public_ip||"EXIT_IP"}</code>
          <code>NS {domain||"m.example.com"} → {nameserver||"ns.example.com"}</code>
        </div>
      </section>

      <section className={styles.securityCard}>
        <div><b>{pick("سیاست ایمن Port 53","Safe Port 53 policy")}</b><span>{pick("اگر UDP/53 عمومی توسط سرویس دیگری اشغال باشد، نصب Fail-Closed می‌شود و هیچ Process یا سرویس دیگری متوقف نمی‌شود.","If public UDP/53 is occupied by another service, installation fails closed and no other process or service is stopped.")}</span></div>
        <div><b>{pick("کلید محرمانه","Secret key")}</b><span>{pick("کلید در دیتابیس و Inventory ذخیره/نمایش داده نمی‌شود؛ فقط با دکمه Client Config و دسترسی Admin از Exit خوانده می‌شود.","The key is not stored or exposed in inventory; it is read from the Exit only through the admin-only Client Config action.")}</span></div>
      </section>

      <section className={styles.actions}>
        <button className={styles.primary} type="button" onClick={()=>void install()} disabled={Boolean(busy)||!selected}>{busy==="install"?pick("در حال نصب و تست...","Installing and testing..."):pick("نصب / Repair","Install / Repair")}</button>
        <button className={styles.secondary} type="button" onClick={()=>void health()} disabled={Boolean(busy)||!selected||selected.status==="not_installed"}>{busy==="health"?pick("در حال تست...","Checking..."):"Health Check"}</button>
        <button className={styles.secondary} type="button" onClick={()=>void revealClient()} disabled={Boolean(busy)||!selected||!selected.client_config_available}>{busy==="client"?pick("در حال دریافت...","Loading..."):pick("نمایش Client Config","Show Client Config")}</button>
        <button className={styles.danger} type="button" onClick={()=>void remove()} disabled={Boolean(busy)||!selected||selected.status==="not_installed"}>{busy==="remove"?pick("در حال حذف...","Removing..."):pick("توقف و حذف سرویس","Stop and remove service")}</button>
      </section>

      {records.length>0&&<section className={styles.card}>
        <h3>{pick("DNS آماده ثبت","DNS records ready to publish")}</h3>
        <div className={styles.records}>{records.map(record=><div key={`${record.type}:${record.name}`}><b>{record.type}</b><code>{record.name}</code><span>→</span><code>{record.value}</code></div>)}</div>
      </section>}

      {selected?.last_error&&<section className={styles.runtimeError}><b>{pick("آخرین خطای Runtime","Last runtime error")}</b><code>{selected.last_error}</code></section>}

      {client&&<section className={styles.secretCard}>
        <div className={styles.secretHead}><div><h3>{pick("۳. Client Config محرمانه","3. Secret client config")}</h3><p>{pick("این اطلاعات شامل Shared Key است. فقط روی دستگاه‌های مجاز ذخیره شود.","This data includes the shared key. Store it only on authorized devices.")}</p></div><Badge tone="warn">SECRET</Badge></div>
        <div className={styles.secretGrid}>
          <div><span>Domain</span><code>{client.domain}</code><button type="button" onClick={()=>void copy(client.domain)}>{pick("کپی","Copy")}</button></div>
          <div><span>Encryption</span><code>{methodName(client.encryption_method)}</code></div>
          <div><span>Shared Key</span><code className={styles.key}>{client.encryption_key}</code><button type="button" onClick={()=>void copy(client.encryption_key)}>{pick("کپی","Copy")}</button></div>
        </div>
        <label className={styles.codeBlock}><span>client_config.toml</span><textarea readOnly value={client.client_config_toml}/><button type="button" onClick={()=>void copy(client.client_config_toml)}>{pick("کپی فایل","Copy file")}</button></label>
        <label className={styles.codeBlock}><span>client_resolvers.txt</span><textarea readOnly value={client.client_resolvers_txt}/><button type="button" onClick={()=>void copy(client.client_resolvers_txt)}>{pick("کپی فایل","Copy file")}</button></label>
        <div className={styles.command}><code>{client.command_example}</code><button type="button" onClick={()=>void copy(client.command_example)}>{pick("کپی دستور","Copy command")}</button></div>
      </section>}

      <section className={styles.footerNote}>
        <span>Source: masterking32/MasterDnsVPN</span>
        <code>{inventory?.source.commit||"—"}</code>
        <span>Go {inventory?.source.go_version||"—"}</span>
      </section>
    </div>
  </Shell>;
}
