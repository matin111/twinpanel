"use client";

import {useEffect,useMemo,useState} from "react";
import {createPortal} from "react-dom";

import {adminApi,type RuntimeRow} from "../lib/admin-api";
import {
  subscriptionDeliveryPolicyApi,
  type DeliveryInfrastructureNode,
  type DeliveryPolicy,
  type DeliveryTarget,
} from "../lib/subscription-delivery-policy-api";
import {useI18n} from "../lib/i18n";
import styles from "./subscription-delivery-policy-manager.module.css";

type TargetDraft={
  enabled:boolean;
  direct_enabled:boolean;
  tunnel_enabled:boolean;
  tunnel_id:number|null;
  priority:number;
};

const s=(value:unknown)=>String(value??"");
const n=(value:unknown)=>{const out=Number(value??0);return Number.isFinite(out)?out:0;};

function flag(code?:string|null){
  const value=String(code||"").toUpperCase();
  if(!/^[A-Z]{2}$/.test(value))return "🌐";
  return String.fromCodePoint(...[...value].map(char=>127397+char.charCodeAt(0)));
}

function activeSubscriptionId(){
  const active=document.querySelector<HTMLElement>(".subs-list-item.active");
  const match=String(active?.textContent||"").match(/#\s*(\d+)/);
  return match?Number(match[1]):0;
}

function initialTargets(policy:DeliveryPolicy){
  const map:Record<number,TargetDraft>={};
  for(const node of policy.infrastructure){
    const target=policy.targets.find(item=>item.node_id===node.id);
    map[node.id]=target?{
      enabled:true,
      direct_enabled:Boolean(target.direct_enabled),
      tunnel_enabled:Boolean(target.tunnel_enabled),
      tunnel_id:target.tunnel_id??null,
      priority:Number(target.priority||100),
    }:{enabled:false,direct_enabled:false,tunnel_enabled:false,tunnel_id:null,priority:100};
  }
  return map;
}

function protocolCount(node:DeliveryInfrastructureNode,protocols:string[]){
  if(!protocols.length)return {installed:0,online:0};
  let installed=0;let online=0;
  for(const protocol of protocols){
    const row=node.protocols.find(item=>item.protocol===protocol);
    if(row){installed+=1;if(row.status==="online")online+=1;}
  }
  return {installed,online};
}

export function SubscriptionDeliveryPolicyManager(){
  const {pick}=useI18n();
  const [mounted,setMounted]=useState(false);
  const [actionHost,setActionHost]=useState<HTMLElement|null>(null);
  const [open,setOpen]=useState(false);
  const [tab,setTab]=useState<"protocols"|"servers">("protocols");
  const [subscriptions,setSubscriptions]=useState<RuntimeRow[]>([]);
  const [subscriptionId,setSubscriptionId]=useState(0);
  const [policy,setPolicy]=useState<DeliveryPolicy|null>(null);
  const [protocols,setProtocols]=useState<string[]>([]);
  const [targets,setTargets]=useState<Record<number,TargetDraft>>({});
  const [loading,setLoading]=useState(false);
  const [saving,setSaving]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");

  useEffect(()=>{
    setMounted(true);
    let frame=0;
    let host:HTMLDivElement|null=null;
    const locate=()=>{
      const actions=document.querySelector<HTMLElement>(".subs-full .page-head .action-row");
      if(!actions){frame=window.requestAnimationFrame(locate);return;}
      host=document.createElement("div");
      host.className="subscription-delivery-policy-action-host";
      host.setAttribute("data-delivery-policy-actions","true");
      actions.prepend(host);
      setActionHost(host);
    };
    frame=window.requestAnimationFrame(locate);
    return()=>{window.cancelAnimationFrame(frame);setActionHost(null);host?.remove();};
  },[]);

  const readyCapabilities=useMemo(()=>policy?.capabilities.filter(item=>item.account_delivery_ready)??[],[policy]);
  const blockedModernCount=useMemo(()=>policy?.capabilities.filter(item=>!item.account_delivery_ready).length??0,[policy]);

  const hydrate=(next:DeliveryPolicy)=>{
    setPolicy(next);
    setProtocols([...next.protocols]);
    setTargets(initialTargets(next));
  };

  const loadPolicy=async(id:number)=>{
    if(!id){setPolicy(null);return;}
    setLoading(true);setError("");setNotice("");
    try{hydrate(await subscriptionDeliveryPolicyApi.get(id));}
    catch(reason){setPolicy(null);setError(reason instanceof Error?reason.message:String(reason));}
    finally{setLoading(false);}
  };

  const openManager=async()=>{
    setOpen(true);setTab("protocols");setError("");setNotice("");setLoading(true);
    try{
      const rows=await adminApi.subscriptionsV2();
      setSubscriptions(rows);
      const current=activeSubscriptionId();
      const id=current&&rows.some(row=>n(row.id)===current)?current:n(rows[0]?.id);
      setSubscriptionId(id);
      if(id)hydrate(await subscriptionDeliveryPolicyApi.get(id));
      else setPolicy(null);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setLoading(false);}
  };

  const chooseSubscription=(id:number)=>{
    setSubscriptionId(id);
    void loadPolicy(id);
  };

  const toggleProtocol=(protocol:string)=>{
    setProtocols(current=>current.includes(protocol)?current.filter(item=>item!==protocol):[...current,protocol]);
  };

  const updateTarget=(node:DeliveryInfrastructureNode,patch:Partial<TargetDraft>)=>{
    setTargets(current=>{
      const previous=current[node.id]||{enabled:false,direct_enabled:false,tunnel_enabled:false,tunnel_id:null,priority:100};
      const next={...previous,...patch};
      if(patch.enabled===false){next.direct_enabled=false;next.tunnel_enabled=false;next.tunnel_id=null;}
      if(patch.enabled===true&&!previous.enabled&&!next.direct_enabled&&!next.tunnel_enabled)next.direct_enabled=true;
      if(patch.tunnel_enabled===false)next.tunnel_id=null;
      if(patch.tunnel_enabled===true&&!next.tunnel_id&&node.tunnels.length===1)next.tunnel_id=node.tunnels[0].id;
      return {...current,[node.id]:next};
    });
  };

  const save=async()=>{
    if(!policy||!subscriptionId||saving)return;
    if(!protocols.length){setError(pick("حداقل یک پروتکل فعال انتخاب کنید.","Select at least one active protocol."));setTab("protocols");return;}
    setSaving(true);setError("");setNotice("");
    try{
      const payload={
        protocols,
        targets:policy.infrastructure.map(node=>{
          const item=targets[node.id]||{enabled:false,direct_enabled:false,tunnel_enabled:false,tunnel_id:null,priority:100};
          return {node_id:node.id,...item};
        }),
      };
      const saved=await subscriptionDeliveryPolicyApi.save(subscriptionId,payload);
      hydrate(saved);
      const reconciled=await subscriptionDeliveryPolicyApi.reconcile(subscriptionId);
      if(reconciled.ok){
        setNotice(pick("Policy ذخیره و دسترسی‌های لازم با حفظ Credentialهای موجود همگام شد.","Policy saved and required access was reconciled while preserving existing credentials."));
      }else{
        const count=Array.isArray(reconciled.errors)?reconciled.errors.length:0;
        setNotice(pick(`Policy ذخیره شد؛ Reconcile برای ${count} مورد نیاز به بررسی دارد.`,`Policy saved; reconcile needs review for ${count} item(s).`));
      }
      hydrate(await subscriptionDeliveryPolicyApi.get(subscriptionId));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setSaving(false);}
  };

  if(!mounted)return null;

  const action=actionHost?createPortal(
    <button type="button" className="ghost" onClick={()=>void openManager()}>
      ◈ {pick("دسترسی اتصال","Connection access")}
    </button>,
    actionHost,
  ):null;

  const modal=open?createPortal(
    <div className={styles.backdrop} role="dialog" aria-modal="true" aria-label={pick("دسترسی اتصال اشتراک","Subscription connection access")}>
      <button className={styles.backdropClose} type="button" aria-label={pick("بستن","Close")} onClick={()=>!saving&&setOpen(false)}/>
      <section className={styles.modal}>
        <header className={styles.header}>
          <div className={styles.headerIcon}>◈</div>
          <div className={styles.headerCopy}>
            <span>{pick("Account Delivery","Account Delivery")}</span>
            <h2>{pick("دسترسی اتصال","Connection access")}</h2>
            <p>{pick("پروتکل، سرور و مسیر Direct/Tunnel را برای همین اشتراک مستقل مدیریت کنید.","Manage protocols, servers and Direct/Tunnel routes independently for this subscription.")}</p>
          </div>
          <button className={styles.close} type="button" disabled={saving} onClick={()=>setOpen(false)}>×</button>
        </header>

        <div className={styles.toolbar}>
          <label>
            <span>{pick("اشتراک","Subscription")}</span>
            <select value={subscriptionId} disabled={loading||saving} onChange={event=>chooseSubscription(Number(event.target.value))}>
              {subscriptions.map(row=><option key={n(row.id)} value={n(row.id)}>#{n(row.id)} · {s(row.account_username||row.customer_name||row.customer_email)||pick("بدون نام","Unnamed")}</option>)}
            </select>
          </label>
          {policy&&<div className={`${styles.modeBadge} ${policy.mode==="explicit"?styles.explicit:styles.legacy}`}>
            <i/>{policy.mode==="explicit"?pick("Policy صریح","Explicit policy"):pick("حالت Legacy","Legacy mode")}
          </div>}
        </div>

        {error&&<div className={styles.error}>{error}</div>}
        {notice&&<div className={styles.notice}>{notice}</div>}
        {policy?.mode==="legacy"&&<div className={styles.warning}>{pick("این اشتراک هنوز رفتار قدیمی Tunnel-first + Direct fallback را دارد. با اولین Save، فقط انتخاب‌های صریح همین صفحه حاکم می‌شوند.","This subscription still uses legacy Tunnel-first + Direct fallback. After the first Save, only the explicit choices on this screen will apply.")}</div>}

        <div className={styles.tabs}>
          <button type="button" className={tab==="protocols"?styles.activeTab:""} onClick={()=>setTab("protocols")}>{pick("پروتکل‌ها","Protocols")}</button>
          <button type="button" className={tab==="servers"?styles.activeTab:""} onClick={()=>setTab("servers")}>{pick("سرورها و مسیر اتصال","Servers & routes")}</button>
        </div>

        <div className={styles.body}>
          {loading?<div className={styles.loading}>{pick("در حال دریافت Policy…","Loading policy…")}</div>:policy&&tab==="protocols"?<>
            <div className={styles.sectionHead}>
              <div><b>{pick("پروتکل‌های اکانت","Account protocols")}</b><small>{pick("فقط Protocolهایی که Provision/Export واقعی دارند قابل فعال‌سازی هستند.","Only protocols with real provisioning/export are switchable.")}</small></div>
              <span>{protocols.length.toLocaleString("fa-IR")} {pick("فعال","active")}</span>
            </div>
            <div className={styles.protocolGrid}>
              {readyCapabilities.map(capability=>{
                const installed=policy.infrastructure.filter(node=>node.protocols.some(item=>item.protocol===capability.protocol)).length;
                const online=policy.infrastructure.filter(node=>node.protocols.some(item=>item.protocol===capability.protocol&&item.status==="online")).length;
                const checked=protocols.includes(capability.protocol);
                return <button type="button" key={capability.protocol} className={`${styles.protocolCard} ${checked?styles.selected:""}`} onClick={()=>toggleProtocol(capability.protocol)}>
                  <div><b>{capability.title}</b><small>{online}/{installed} {pick("سرور آماده","servers ready")}</small></div>
                  <span className={styles.switch} aria-hidden="true"><i/></span>
                </button>;
              })}
            </div>
            {blockedModernCount>0&&<div className={styles.info}>{pick(`${blockedModernCount} پروتکل Modern تا تکمیل Account Adapter و Quota Enforcement در Delivery قابل انتخاب نیستند.`,`${blockedModernCount} modern protocols remain unavailable for Delivery until Account Adapter and Quota Enforcement are complete.`)}</div>}
          </>:policy&&<>
            <div className={styles.sectionHead}>
              <div><b>{pick("سرورها و مسیر اتصال","Servers & connection route")}</b><small>{pick("Health فقط تحویل فعلی را کنترل می‌کند؛ Policy مشخص می‌کند چه مسیرهایی مجازند.","Health controls current delivery only; policy defines which routes are allowed.")}</small></div>
            </div>
            <div className={styles.serverList}>
              {policy.infrastructure.map(node=>{
                const target=targets[node.id]||{enabled:false,direct_enabled:false,tunnel_enabled:false,tunnel_id:null,priority:100};
                const availability=protocolCount(node,protocols);
                const endpoint=node.public_domain||node.public_ip||"—";
                return <article key={node.id} className={`${styles.serverCard} ${target.enabled?styles.serverEnabled:""}`}>
                  <div className={styles.serverTop}>
                    <div className={styles.serverIdentity}><span>{flag(node.country_code)}</span><div><b>{node.name}</b><small dir="ltr">{endpoint}</small></div></div>
                    <label className={styles.toggleLine}><span>{pick("استفاده برای این اشتراک","Use for subscription")}</span><input type="checkbox" checked={target.enabled} onChange={event=>updateTarget(node,{enabled:event.target.checked})}/><i/></label>
                  </div>
                  <div className={styles.healthRow}>
                    <span data-state={node.status}>{node.status==="online"?pick("Server Online","Server Online"):pick("Server Offline","Server Offline")}</span>
                    <span>{availability.online}/{availability.installed} {pick("پروتکل انتخاب‌شده آماده","selected protocols ready")}</span>
                    {!node.show_to_users&&<span data-state="hidden">{pick("مخفی از کاربران","Hidden from users")}</span>}
                  </div>
                  <div className={styles.routeGrid}>
                    <label className={`${styles.routeCard} ${target.direct_enabled?styles.routeSelected:""}`}>
                      <input type="checkbox" disabled={!target.enabled} checked={target.direct_enabled} onChange={event=>updateTarget(node,{direct_enabled:event.target.checked})}/>
                      <span><b>Direct</b><small>{pick("اتصال مستقیم به Exit Domain/IP","Direct connection to Exit domain/IP")}</small></span>
                    </label>
                    <label className={`${styles.routeCard} ${target.tunnel_enabled?styles.routeSelected:""} ${!node.tunnels.length?styles.routeUnavailable:""}`}>
                      <input type="checkbox" disabled={!target.enabled||!node.tunnels.length} checked={target.tunnel_enabled} onChange={event=>updateTarget(node,{tunnel_enabled:event.target.checked})}/>
                      <span><b>Tunnel</b><small>{node.tunnels.length?pick("تحویل از Iran ingress انتخابی","Deliver through selected Iran ingress"):pick("Tunnel فعالی برای این Exit نیست","No active tunnel for this Exit")}</small></span>
                    </label>
                  </div>
                  {target.enabled&&target.tunnel_enabled&&node.tunnels.length>0&&<label className={styles.tunnelSelect}><span>{pick("Tunnel","Tunnel")}</span><select value={target.tunnel_id??""} onChange={event=>updateTarget(node,{tunnel_id:Number(event.target.value)||null})}><option value="">{pick("انتخاب Tunnel","Select tunnel")}</option>{node.tunnels.map(tunnel=><option key={tunnel.id} value={tunnel.id}>#{tunnel.id} · Iran #{tunnel.iran_node_id} → {node.name} · {tunnel.status}</option>)}</select></label>}
                </article>;
              })}
            </div>
          </>}
        </div>

        <footer className={styles.footer}>
          <div>{policy?.share_code_stable&&<span>✓ {pick("لینک اشتراک ثابت می‌ماند","Subscription link stays stable")}</span>}</div>
          <button type="button" className="ghost" disabled={saving} onClick={()=>setOpen(false)}>{pick("انصراف","Cancel")}</button>
          <button type="button" className="primary" disabled={saving||loading||!policy} onClick={()=>void save()}>{saving?pick("در حال ذخیره و Reconcile…","Saving & reconciling…"):pick("ذخیره دسترسی اتصال","Save connection access")}</button>
        </footer>
      </section>
    </div>,
    document.body,
  ):null;

  return <>{action}{modal}</>;
}
