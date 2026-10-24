"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {createPortal} from "react-dom";

import {adminApi,type AdminUser,type RuntimeRow} from "../lib/admin-api";
import {subscriptionProtocolApi,type SubscriptionProtocolDefinition} from "../lib/subscription-protocol-api";
import {useI18n} from "../lib/i18n";

const cleanNumber=(value:string)=>{
  const raw=value.trim();
  if(!raw)return null;
  const parsed=Number(raw);
  return Number.isFinite(parsed)?parsed:null;
};
const num=(value:unknown)=>{
  const parsed=Number(value??0);
  return Number.isFinite(parsed)?parsed:0;
};

export function AdminManualSubscriptionCreate(){
  const {pick}=useI18n();
  const [mounted,setMounted]=useState(false);
  const [actionHost,setActionHost]=useState<HTMLElement|null>(null);
  const [open,setOpen]=useState(false);
  const [users,setUsers]=useState<AdminUser[]>([]);
  const [plans,setPlans]=useState<RuntimeRow[]>([]);
  const [catalog,setCatalog]=useState<SubscriptionProtocolDefinition[]>([]);
  const [loading,setLoading]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [search,setSearch]=useState("");
  const [userId,setUserId]=useState(0);
  const [planId,setPlanId]=useState(0);
  const [traffic,setTraffic]=useState("");
  const [duration,setDuration]=useState("");
  const [deviceLimit,setDeviceLimit]=useState("1");
  const [username,setUsername]=useState("");
  const [password,setPassword]=useState("");
  const [protocols,setProtocols]=useState<string[]>([]);

  useEffect(()=>{
    setMounted(true);
    let frame=0;
    let host:HTMLDivElement|null=null;
    let original:HTMLButtonElement|null=null;
    let originalDisplay="";

    const locate=()=>{
      const pageHead=document.querySelector<HTMLElement>(".legacy-subscriptions-page .page-head");
      if(!pageHead){frame=window.requestAnimationFrame(locate);return;}

      original=pageHead.querySelector<HTMLButtonElement>(":scope > button.primary");
      if(!original){frame=window.requestAnimationFrame(locate);return;}

      host=document.createElement("div");
      host.className="row-actions subscription-create-action-group";
      host.setAttribute("data-subscription-create-actions","true");
      pageHead.insertBefore(host,original);

      originalDisplay=original.style.display;
      original.style.display="none";
      setActionHost(host);
    };

    frame=window.requestAnimationFrame(locate);
    return()=>{
      window.cancelAnimationFrame(frame);
      setActionHost(null);
      if(original)original.style.display=originalDisplay;
      host?.remove();
    };
  },[]);

  const filteredUsers=useMemo(()=>{
    const query=search.trim().toLowerCase();
    return users
      .filter(user=>user.role!=="admin"&&user.is_active!==false)
      .filter(user=>!query||`${user.full_name||""} ${user.email||""} ${user.phone||""}`.toLowerCase().includes(query))
      .slice(0,50);
  },[users,search]);

  const classicCatalog=useMemo(()=>catalog.filter(item=>item.family==="classic"),[catalog]);
  const modernCatalog=useMemo(()=>catalog.filter(item=>item.family==="modern"),[catalog]);

  const applyPlan=(id:number,planRows=plans)=>{
    setPlanId(id);
    if(!id)return;
    const plan=planRows.find(item=>num(item.id)===id);
    if(!plan)return;
    setTraffic(String(num(plan.traffic_gb)));
    setDuration(String(Math.max(1,Math.trunc(num(plan.duration_days)||30))));
    setDeviceLimit(String(Math.max(1,Math.trunc(num(plan.device_limit)||1))));
  };

  const openCreate=async()=>{
    setOpen(true);setLoading(true);setError("");setOk("");setSearch("");
    setUsername("");setPassword("");setProtocols([]);setPlanId(0);
    try{
      const [userRows,planRows,catalogPayload]=await Promise.all([
        adminApi.users(),
        adminApi.plans(),
        subscriptionProtocolApi.catalog(),
      ]);

      if(catalogPayload.protocols.length!==15){
        throw new Error(pick("کاتالوگ ۱۵ پروتکل کامل نیست","The 15-protocol catalog is incomplete"));
      }

      setUsers(userRows);
      setPlans(planRows);
      setCatalog(catalogPayload.protocols);

      const firstUser=userRows.find(user=>user.role!=="admin"&&user.is_active!==false);
      setUserId(firstUser?.id||0);

      const firstPlan=planRows.find(item=>item.is_active!==false)||planRows[0];
      const firstPlanId=num(firstPlan?.id);
      if(firstPlanId)applyPlan(firstPlanId,planRows);
      else{setTraffic("");setDuration("");setDeviceLimit("1");}

      setProtocols(catalogPayload.protocols.filter(item=>item.family==="classic").map(item=>item.key));
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setLoading(false);
    }
  };

  const toggleProtocol=(key:string)=>{
    setProtocols(current=>current.includes(key)
      ?current.filter(item=>item!==key)
      :[...current,key]);
  };

  const selectAllProtocols=()=>setProtocols(catalog.map(item=>item.key));
  const clearProtocols=()=>setProtocols([]);

  const submit=async(event:FormEvent)=>{
    event.preventDefault();
    if(busy||loading)return;

    const trafficValue=cleanNumber(traffic);
    const durationValue=cleanNumber(duration);
    const deviceValue=cleanNumber(deviceLimit);

    if(!userId){setError(pick("کاربر را انتخاب کنید","Select a user"));return;}
    if(trafficValue===null||trafficValue<0){setError(pick("حجم را وارد کنید؛ صفر یعنی نامحدود","Enter traffic; zero means unlimited"));return;}
    if(durationValue===null||durationValue<=0||!Number.isInteger(durationValue)){setError(pick("مدت را به روز و بیشتر از صفر وارد کنید","Enter duration in whole days greater than zero"));return;}
    if(deviceValue===null||deviceValue<1||!Number.isInteger(deviceValue)){setError(pick("تعداد اتصال همزمان معتبر نیست","Concurrent device limit is invalid"));return;}
    if(protocols.length===0){setError(pick("حداقل یک پروتکل انتخاب کنید","Select at least one protocol"));return;}

    setBusy(true);setError("");setOk("");
    try{
      const created=await adminApi.createSubscriptionV2({
        user_id:userId,
        plan_id:planId||null,
        node_ids:[],
        protocols,
        traffic_gb:trafficValue,
        duration_days:durationValue,
        device_limit:deviceValue,
        ...(username.trim()?{username:username.trim()}:{}),
        ...(password.trim()?{password:password.trim()}:{}),
      });

      try{await adminApi.provisionSubscription(Number(created.id||0));}catch{}

      setOk(pick("اشتراک با پروتکل‌های انتخابی ساخته و اکانت صادر شد. لیست در حال بروزرسانی است…","Subscription created with the selected protocols and provisioned. Refreshing…"));
      window.setTimeout(()=>window.location.reload(),900);
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy(false);
    }
  };

  if(!mounted)return null;

  const action=actionHost?createPortal(
    <button type="button" className="primary" onClick={()=>void openCreate()}>
      ＋ {pick("اشتراک جدید","New subscription")}
    </button>,
    actionHost,
  ):null;

  const protocolGroup=(title:string,items:SubscriptionProtocolDefinition[])=>(
    <div className="runtime-choice-section">
      <div className="card-head"><b>{title}</b><small>{items.length}</small></div>
      <div className="protocol-toggle-grid">
        {items.map(item=><label className="toggle module-toggle" key={item.key}><span>{item.title}</span><input type="checkbox" checked={protocols.includes(item.key)} onChange={()=>toggleProtocol(item.key)}/><i/></label>)}
      </div>
    </div>
  );

  const modal=open?createPortal(
    <div className="runtime-modal manual-subscription-modal" role="dialog" aria-modal="true" aria-label={pick("ساخت اشتراک","Create subscription")}>
      <button type="button" className="runtime-modal-bg" aria-label="close" onClick={()=>!busy&&setOpen(false)}/>
      <div className="runtime-modal-card manage-card">
        <div className="card-head">
          <div>
            <b>{pick("ساخت اشتراک","Create subscription")}</b>
            <small>{pick("پلن فقط حجم، مدت، قیمت و محدودیت دستگاه را تعیین می‌کند؛ پروتکل‌ها فقط برای همین اشتراک انتخاب می‌شوند.","The plan supplies commercial limits only; protocols are selected only for this subscription.")}</small>
          </div>
          <button type="button" className="icon-button" disabled={busy} onClick={()=>setOpen(false)}>×</button>
        </div>

        {error&&<div className="runtime-error">{error}</div>}
        {ok&&<div className="runtime-success">{ok}</div>}

        <form className="subscription-create-form" onSubmit={submit}>
          <div className="setting-grid compact-create-grid">
            <label className="field"><span>{pick("جستجوی کاربر","User search")}</span><input value={search} onChange={event=>setSearch(event.target.value)} placeholder={pick("نام، ایمیل یا موبایل…","Name, email or mobile…")}/></label>
            <label className="field"><span>{pick("کاربر","User")}</span><select value={userId} disabled={loading} onChange={event=>setUserId(Number(event.target.value))}><option value={0}>{loading?pick("در حال دریافت…","Loading…"):pick("انتخاب کاربر","Select user")}</option>{filteredUsers.map(user=><option key={user.id} value={user.id}>{user.full_name||user.email||`#${user.id}`} · {user.phone||user.email||"—"}</option>)}</select></label>
            <label className="field"><span>{pick("پلن","Plan")}</span><select value={planId} disabled={loading} onChange={event=>{const id=Number(event.target.value);applyPlan(id);if(!id){setTraffic("");setDuration("");setDeviceLimit("1");}}}><option value={0}>{pick("بدون پلن / دستی","No plan / Manual")}</option>{plans.filter(item=>item.is_active!==false).map(plan=><option key={num(plan.id)} value={num(plan.id)}>{String(plan.name||`#${num(plan.id)}`)}</option>)}</select></label>
            <label className="field"><span>{pick("حجم GB","Traffic GB")}</span><input required inputMode="decimal" type="number" min={0} step="0.1" value={traffic} onChange={event=>setTraffic(event.target.value)} placeholder={pick("مثلاً 50؛ صفر = نامحدود","e.g. 50; zero = unlimited")}/></label>
            <label className="field"><span>{pick("مدت روز","Duration days")}</span><input required inputMode="numeric" type="number" min={1} step={1} value={duration} onChange={event=>setDuration(event.target.value)} placeholder={pick("مثلاً 30","e.g. 30")}/></label>
            <label className="field"><span>{pick("اتصال همزمان","Concurrent devices")}</span><input required inputMode="numeric" type="number" min={1} step={1} value={deviceLimit} onChange={event=>setDeviceLimit(event.target.value)}/></label>
            <label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" autoComplete="off" value={username} onChange={event=>setUsername(event.target.value)} placeholder={pick("خالی = خودکار","empty = automatic")}/></label>
            <label className="field"><span>{pick("رمز عبور","Password")}</span><input dir="ltr" type="text" autoComplete="new-password" value={password} onChange={event=>setPassword(event.target.value)} placeholder={pick("خالی = خودکار","empty = automatic")}/></label>
          </div>

          <div className="runtime-choice-section">
            <div className="card-head">
              <div><b>{pick("پروتکل‌های این اشتراک","Protocols for this subscription")}</b><small>{protocols.length}/15</small></div>
              <div className="row-actions">
                <button type="button" className="ghost" disabled={loading||catalog.length!==15} onClick={selectAllProtocols}>{pick("انتخاب همه ۱۵ پروتکل","Select all 15 protocols")}</button>
                <button type="button" className="ghost" disabled={loading||protocols.length===0} onClick={clearProtocols}>{pick("لغو انتخاب همه","Clear selection")}</button>
              </div>
            </div>
          </div>

          {protocolGroup(pick("پروتکل‌های کلاسیک","Classic protocols"),classicCatalog)}
          {protocolGroup(pick("پروتکل‌های جدید","Modern protocols"),modernCatalog)}

          <div className="modalActions">
            <button type="button" className="ghost" disabled={busy} onClick={()=>setOpen(false)}>{pick("انصراف","Cancel")}</button>
            <button type="submit" className="primary" disabled={busy||loading||catalog.length!==15}>{busy?pick("در حال ساخت…","Creating…"):pick("ساخت و صدور اکانت","Create & provision account")}</button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  ):null;

  return <>{action}{modal}</>;
}
