"use client";

import {useEffect, useMemo, useState} from "react";

import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge, PageHead, Shell} from "./ui";
import styles from "./outbound-policy-center.module.css";


type TransportInfo={
  type?:string;
  path?:string;
  service_name?:string;
  headers?:Record<string,string>;
};

type TlsInfo={
  enabled?:boolean;
  server_name?:string;
};

type OutboundRow={
  type:string;
  tag:string;
  server?:string;
  server_port?:number;
  username?:string;
  password?:string;
  has_password?:boolean;
  managed?:boolean;
  imported?:boolean;
  transport?:TransportInfo;
  tls?:TlsInfo;
};

type OutboundNode={
  id:number;
  name:string;
  public_ip:string;
  public_domain?:string|null;
  service_active:boolean;
  error?:unknown;
  outbounds:OutboundRow[];
  default_tag?:string|null;
  default_mode:string;
};

type Inventory={
  ok:boolean;
  supported_types:string[];
  supported_import_types?:string[];
  nodes:OutboundNode[];
};

type TestResult={
  ok:boolean;
  node_id:number;
  tag:string;
  tcp_ok:boolean;
  tcp_ms?:number|null;
  e2e_ok:boolean;
  exit_ip?:string|null;
  http_code?:number|null;
  latency_ms?:number|null;
  error?:string|null;
};

type PolicyMode="inherit"|"direct"|"outbound"|"block";

type PolicyRow={
  key:string;
  title:string;
  plane:string;
  inbound_tag?:string|null;
  policy_supported:boolean;
  installed?:boolean|null;
  reason?:string|null;
  mode:PolicyMode;
  outbound_tag?:string|null;
  effective_outbound:string;
};

type PolicyInventory={
  ok:boolean;
  schema:number;
  node_id:number;
  node_name:string;
  service_active:boolean;
  default_tag?:string|null;
  outbounds:OutboundRow[];
  protocols:PolicyRow[];
  capabilities:{
    native_protocol_policy:boolean;
    classic_egress_adapter:boolean;
    xray_egress_adapter:boolean;
    modes:string[];
  };
};

type PolicyDraft={mode:PolicyMode;outboundTag:string};
type EditDraft={server:string;serverPort:string;host:string;path:string;sni:string};
type Tab="routing"|"pool"|"add";

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
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
        const message=(detail as {message?:unknown;error?:unknown;reason?:unknown}).message;
        const error=(detail as {message?:unknown;error?:unknown;reason?:unknown}).error;
        const reason=(detail as {message?:unknown;error?:unknown;reason?:unknown}).reason;
        throw new Error([message,error,reason].filter(Boolean).map(String).join(" · ")||`API ${response.status}`);
      }
    }
    throw new Error(`API ${response.status}`);
  }
  return payload as T;
}

function errorText(value:unknown):string{
  if(!value)return "";
  if(typeof value==="string")return value;
  try{return JSON.stringify(value);}catch{return String(value);}
}

function protocolTitle(value:string):string{
  const key=String(value||"").toLowerCase();
  if(key==="vless")return "VLESS";
  if(key==="vmess")return "VMess";
  if(key==="trojan")return "Trojan";
  if(key==="shadowsocks")return "Shadowsocks";
  if(key==="direct")return "DIRECT";
  if(key==="socks")return "SOCKS5";
  if(key==="http")return "HTTP";
  return key.toUpperCase();
}

function headerValue(headers:Record<string,string>|undefined,name:string):string{
  if(!headers)return "";
  const wanted=name.toLowerCase();
  const key=Object.keys(headers).find(item=>item.toLowerCase()===wanted);
  return key?String(headers[key]||""):"";
}

function endpoint(row:OutboundRow):string{
  if(row.type==="direct")return "Internet / WAN";
  const host=String(row.server||"").trim();
  const port=row.server_port?String(row.server_port):"";
  return [host,port].filter(Boolean).join(":")||"—";
}

function transportLabel(row:OutboundRow):string{
  const transport=String(row.transport?.type||"").toUpperCase();
  const tls=row.tls?.enabled?"TLS":"";
  return [transport,tls].filter(Boolean).join(" + ")||"Native";
}

