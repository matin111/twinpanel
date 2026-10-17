"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {createPortal} from "react-dom";

import {adminApi,type AdminUser} from "../lib/admin-api";
import {useI18n} from "../lib/i18n";

const protocolKeys=["cisco","openvpn","wireguard","l2tp","v2ray"] as const;
const protocolLabels:Record<(typeof protocolKeys)[number],string>={
  cisco:"Cisco / OpenConnect",
  openvpn:"OpenVPN",
  wireguard:"WireGuard",
  l2tp:"L2TP / IPsec",
  v2ray:"V2Ray / Xray",
};

const cleanNumber=(value:string)=>{
  const raw=value.trim();
  if(!raw)return null;
  const parsed=Number(raw);
  return Number.isFinite(parsed)?parsed:null;
};

export function AdminManualSubscriptionCreate(){
  const {pick}=useI18n();
  const [mounted,setMounted]=useState(false);
  const [actionHost,setActionHost]=useState<HTMLElement|null>(null);
  const [open,setOpen]=useState(false);
  const [users,setUsers]=useState<AdminUser[]>([]);
  const [loadingUsers,setLoadingUsers]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [search,setSearch]=useState("");
  const [userId,setUserId]=useState(0);
  const [traffic,setTraffic]=useState("");
  const [duration,setDuration]=useState("");
  const [deviceLimit,setDeviceLimit]=useState("1");
  const [username,setUsername]=useState("");
  const [password,setPassword]=useState("");
  const [protocols,setProtocols]=useState<string[]>([...protocolKeys]);

  useEffect(()=>{
    setMounted(true);
    let frame=0;
    const locate=()=>{
      const host=document.querySelector<HTMLElement>(".legacy-subscriptions-page .page-head");
      if(host){setActionHost(host);return;}
      frame=window.requestAnimationFrame(locate);
    };
    frame=window.requestAnimationFrame(locate);
    return()=>window.cancelAnimationFrame(frame);
  },[]);

  const filteredUsers=useMemo(()=>{
    const query=search.trim().toLowerCase();
    return users
      .filter(user=>user.role!=="admin"&&user.is_active!==false)
      .filter(user=>!query||`${user.full_name||""} ${user.email||""} ${user.phone||""}`.toLowerCase().includes(query))
      .slice(0,50);
  },[users,search]);

  const loadUsers=async()=>{
    setLoadingUsers(true);setError("");
    try{
      const rows=await adminApi.users();
      setUsers(rows);
      const first=rows.find(user=>user.role!=="admin"&&user.is_active!==false);
      setUserId(first?.id||0);
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setLoadingUsers(false);
    }
  };

  const openManual=()=>{
    setError("");setOk("");setSearch("");
    setTraffic("");setDuration("");setDeviceLimit("1");
    setUsername("");setPassword("");setProtocols([...protocolKeys]);
    setOpen(true);
    void loadUsers();
  };

  const toggleProtocol=(key:string)=>{
    setProtocols(current=>current.includes(key)
      ?current.filter(item=>item!==key)
      :[...current,key]);
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();
    if(busy)return;

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
        plan_id:null,
        node_ids:[],
        protocols,
        traffic_gb:trafficValue,
        duration_days:durationValue,
        device_limit:deviceValue,
        ...(username.trim()?{username:username.trim()}:{}),
        ...(password.trim()?{password:password.trim()}:{}),
      });

      try{await adminApi.provisionSubscription(Number(created.id||0));}catch{}

      setOk(pick("اشتراک دستی ساخته و اکانت صادر شد. لیست در حال بروزرسانی است…","Manual subscription created and account provisioned. Refreshing the list…"));
      window.setTimeout(()=>window.location.reload(),900);
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy(false);
    }
  };

  if(!mounted)return null;

  const action=actionHost?createPortal(
    <button type="button" className="primary-soft" onClick={openManual}>
      ＋ {pick("اشتراک دستی","Manual subscription")}
    </button>,
    actionHost,
  ):null;

  const modal=open?createPortal(
    <div className="runtime-modal" role="dialog" aria-modal="true" aria-label={pick("ساخت اشتراک دستی","Create manual subscription")}>
      <button type="button" className="runtime-modal-bg" aria-label="close" onClick={()=>!busy&&setOpen(false)}/>
      <div className="runtime-modal-card manage-card">
        <div className="card-head">
          <div>
            <b>{pick("ساخت اشتراک دستی","Create manual subscription")}</b>
            <small>{pick("بدون انتخاب پلن؛ حجم، مدت و پروتکل‌ها مستقیماً برای همین اشتراک تعیین می‌شوند.","No plan is selected; traffic, duration and protocols are assigned directly to this subscription.")}</small>
          </div>
          <button type="button" className="icon-button" disabled={busy} onClick={()=>setOpen(false)}>×</button>
        </div>

        {error&&<div className="runtime-error">{error}</div>}
        {ok&&<div className="runtime-success">{ok}</div>}

        <form className="subscription-create-form" onSubmit={submit}>
          <div className="runtime-warning">
            {pick("حالت دستی به هیچ پلنی وابسته نیست. حجم ۰ یعنی نامحدود؛ مدت باید مشخص باشد.","Manual mode is not linked to any plan. Traffic 0 means unlimited; duration must be specified.")}
          </div>

          <div className="setting-grid compact-create-grid">
            <label className="field"><span>{pick("جستجوی کاربر","User search")}</span><input value={search} onChange={event=>setSearch(event.target.value)} placeholder={pick("نام، ایمیل یا موبایل…","Name, email or mobile…")}/></label>
            <label className="field"><span>{pick("کاربر","User")}</span><select value={userId} disabled={loadingUsers} onChange={event=>setUserId(Number(event.target.value))}><option value={0}>{loadingUsers?pick("در حال دریافت…","Loading…"):pick("انتخاب کاربر","Select user")}</option>{filteredUsers.map(user=><option key={user.id} value={user.id}>{user.full_name||user.email||`#${user.id}`} · {user.phone||user.email||"—"}</option>)}</select></label>
            <label className="field"><span>{pick("حجم GB","Traffic GB")}</span><input required inputMode="decimal" type="number" min={0} step="0.1" value={traffic} onChange={event=>setTraffic(event.target.value)} placeholder={pick("مثلاً 50؛ صفر = نامحدود","e.g. 50; zero = unlimited")}/></label>
            <label className="field"><span>{pick("مدت روز","Duration days")}</span><input required inputMode="numeric" type="number" min={1} step={1} value={duration} onChange={event=>setDuration(event.target.value)} placeholder={pick("مثلاً 30","e.g. 30")}/></label>
            <label className="field"><span>{pick("اتصال همزمان","Concurrent devices")}</span><input required inputMode="numeric" type="number" min={1} step={1} value={deviceLimit} onChange={event=>setDeviceLimit(event.target.value)}/></label>
            <label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" autoComplete="off" value={username} onChange={event=>setUsername(event.target.value)} placeholder={pick("خالی = خودکار","empty = automatic")}/></label>
            <label className="field"><span>{pick("رمز عبور","Password")}</span><input dir="ltr" type="text" autoComplete="new-password" value={password} onChange={event=>setPassword(event.target.value)} placeholder={pick("خالی = خودکار","empty = automatic")}/></label>
          </div>

          <div className="runtime-choice-section">
            <b>{pick("پروتکل‌ها","Protocols")}</b>
            <div className="protocol-toggle-grid">
              {protocolKeys.map(key=><label className="toggle module-toggle" key={key}><span>{protocolLabels[key]}</span><input type="checkbox" checked={protocols.includes(key)} onChange={()=>toggleProtocol(key)}/><i/></label>)}
            </div>
          </div>

          <div className="modalActions">
            <button type="button" className="ghost" disabled={busy} onClick={()=>setOpen(false)}>{pick("انصراف","Cancel")}</button>
            <button type="submit" className="primary" disabled={busy||loadingUsers}>{busy?pick("در حال ساخت…","Creating…"):pick("ساخت و صدور اکانت","Create & provision account")}</button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  ):null;

  return <>{action}{modal}</>;
}