function planeLabel(value:string,fa:boolean):string{
  if(value==="singbox")return "Sing-box";
  if(value==="kernel")return fa?"Kernel VPN":"Kernel VPN";
  if(value==="xray")return "Xray Core";
  return value;
}

export function OutboundPolicyCenter(){
  const {pick,lang}=useI18n();
  const fa=lang==="fa";
  const [inventory,setInventory]=useState<Inventory|null>(null);
  const [policy,setPolicy]=useState<PolicyInventory|null>(null);
  const [nodeId,setNodeId]=useState(0);
  const [tab,setTab]=useState<Tab>("routing");
  const [loading,setLoading]=useState(true);
  const [policyLoading,setPolicyLoading]=useState(false);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [tests,setTests]=useState<Record<string,TestResult>>({});
  const [policyDrafts,setPolicyDrafts]=useState<Record<string,PolicyDraft>>({});
  const [config,setConfig]=useState("");
  const [setDefaultOnImport,setSetDefaultOnImport]=useState(false);
  const [editingTag,setEditingTag]=useState("");
  const [editDraft,setEditDraft]=useState<EditDraft|null>(null);

  const node=useMemo(
    ()=>inventory?.nodes.find(item=>item.id===nodeId)||null,
    [inventory,nodeId],
  );

  const imported=useMemo(
    ()=>(node?.outbounds||[]).filter(item=>item.imported&&item.managed),
    [node],
  );

  const supported=inventory?.supported_import_types||["vless","vmess","trojan","shadowsocks"];
  const activePolicies=policy?.protocols.filter(item=>item.policy_supported&&item.mode!=="inherit").length||0;
  const healthyTests=Object.values(tests).filter(item=>item.ok).length;

  const loadInventory=async(silent=false)=>{
    if(!silent)setLoading(true);
    setError("");
    try{
      const data=await request<Inventory>("/v1/settings/vpn/outbounds");
      setInventory(data);
      setNodeId(current=>data.nodes.some(item=>item.id===current)?current:(data.nodes[0]?.id||0));
    }catch(exc){
      setError(exc instanceof Error?exc.message:String(exc));
    }finally{
      if(!silent)setLoading(false);
    }
  };

  const loadPolicy=async(id:number,silent=false)=>{
    if(!id)return;
    if(!silent)setPolicyLoading(true);
    try{
      const data=await request<PolicyInventory>(`/v1/settings/vpn/outbound-policy/${id}`);
      setPolicy(data);
      setPolicyDrafts(Object.fromEntries(data.protocols.map(item=>[
        item.key,
        {mode:item.mode,outboundTag:item.outbound_tag||""},
      ])));
    }catch(exc){
      setPolicy(null);
      setError(exc instanceof Error?exc.message:String(exc));
    }finally{
      if(!silent)setPolicyLoading(false);
    }
  };

  const refresh=async()=>{
    setNotice("");
    await loadInventory(true);
    if(nodeId)await loadPolicy(nodeId,true);
  };

  useEffect(()=>{void loadInventory();},[]);
  useEffect(()=>{
    if(nodeId){
      setTests({});
      setEditingTag("");
      setEditDraft(null);
      void loadPolicy(nodeId);
    }
  },[nodeId]);

  const applyPolicy=async(row:PolicyRow)=>{
    if(!node)return;
    const draft=policyDrafts[row.key]||{mode:row.mode,outboundTag:row.outbound_tag||""};
    if(draft.mode==="outbound"&&!draft.outboundTag){
      setError(pick("برای این پروتکل یک Outbound انتخاب کنید.","Choose an outbound for this protocol."));
      return;
    }
    setBusy(`policy:${row.key}`);setError("");setNotice("");
    try{
      const data=await request<PolicyInventory>(`/v1/settings/vpn/outbound-policy/${node.id}/${encodeURIComponent(row.key)}`,{
        method:"PATCH",
        body:JSON.stringify({
          mode:draft.mode,
          outbound_tag:draft.mode==="outbound"?draft.outboundTag:null,
        }),
      });
      setPolicy(data);
      setPolicyDrafts(Object.fromEntries(data.protocols.map(item=>[
        item.key,
        {mode:item.mode,outboundTag:item.outbound_tag||""},
      ])));
      setNotice(pick(`مسیر ${row.title} با اعتبارسنجی و Rollback-safe اعمال شد.`,`Routing policy for ${row.title} was validated and applied rollback-safely.`));
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const importConfig=async()=>{
    if(!node)return;
    const value=config.trim();
    if(!value){setError(pick("کانفیگ را Paste کنید.","Paste a config first."));return;}
    setBusy("import");setError("");setNotice("");
    try{
      const result=await request<{tag:string;type:string}>(`/v1/settings/vpn/outbounds/${node.id}/import`,{
        method:"POST",
        body:JSON.stringify({config:value,set_default:setDefaultOnImport}),
      });
      setConfig("");
      setNotice(pick(`Outbound ${protocolTitle(result.type)} با Tag «${result.tag}» ذخیره شد.`,`Saved ${protocolTitle(result.type)} outbound as “${result.tag}”.`));
      await loadInventory(true);
      await loadPolicy(node.id,true);
      setTab("pool");
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const makeDefault=async(tag:string)=>{
    if(!node)return;
    setBusy(`default:${tag}`);setError("");setNotice("");
    try{
      await request(`/v1/settings/vpn/outbounds/${node.id}/default`,{method:"POST",body:JSON.stringify({tag})});
      setNotice(pick(`مسیر پیش‌فرض نود روی ${tag} قرار گرفت.`,`Node default route is now ${tag}.`));
      await loadInventory(true);await loadPolicy(node.id,true);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const clearDefault=async()=>{
    if(!node)return;
    setBusy("clear-default");setError("");setNotice("");
    try{
      await request(`/v1/settings/vpn/outbounds/${node.id}/default/clear`,{method:"POST"});
      setNotice(pick("مسیر پیش‌فرض نود به Direct/ضمنی برگشت.","Node default route returned to Direct/implicit."));
      await loadInventory(true);await loadPolicy(node.id,true);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const testOutbound=async(tag:string)=>{
    if(!node)return;
    setBusy(`test:${tag}`);setError("");setNotice("");
    try{
      const result=await request<TestResult>(`/v1/settings/vpn/outbounds/${node.id}/${encodeURIComponent(tag)}/test`,{method:"POST"});
      setTests(current=>({...current,[tag]:result}));
      setNotice(result.ok
        ?pick(`تست واقعی ${tag} موفق بود؛ Exit IP: ${result.exit_ip||"—"}`,`${tag} passed; Exit IP: ${result.exit_ip||"—"}`)
        :pick(`تست ${tag} ناموفق بود.`,`Test failed for ${tag}.`));
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const removeOutbound=async(tag:string)=>{
    if(!node||tag==="direct")return;
    if(!window.confirm(pick(`Outbound «${tag}» حذف شود؟`,`Delete outbound “${tag}”?`)))return;
    setBusy(`delete:${tag}`);setError("");setNotice("");
    try{
      await request(`/v1/settings/vpn/outbounds/${node.id}/${encodeURIComponent(tag)}`,{method:"DELETE"});
      setTests(current=>{const next={...current};delete next[tag];return next;});
      setNotice(pick("Outbound حذف شد.","Outbound deleted."));
      await loadInventory(true);await loadPolicy(node.id,true);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const openEdit=(row:OutboundRow)=>{
    setEditingTag(row.tag);
    setEditDraft({
      server:row.server||"",
      serverPort:row.server_port?String(row.server_port):"",
      host:headerValue(row.transport?.headers,"Host"),
      path:row.transport?.path||"",
      sni:row.tls?.server_name||"",
    });
  };

  const saveEdit=async()=>{
    if(!node||!editingTag||!editDraft)return;
    const port=Number(editDraft.serverPort);
    if(!editDraft.server.trim()||!Number.isInteger(port)||port<1||port>65535){
      setError(pick("آدرس/IP و پورت معتبر وارد کنید.","Enter a valid address/IP and port."));
      return;
    }
    setBusy(`edit:${editingTag}`);setError("");setNotice("");
    try{
      await request(`/v1/settings/vpn/outbounds/${node.id}/${encodeURIComponent(editingTag)}`,{
        method:"PATCH",
        body:JSON.stringify({
          server:editDraft.server.trim(),
          server_port:port,
          host:editDraft.host.trim(),
          path:editDraft.path.trim(),
          ...(editDraft.sni.trim()?{sni:editDraft.sni.trim()}:{}),
        }),
      });
      setTests(current=>{const next={...current};delete next[editingTag];return next;});
      setEditingTag("");setEditDraft(null);
      setNotice(pick("Outbound ویرایش و با Sing-box check اعمال شد.","Outbound was edited and applied after Sing-box validation."));
      await loadInventory(true);await loadPolicy(node.id,true);
    }catch(exc){setError(exc instanceof Error?exc.message:String(exc));}
    finally{setBusy("");}
  };

  const updateDraft=(key:string,patch:Partial<PolicyDraft>)=>{
    setPolicyDrafts(current=>({
      ...current,
      [key]:{...(current[key]||{mode:"inherit" as PolicyMode,outboundTag:""}),...patch},
    }));
  };

  const hasPolicyChanges=(row:PolicyRow)=>{
    const draft=policyDrafts[row.key];
    if(!draft)return false;
    return draft.mode!==row.mode||(draft.mode==="outbound"&&draft.outboundTag!==(row.outbound_tag||""));
  };

  return <Shell active="/admin/outbounds">
    <div className={styles.page} dir={fa?"rtl":"ltr"}>
      <PageHead title={pick("مرکز مسیریابی خروجی","Outbound Policy Center")}/>

      <section className={styles.hero}>
        <div className={styles.heroGlow}/>
        <div className={styles.heroMain}>
          <div className={styles.eyebrow}>TWINPANEL · EGRESS CONTROL PLANE</div>
          <h1>{pick("مرکز مسیریابی خروجی","Outbound Policy Center")}</h1>
          <p>{pick(
            "مسیر خروج هر پروتکل را مستقل کنترل کنید، سلامت Outboundها را با تست واقعی بسنجید و بدون دست‌کاری مسیرهای سالم، Policy اختصاصی بسازید.",
            "Control each protocol's egress independently, verify outbounds with real tests, and build explicit policies without disturbing healthy routes.",
          )}</p>
          <div className={styles.heroBadges}>
            <span>Config Check</span><span>Atomic Apply</span><span>Auto Rollback</span><span>Per-Protocol Rules</span>
          </div>
        </div>
        <div className={styles.heroControls}>
          <label>
            <span>{pick("نود فعال","Active node")}</span>
            <select value={nodeId} onChange={event=>setNodeId(Number(event.target.value))} disabled={loading||Boolean(busy)}>
              {(inventory?.nodes||[]).map(item=><option key={item.id} value={item.id}>{item.name} · {item.public_ip}</option>)}
            </select>
          </label>
          <button className={styles.refreshButton} onClick={()=>void refresh()} disabled={loading||policyLoading||Boolean(busy)}>
            {loading||policyLoading?pick("در حال دریافت...","Loading..."):pick("به‌روزرسانی وضعیت","Refresh status")}
          </button>
        </div>
      </section>

      {error?<div className={styles.alertError}><b>{pick("خطا","Error")}</b><span>{error}</span></div>:null}
      {notice?<div className={styles.alertSuccess}><b>{pick("انجام شد","Applied")}</b><span>{notice}</span></div>:null}
      {node?.error?<div className={styles.alertError}><b>{pick("خطای نود","Node error")}</b><span>{errorText(node.error)}</span></div>:null}

      <section className={styles.stats}>
        <article className={styles.statCard}>
          <div className={styles.statTop}><span>{pick("هسته خروجی","Egress core")}</span><i className={node?.service_active?styles.dotOk:styles.dotBad}/></div>
          <strong>{node?.service_active?pick("آنلاین","Online"):pick("آفلاین","Offline")}</strong>
          <small>{node?.name||"—"} · {node?.public_ip||"—"}</small>
        </article>
        <article className={styles.statCard}>
          <div className={styles.statTop}><span>{pick("مسیر پیش‌فرض","Default route")}</span><i className={styles.dotViolet}/></div>
          <strong className={styles.mono}>{node?.default_tag||"direct"}</strong>
          <small>{pick("Fallback پروتکل‌های بدون Policy","Fallback for protocols without a policy")}</small>
        </article>
        <article className={styles.statCard}>
          <div className={styles.statTop}><span>{pick("Outboundهای مدیریت‌شده","Managed outbounds")}</span><i className={styles.dotBlue}/></div>
          <strong>{imported.length}</strong>
          <small>{healthyTests} {pick("مسیر با تست موفق در این نشست","routes passed in this session")}</small>
        </article>
        <article className={styles.statCard}>
          <div className={styles.statTop}><span>{pick("Policy فعال","Active policies")}</span><i className={styles.dotAmber}/></div>
          <strong>{activePolicies}</strong>
          <small>{pick("Rule مستقل از route.final","Rules independent from route.final")}</small>
        </article>
      </section>

      <section className={styles.controlBar}>
        <div className={styles.tabs}>
          <button className={tab==="routing"?styles.tabActive:""} onClick={()=>setTab("routing")}>
            {pick("مسیریابی پروتکل‌ها","Protocol routing")}
          </button>
          <button className={tab==="pool"?styles.tabActive:""} onClick={()=>setTab("pool")}>
            {pick("استخر Outbound","Outbound pool")} <span>{imported.length}</span>
          </button>
          <button className={tab==="add"?styles.tabActive:""} onClick={()=>setTab("add")}>
            + {pick("افزودن Outbound","Add outbound")}
          </button>
        </div>
        <div className={styles.defaultRoute}>
          <span>{pick("Default:","Default:")}</span>
          <b className={styles.mono}>{node?.default_tag||"direct"}</b>
          {node?.default_tag&&node.default_tag!=="direct"?<button onClick={()=>void clearDefault()} disabled={Boolean(busy)}>{pick("بازگشت به Direct","Return to Direct")}</button>:null}
        </div>
      </section>

      {tab==="routing"?<section className={styles.panel}>
        <div className={styles.sectionHead}>
          <div>
            <span className={styles.sectionKicker}>ROUTING MATRIX</span>
            <h2>{pick("مسیر خروج هر پروتکل","Egress path per protocol")}</h2>
            <p>{pick(
              "اولویت اجرا: Policy پروتکل ← مسیر پیش‌فرض نود. فقط مسیرهایی که واقعاً در Data Plane قابل کنترل‌اند قابل اعمال هستند.",
              "Precedence: protocol policy → node default. Only routes with real data-plane control can be applied.",
            )}</p>
          </div>
          <div className={styles.legend}>
            <span><i className={styles.dotOk}/>{pick("قابل اعمال","Writable")}</span>
            <span><i className={styles.dotMuted}/>{pick("نیازمند Adapter","Adapter required")}</span>
          </div>
        </div>

        {policyLoading?<div className={styles.loadingBox}>{pick("در حال خواندن Policyهای واقعی نود...","Reading node policies...")}</div>:null}
        {!policyLoading&&policy?<div className={styles.matrix}>
          <div className={styles.matrixHeader}>
            <span>{pick("پروتکل","Protocol")}</span>
            <span>{pick("Data Plane","Data plane")}</span>
            <span>{pick("حالت مسیر","Route mode")}</span>
            <span>{pick("Outbound مقصد","Target outbound")}</span>
            <span>{pick("مسیر مؤثر","Effective path")}</span>
            <span>{pick("عملیات","Action")}</span>
          </div>
          {policy.protocols.map(row=>{
            const draft=policyDrafts[row.key]||{mode:row.mode,outboundTag:row.outbound_tag||""};
            const writable=row.policy_supported&&row.installed!==false;
            return <div className={`${styles.matrixRow} ${!row.policy_supported?styles.matrixRowLocked:""}`} key={row.key}>
              <div className={styles.protocolCell}>
                <div className={styles.protocolIcon}>{row.title.slice(0,2).toUpperCase()}</div>
                <div><b>{row.title}</b><small>{row.inbound_tag||row.key}</small></div>
              </div>
              <div className={styles.stackCell}>
                <span>{planeLabel(row.plane,fa)}</span>
                {row.policy_supported
                  ?<Badge tone={row.installed===false?"warn":"ok"}>{row.installed===false?pick("نصب نیست","Not installed"):pick("Route-ready","Route-ready")}</Badge>
                  :<Badge tone="warn">{pick("Adapter لازم","Adapter required")}</Badge>}
              </div>
              <div>
                {row.policy_supported?<select
                  className={styles.routeSelect}
                  value={draft.mode}
                  onChange={event=>updateDraft(row.key,{mode:event.target.value as PolicyMode})}
                  disabled={!writable||Boolean(busy)}
                >
                  <option value="inherit">{pick("پیش‌فرض نود","Inherit default")}</option>
                  <option value="direct">Direct</option>
                  <option value="outbound">{pick("Outbound مشخص","Specific outbound")}</option>
                  <option value="block">{pick("مسدود","Block")}</option>
                </select>:<span className={styles.lockText}>{pick(
                  row.reason==="separate_core_adapter_required"?"نیازمند اتصال Policy به Xray Core":"نیازمند Egress Adapter واقعی",
                  row.reason==="separate_core_adapter_required"?"Needs Xray policy adapter":"Needs a real egress adapter",
                )}</span>}
              </div>
              <div>
                {row.policy_supported&&draft.mode==="outbound"?<select
                  className={styles.routeSelect}
                  value={draft.outboundTag}
                  onChange={event=>updateDraft(row.key,{outboundTag:event.target.value})}
                  disabled={!writable||Boolean(busy)}
                >
                  <option value="">{pick("انتخاب Outbound...","Choose outbound...")}</option>
                  {imported.map(item=><option value={item.tag} key={item.tag}>{item.tag}</option>)}
                </select>:<span className={styles.mutedValue}>{draft.mode==="direct"?"direct":draft.mode==="block"?"reject":pick("از Default ارث می‌برد","Inherited")}</span>}
              </div>
              <div className={styles.effectiveCell}>
                <span className={styles.routePill}>{row.effective_outbound}</span>
                {row.mode!=="inherit"?<small>{pick("Policy اختصاصی","Explicit policy")}</small>:<small>{pick("Inherited","Inherited")}</small>}
              </div>
              <div className={styles.actionCell}>
                {row.policy_supported?<button
                  className={hasPolicyChanges(row)?styles.primaryButton:styles.ghostButton}
                  disabled={!writable||Boolean(busy)||!hasPolicyChanges(row)}
                  onClick={()=>void applyPolicy(row)}
                >{busy===`policy:${row.key}`?pick("اعمال...","Applying..."):pick("اعمال Policy","Apply")}</button>:<span className={styles.lockBadge}>LOCKED</span>}
              </div>
            </div>;
          })}
        </div>:null}

        <div className={styles.architectureNote}>
          <div><b>{pick("چرا بعضی پروتکل‌ها قفل‌اند؟","Why are some protocols locked?")}</b><p>{pick(
            "OpenVPN، WireGuard، Cisco و L2TP اکنون در Kernel Data Plane مستقیماً NAT می‌شوند. تا وقتی Egress Adapter محدود و rollback-safe برای subnet آن‌ها ساخته نشود، انتخاب Outbound در UI واقعاً روی بسته‌ها اثر نمی‌گذارد؛ TwinPanel عمداً چنین گزینه جعلی‌ای فعال نمی‌کند.",
            "OpenVPN, WireGuard, Cisco and L2TP currently NAT directly in the kernel data plane. Until a bounded, rollback-safe egress adapter is installed for their subnets, a UI selection would not change real packets, so TwinPanel intentionally keeps those controls locked.",
          )}</p></div>
          <div className={styles.safetyChips}><span>Fail-closed UI</span><span>Config validation</span><span>Rule preservation</span><span>Rollback</span></div>
        </div>
      </section>:null}

      {tab==="pool"?<section className={styles.panel}>
        <div className={styles.sectionHead}>
          <div><span className={styles.sectionKicker}>EGRESS POOL</span><h2>{pick("Outboundهای این نود","Node outbounds")}</h2><p>{pick("تست واقعی TCP، HTTPS، Exit IP و Latency بدون تغییر مسیر Production.","Real TCP, HTTPS, Exit-IP and latency tests without changing production routing.")}</p></div>
          <button className={styles.primaryButton} onClick={()=>setTab("add")}>+ {pick("Outbound جدید","New outbound")}</button>
        </div>

        {!node?.outbounds?.length?<div className={styles.loadingBox}>{pick("Outboundی روی این نود پیدا نشد.","No outbounds found on this node.")}</div>:null}
        <div className={styles.poolGrid}>
          {(node?.outbounds||[]).map(row=>{
            const test=tests[row.tag];
            const isDefault=node.default_tag===row.tag;
            const editable=Boolean(row.imported&&row.managed);
            return <article className={`${styles.outboundCard} ${isDefault?styles.outboundCardDefault:""}`} key={row.tag}>
              <div className={styles.cardTop}>
                <div><span className={styles.typeBadge}>{protocolTitle(row.type)}</span>{isDefault?<span className={styles.defaultBadge}>{pick("پیش‌فرض","DEFAULT")}</span>:null}</div>
                <span className={row.type==="direct"?styles.healthNeutral:(test?.ok?styles.healthOk:styles.healthIdle)}>{row.type==="direct"?"DIRECT":test?.ok?pick("سالم","HEALTHY"):pick("تست نشده","NOT TESTED")}</span>
              </div>
              <h3 className={styles.mono}>{row.tag}</h3>
              <div className={styles.endpoint}>{endpoint(row)}</div>
              <div className={styles.metaGrid}>
                <div><span>Transport</span><b>{transportLabel(row)}</b></div>
                <div><span>Host / SNI</span><b>{headerValue(row.transport?.headers,"Host")||row.tls?.server_name||"—"}</b></div>
                <div><span>Path</span><b>{row.transport?.path||row.transport?.service_name||"—"}</b></div>
                <div><span>{pick("مدیریت","Managed")}</span><b>{row.managed?pick("بله","Yes"):pick("سیستمی","System")}</b></div>
              </div>

              {test?<div className={test.ok?styles.testSuccess:styles.testError}>
                <div><span>Exit IP</span><b className={styles.mono}>{test.exit_ip||"—"}</b></div>
                <div><span>Latency</span><b>{test.latency_ms!=null?`${test.latency_ms.toFixed(1)} ms`:"—"}</b></div>
                <div><span>TCP</span><b>{test.tcp_ok?`PASS${test.tcp_ms!=null?` · ${test.tcp_ms.toFixed(1)} ms`:""}`:"FAIL"}</b></div>
                <div><span>HTTP</span><b>{test.http_code||"—"}</b></div>
                {!test.ok&&test.error?<p>{test.error}</p>:null}
              </div>:null}

              {editingTag===row.tag&&editDraft?<div className={styles.editBox}>
                <div className={styles.editGrid}>
                  <label><span>Address / IP</span><input value={editDraft.server} onChange={e=>setEditDraft({...editDraft,server:e.target.value})}/></label>
                  <label><span>Port</span><input inputMode="numeric" value={editDraft.serverPort} onChange={e=>setEditDraft({...editDraft,serverPort:e.target.value})}/></label>
                  <label><span>Host</span><input value={editDraft.host} onChange={e=>setEditDraft({...editDraft,host:e.target.value})}/></label>
                  <label><span>Path</span><input value={editDraft.path} onChange={e=>setEditDraft({...editDraft,path:e.target.value})}/></label>
                  <label className={styles.editWide}><span>SNI</span><input value={editDraft.sni} onChange={e=>setEditDraft({...editDraft,sni:e.target.value})}/></label>
                </div>
                <div className={styles.inlineActions}><button className={styles.primaryButton} onClick={()=>void saveEdit()} disabled={Boolean(busy)}>{pick("ذخیره امن","Save safely")}</button><button className={styles.ghostButton} onClick={()=>{setEditingTag("");setEditDraft(null);}}>{pick("لغو","Cancel")}</button></div>
              </div>:null}

              <div className={styles.cardActions}>
                {row.type!=="direct"&&editable?<button onClick={()=>void testOutbound(row.tag)} disabled={Boolean(busy)}>{busy===`test:${row.tag}`?pick("تست...","Testing..."):pick("تست واقعی","Real test")}</button>:null}
                {editable?<button onClick={()=>openEdit(row)} disabled={Boolean(busy)}>{pick("ویرایش","Edit")}</button>:null}
                {!isDefault?<button onClick={()=>void makeDefault(row.tag)} disabled={Boolean(busy)}>{pick("مسیر پیش‌فرض","Set default")}</button>:null}
                {editable?<button className={styles.dangerButton} onClick={()=>void removeOutbound(row.tag)} disabled={Boolean(busy)}>{pick("حذف","Delete")}</button>:null}
              </div>
            </article>;
          })}
        </div>
      </section>:null}

      {tab==="add"?<section className={styles.panel}>
        <div className={styles.addLayout}>
          <div className={styles.addMain}>
            <span className={styles.sectionKicker}>IMPORT OUTBOUND</span>
            <h2>{pick("افزودن خروجی جدید","Add a new outbound")}</h2>
            <p>{pick("کانفیگ را Paste کنید؛ TwinPanel آن را Parse می‌کند، به فرمت Sing-box تبدیل می‌کند، Config Check می‌گیرد و فقط بعد از اعتبارسنجی ذخیره می‌کند.","Paste a config. TwinPanel parses it, converts it to Sing-box format, validates the config, and saves only after a successful check.")}</p>
            <div className={styles.protocolChips}>{supported.map(item=><span key={item}>{protocolTitle(item)}</span>)}</div>
            <textarea
              className={styles.configArea}
              value={config}
              onChange={event=>setConfig(event.target.value)}
              placeholder={"vless://...\nvmess://...\ntrojan://...\nss://..."}
              spellCheck={false}
            />
            <label className={styles.checkRow}><input type="checkbox" checked={setDefaultOnImport} onChange={event=>setSetDefaultOnImport(event.target.checked)}/><span>{pick("بعد از ذخیره، مسیر پیش‌فرض کل نود هم روی این Outbound قرار بگیرد","Also make this outbound the node-wide default after import")}</span></label>
            <div className={styles.addActions}><button className={styles.primaryButton} onClick={()=>void importConfig()} disabled={Boolean(busy)||!config.trim()}>{busy==="import"?pick("در حال بررسی و ذخیره...","Validating and saving..."):pick("بررسی، ذخیره و اضافه‌کردن به Pool","Validate & add to pool")}</button><button className={styles.ghostButton} onClick={()=>setConfig("")} disabled={Boolean(busy)}>{pick("پاک کردن","Clear")}</button></div>
          </div>
          <aside className={styles.addAside}>
            <div className={styles.safetyCard}><span className={styles.safetyIcon}>✓</span><div><b>{pick("اعمال امن","Safe apply")}</b><p>{pick("قبل از Restart، فایل جدید با Sing-box check اعتبارسنجی می‌شود.","The new config is validated with sing-box check before restart.")}</p></div></div>
            <div className={styles.safetyCard}><span className={styles.safetyIcon}>↶</span><div><b>Rollback</b><p>{pick("اگر Restart یا Active شدن سرویس شکست بخورد، Config قبلی برمی‌گردد.","If restart or activation fails, the previous config is restored.")}</p></div></div>
            <div className={styles.safetyCard}><span className={styles.safetyIcon}>◎</span><div><b>{pick("تست جدا از Production","Isolated test")}</b><p>{pick("تست Outbound مسیر اصلی سرویس را Restart نمی‌کند.","Outbound testing does not restart the primary service path.")}</p></div></div>
          </aside>
        </div>
      </section>:null}
    </div>
  </Shell>;
}
