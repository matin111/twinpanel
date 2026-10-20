"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {QRCodeSVG} from "qrcode.react";
import {Badge,Card,Shell,Stat} from "./ui";
import {SubscriptionLinkDeliveryModal} from "./subscription-link-delivery-modal";
import {adminApi,AdminNode,AdminUser,RuntimeRow} from "../lib/admin-api";
import {legacyAdminApi} from "../lib/legacy-admin-api";
import {useI18n} from "../lib/i18n";

const GB=1024**3;
const protocolKeys=["cisco","openvpn","wireguard","l2tp","v2ray"] as const;
const protocolLabels:Record<string,string>={
  cisco:"Cisco / OpenConnect",
  openvpn:"OpenVPN",
  wireguard:"WireGuard",
  l2tp:"L2TP / IPsec",
  v2ray:"V2Ray / Xray"
};

const s=(value:unknown)=>String(value??"");
const n=(value:unknown)=>{const out=Number(value??0);return Number.isFinite(out)?out:0;};
const list=(value:unknown):RuntimeRow[]=>Array.isArray(value)?value.filter(item=>item&&typeof item==="object") as RuntimeRow[]:value&&typeof value==="object"?[value as RuntimeRow]:[];
const strings=(value:unknown)=>Array.isArray(value)?value.map(String):[];
const formatDate=(value:unknown)=>{if(!value)return "—";const date=new Date(String(value));return Number.isNaN(date.getTime())?String(value):date.toLocaleDateString("fa-IR",{year:"numeric",month:"short",day:"numeric"});};
const formatBytes=(value:unknown)=>`${(n(value)/GB).toLocaleString("fa-IR",{maximumFractionDigits:1})} GB`;
const tone=(value:unknown):"ok"|"warn"|"bad"|"violet"=>{const key=s(value).toLowerCase();return key==="active"?"ok":["expired","canceled"].includes(key)?"bad":"warn";};
const statusLabel=(value:unknown)=>{const key=s(value).toLowerCase();return key==="active"?"فعال":key==="pending"?"در انتظار":key==="expired"?"منقضی":key==="suspended"?"معلق":key==="canceled"?"لغوشده":s(value)||"نامشخص";};
const optionalPositive=(value:string)=>{const clean=value.trim();if(!clean)return undefined;const out=Number(clean);return Number.isFinite(out)&&out>0?out:undefined;};
const planProtocols=(plan:RuntimeRow|undefined)=>plan?protocolKeys.filter(key=>Boolean(plan[`enable_${key}`])):[];
const planTraffic=(plan:RuntimeRow|undefined)=>n(plan?.traffic_gb)>0?String(n(plan?.traffic_gb)):"";
const planDuration=(plan:RuntimeRow|undefined)=>n(plan?.duration_days)>0?String(Math.trunc(n(plan?.duration_days))):"";

function copy(value:string){if(value)void navigator.clipboard.writeText(value);}
function absoluteLink(value:string){if(!value)return "";if(/^https?:\/\//i.test(value))return value;if(typeof window!=="undefined")return new URL(value,window.location.origin).toString();return value;}
function downloadText(filename:string,content:string){const blob=new Blob([content],{type:"text/plain;charset=utf-8"});const url=URL.createObjectURL(blob);const anchor=document.createElement("a");anchor.href=url;anchor.download=filename||"config.txt";anchor.click();URL.revokeObjectURL(url);}

function Notice({error,ok}:{error:string;ok:string}){return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}

function Modal({title,sub,onClose,children,wide=false}:{title:string;sub?:string;onClose:()=>void;children:React.ReactNode;wide?:boolean}){
  return <div className="runtime-modal" role="dialog" aria-modal="true">
    <button className="runtime-modal-bg" aria-label="close" onClick={onClose}/>
    <div className={`runtime-modal-card ${wide?"manage-card":""}`}>
      <div className="card-head"><div><b>{title}</b>{sub&&<small>{sub}</small>}</div><button type="button" className="icon-button" onClick={onClose}>×</button></div>
      {children}
    </div>
  </div>;
}

type ModalKind="create"|"edit"|"extend"|"connect"|null;
type Draft={user_id:number;plan_id:number;traffic_gb:string;duration_days:string;device_limit:string;username:string;password:string;protocols:string[]};

export function LegacySubscriptionsRuntimePage(){
  const {pick}=useI18n();
  const [rows,setRows]=useState<RuntimeRow[]>([]);
  const [users,setUsers]=useState<AdminUser[]>([]);
  const [plans,setPlans]=useState<RuntimeRow[]>([]);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [query,setQuery]=useState("");
  const [status,setStatus]=useState<"all"|"active"|"expired"|"suspended"|"pending">("all");
  const [modal,setModal]=useState<ModalKind>(null);
  const [selected,setSelected]=useState<RuntimeRow|null>(null);
  const [connection,setConnection]=useState<RuntimeRow|null>(null);
  const [activeProtocol,setActiveProtocol]=useState("cisco");
  const [showPassword,setShowPassword]=useState(false);
  const [userSearch,setUserSearch]=useState("");
  const [extendDays,setExtendDays]=useState(30);
  const [extendTraffic,setExtendTraffic]=useState(10);
  const [linkModalId,setLinkModalId]=useState<number|null>(null);
  const [linkModalLink,setLinkModalLink]=useState("");
  const [linkModalLoading,setLinkModalLoading]=useState(false);
  const [linkModalError,setLinkModalError]=useState("");
  const [draft,setDraft]=useState<Draft>({user_id:0,plan_id:0,traffic_gb:"",duration_days:"",device_limit:"1",username:"",password:"",protocols:[]});

  const load=async(silent=false)=>{
    if(!silent)setLoading(true);
    setError("");
    try{
      let subscriptions:RuntimeRow[];
      try{subscriptions=await adminApi.subscriptionsV2();}catch{subscriptions=await adminApi.subscriptions();}
      const [userRows,planRows,nodeRows]=await Promise.all([adminApi.users(),adminApi.plans(),adminApi.nodes()]);
      setRows(subscriptions);setUsers(userRows);setPlans(planRows);setNodes(nodeRows);
      setSelected(current=>current?(subscriptions.find(item=>n(item.id)===n(current.id))||current):null);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{if(!silent)setLoading(false);}
  };

  useEffect(()=>{void load();const timer=window.setInterval(()=>void load(true),15000);return()=>window.clearInterval(timer);},[]);

  const userMap=useMemo(()=>new Map(users.map(user=>[user.id,user])),[users]);
  const planMap=useMemo(()=>new Map(plans.map(plan=>[n(plan.id),plan])),[plans]);
  const activePlan=planMap.get(draft.plan_id);
  const filtered=useMemo(()=>rows.filter(item=>{
    const q=query.trim().toLowerCase();const user=userMap.get(n(item.user_id));const plan=planMap.get(n(item.plan_id));
    const matches=!q||`${item.id??""} ${item.account_username??""} ${item.customer_name??""} ${item.customer_email??""} ${user?.full_name??""} ${user?.email??""} ${plan?.name??item.plan_name??""}`.toLowerCase().includes(q);
    return matches&&(status==="all"||s(item.status).toLowerCase()===status);
  }),[rows,query,status,userMap,planMap]);

  const stats=useMemo(()=>({total:rows.length,active:rows.filter(item=>s(item.status).toLowerCase()==="active").length,expired:rows.filter(item=>s(item.status).toLowerCase()==="expired").length,suspended:rows.filter(item=>s(item.status).toLowerCase()==="suspended").length}),[rows]);

  const act=async(key:string,label:string,fn:()=>Promise<unknown>,close=false)=>{
    if(busy)return;setBusy(key);setError("");setOk("");
    try{await fn();setOk(label);await load(true);if(close)setModal(null);}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}
  };

  const planDraft=(plan:RuntimeRow|undefined)=>({
    plan_id:n(plan?.id),
    traffic_gb:planTraffic(plan),
    duration_days:planDuration(plan),
    device_limit:String(Math.max(1,n(plan?.device_limit)||1)),
    protocols:planProtocols(plan)
  });

  const openCreate=()=>{
    const plan=plans.find(item=>item.is_active!==false)||plans[0];
    const user=users.find(item=>item.role!=="admin"&&item.is_active!==false)||users.find(item=>item.role!=="admin");
    setDraft({user_id:user?.id||0,...planDraft(plan),username:"",password:""});
    setUserSearch("");setSelected(null);setConnection(null);setModal("create");
  };

  const choosePlan=(id:number)=>{
    const plan=plans.find(item=>n(item.id)===id);
    setDraft(current=>({...current,...planDraft(plan),plan_id:id}));
  };

  const createSubscription=(event:FormEvent)=>{
    event.preventDefault();
    if(!draft.user_id||!draft.plan_id){setError(pick("کاربر و پلن را انتخاب کنید","Select user and plan"));return;}
    const traffic=optionalPositive(draft.traffic_gb);const duration=optionalPositive(draft.duration_days);const device=Math.max(1,Math.trunc(optionalPositive(draft.device_limit)||1));
    void act("create",pick("اشتراک ساخته و اکانت صادر شد","Subscription created and account provisioned"),async()=>{
      const created=await adminApi.createSubscriptionV2({user_id:draft.user_id,plan_id:draft.plan_id,node_ids:[],protocols:draft.protocols,...(traffic!==undefined?{traffic_gb:traffic}:{}),...(duration!==undefined?{duration_days:Math.trunc(duration)}:{}),device_limit:device,...(draft.username.trim()?{username:draft.username.trim()}:{}),...(draft.password.trim()?{password:draft.password.trim()}:{})});
      try{await adminApi.provisionSubscription(n(created.id));}catch{}
    },true);
  };

  const openEdit=(item:RuntimeRow)=>{
    setSelected(item);setConnection(null);const limit=n(item.traffic_limit_gb)||(n(item.traffic_limit_bytes)/GB);
    setDraft({user_id:n(item.user_id),plan_id:n(item.plan_id),traffic_gb:limit>0?String(limit):"",duration_days:n(item.activation_duration_days)>0?String(n(item.activation_duration_days)):"",device_limit:String(Math.max(1,n(item.device_limit)||n(planMap.get(n(item.plan_id))?.device_limit)||1)),username:s(item.account_username),password:"",protocols:strings(item.protocols)});
    setModal("edit");
  };

  const saveEdit=(event:FormEvent)=>{event.preventDefault();if(!selected)return;const traffic=optionalPositive(draft.traffic_gb);void act("edit",pick("اشتراک و اطلاعات اتصال بروزرسانی شد","Subscription and connection info updated"),()=>adminApi.editSubscription(n(selected.id),{plan_id:draft.plan_id,traffic_gb:traffic||0,node_ids:[],protocols:draft.protocols,account_username:draft.username.trim()||undefined,account_password:draft.password.trim()||undefined}),true);};
  const openExtend=(item:RuntimeRow)=>{setSelected(item);setExtendDays(30);setExtendTraffic(10);setModal("extend");};
  const saveExtend=()=>{if(!selected)return;void act("extend",pick("اشتراک تمدید شد","Subscription extended"),()=>legacyAdminApi.extendSubscription(n(selected.id),{add_days:extendDays,add_traffic_gb:extendTraffic}),true);};
  const toggleStatus=async(item:RuntimeRow)=>{const activate=s(item.status).toLowerCase()!=="active";await act(`status-${item.id}`,activate?pick("اشتراک فعال شد","Subscription activated"):pick("اشتراک معلق شد","Subscription suspended"),()=>adminApi.setSubscriptionActive(n(item.id),activate));};
  const remove=async(item:RuntimeRow)=>{const user=userMap.get(n(item.user_id));if(!window.confirm(pick(`اشتراک ${user?.full_name||user?.email||`#${item.id}`} حذف شود؟ این عملیات قابل بازگشت نیست.`,`Delete subscription #${item.id}? This cannot be undone.`)))return;await act(`delete-${item.id}`,pick("اشتراک حذف شد","Subscription deleted"),()=>adminApi.deleteSubscription(n(item.id)));};

  const loadConnection=async(item:RuntimeRow)=>{setSelected(item);setConnection(null);setModal("connect");setBusy("connection");setError("");try{const data=await adminApi.subscriptionConnectionInfo(n(item.id));setConnection(data);const first=(Array.isArray(data.credentials)?data.credentials:[])[0] as RuntimeRow|undefined;setActiveProtocol(s(first?.protocol)||"cisco");}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}};
  const openSubscriptionLink=async(item:RuntimeRow)=>{
    const id=n(item.id);if(!id)return;
    setLinkModalId(id);setLinkModalLink("");setLinkModalLoading(true);setLinkModalError("");
    try{const data=await adminApi.subscriptionConnectionInfo(id);setLinkModalLink(s(data.subscription_link));}
    catch(reason){setLinkModalError(reason instanceof Error?reason.message:String(reason));}
    finally{setLinkModalLoading(false);}
  };
  const closeSubscriptionLink=()=>{setLinkModalId(null);setLinkModalLink("");setLinkModalLoading(false);setLinkModalError("");};
  const provision=async()=>{if(!selected)return;setBusy("provision");setError("");try{await adminApi.provisionSubscription(n(selected.id));setConnection(await adminApi.subscriptionConnectionInfo(n(selected.id)));setOk(pick("اطلاعات اتصال ساخته شد","Connection info provisioned"));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}};
  const refreshPasswords=async()=>{if(!selected)return;setBusy("passwords");setError("");try{await adminApi.refreshSubscriptionPasswords(n(selected.id));setConnection(await adminApi.subscriptionConnectionInfo(n(selected.id)));setOk(pick("رمز Cisco/L2TP بازسازی شد","Cisco/L2TP password refreshed"));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}};

  const userMatches=users.filter(user=>user.role!=="admin"&&(!userSearch.trim()||`${user.full_name||""} ${user.email||""} ${user.phone||""}`.toLowerCase().includes(userSearch.trim().toLowerCase()))).slice(0,30);
  const credentials=connection&&Array.isArray(connection.credentials)?connection.credentials as RuntimeRow[]:[];
  const account=connection&&connection.account&&typeof connection.account==="object"?connection.account as RuntimeRow:null;
  const shareLink=absoluteLink(s(connection?.subscription_link));
  const selectedCredential=credentials.find(item=>s(item.protocol)===activeProtocol)||credentials[0]||null;
  const selectedItems=selectedCredential?list(selectedCredential.items):[];

  const trafficCell=(item:RuntimeRow)=>{const limit=n(item.traffic_limit_bytes);const used=n(item.traffic_used_bytes);if(limit<=0)return <div className="user-cell"><b dir="ltr">{formatBytes(used)} / {pick("نامحدود","Unlimited")}</b><small>∞</small></div>;const percent=Math.min(100,Math.round(used/limit*100));return <div className="user-cell"><b dir="ltr">{formatBytes(used)} / {formatBytes(limit)}</b><small>{percent.toLocaleString("fa-IR")}٪</small></div>;};
  const expiryCell=(item:RuntimeRow)=>{if(item.duration_unlimited===true)return pick("نامحدود","Unlimited");if(item.expires_at)return formatDate(item.expires_at);const days=n(item.activation_duration_days);if(days>0)return pick(`${days.toLocaleString("fa-IR")} روز از اولین اتصال`,`${days} days from first connection`);return "—";};

  return <Shell active="/admin/subscriptions"><div className="page legacy-subscriptions-page">
    <div className="page-head"><div><h1>{pick("اشتراک‌ها","Subscriptions")}</h1><small>{pick("مدیریت اشتراک، تمدید، وضعیت و سابلینک","Subscriptions, renewals, status and public links")}</small></div><button className="primary" onClick={openCreate}>＋ {pick("اشتراک جدید","New subscription")}</button></div>
    <Notice error={error} ok={ok}/>

    <div className="stats dashboard-stats"><Stat label={pick("کل اشتراک‌ها","Total subscriptions")} value={stats.total.toLocaleString("fa-IR")}/><Stat label={pick("اشتراک‌های فعال","Active")} value={stats.active.toLocaleString("fa-IR")}/><Stat label={pick("منقضی","Expired")} value={stats.expired.toLocaleString("fa-IR")}/><Stat label={pick("معلق","Suspended")} value={stats.suspended.toLocaleString("fa-IR")}/></div>

    <Card>
      <div className="runtime-toolbar"><label>⌕ <input value={query} onChange={event=>setQuery(event.target.value)} placeholder={pick("نام، ایمیل، نام کاربری یا کد اشتراک…","Name, email, username or subscription code…")}/></label><select value={status} onChange={event=>setStatus(event.target.value as typeof status)}><option value="all">{pick("همه","All")}</option><option value="active">{pick("فعال","Active")}</option><option value="expired">{pick("منقضی","Expired")}</option><option value="suspended">{pick("معلق","Suspended")}</option><option value="pending">{pick("در انتظار","Pending")}</option></select><button className="ghost" disabled={loading} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button></div>
      {loading&&rows.length===0?<div className="runtime-loading">…</div>:<div className="table"><table><thead><tr><th>{pick("کاربر","User")}</th><th>{pick("پلن","Plan")}</th><th>{pick("نام کاربری","Username")}</th><th>{pick("ترافیک","Traffic")}</th><th>{pick("ساخت","Created")}</th><th>{pick("انقضا","Expires")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map(item=>{const user=userMap.get(n(item.user_id));const plan=planMap.get(n(item.plan_id));return <tr key={n(item.id)}><td><div className="user-cell"><b>{user?.full_name||s(item.customer_name)||`#${item.user_id}`}</b><small dir="ltr">{user?.email||s(item.customer_email)||"—"}</small></div></td><td><div className="user-cell"><b>{s(item.plan_name)||s(plan?.name)||`#${item.plan_id}`}</b><small dir="ltr">MV-{n(item.id)}</small></div></td><td><div className="secret-row"><b dir="ltr">{s(item.account_username)||"—"}</b>{s(item.account_username)&&<button className="mini-btn" onClick={()=>copy(s(item.account_username))}>{pick("کپی","Copy")}</button>}</div></td><td>{trafficCell(item)}</td><td>{formatDate(item.created_at)}</td><td>{expiryCell(item)}</td><td><Badge tone={tone(item.status)}>{statusLabel(item.status)}</Badge></td><td><div className="row-actions"><button className="danger" disabled={!!busy} onClick={()=>void remove(item)}>{pick("حذف","Delete")}</button><button disabled={!!busy} onClick={()=>void toggleStatus(item)}>{s(item.status).toLowerCase()==="active"?pick("تعلیق","Suspend"):pick("فعال‌سازی","Activate")}</button><button onClick={()=>openEdit(item)}>{pick("ویرایش","Edit")}</button><button onClick={()=>openExtend(item)}>{pick("تمدید","Renew")}</button><button className="primary-soft" onClick={()=>void openSubscriptionLink(item)}>{pick("سابلینک","Sub-link")}</button></div></td></tr>;})}</tbody></table>{filtered.length===0&&<div className="runtime-empty">{pick("اشتراکی پیدا نشد","No subscriptions found")}</div>}</div>}
    </Card>

    {modal==="create"&&<Modal title={pick("ساخت اشتراک","Create subscription")} onClose={()=>!busy&&setModal(null)} wide>
      <form className="subscription-create-form" onSubmit={createSubscription}>
        <div className="setting-grid compact-create-grid">
          <label className="field"><span>{pick("جستجوی کاربر","User search")}</span><input value={userSearch} onChange={event=>setUserSearch(event.target.value)} placeholder={pick("نام، ایمیل یا موبایل…","Name, email or mobile…")}/></label>
          <label className="field"><span>{pick("کاربر","User")}</span><select value={draft.user_id} onChange={event=>setDraft(current=>({...current,user_id:Number(event.target.value)}))}><option value={0}>{pick("انتخاب کاربر","Select user")}</option>{userMatches.map(user=><option key={user.id} value={user.id}>{user.full_name||user.email||`#${user.id}`} · {user.phone||user.email||"—"}</option>)}</select></label>
          <label className="field"><span>{pick("پلن","Plan")}</span><select value={draft.plan_id} onChange={event=>choosePlan(Number(event.target.value))}><option value={0}>{pick("انتخاب پلن","Select plan")}</option>{plans.filter(plan=>plan.is_active!==false).map(plan=><option key={n(plan.id)} value={n(plan.id)}>{s(plan.name)||`#${plan.id}`}</option>)}</select></label>
        </div>

        {activePlan&&<div className="subscription-plan-summary"><b>{s(activePlan.name)}</b><span>{n(activePlan.traffic_gb)>0?`${n(activePlan.traffic_gb).toLocaleString("fa-IR")} GB`:pick("حجم نامحدود","Unlimited traffic")}</span><span>{n(activePlan.duration_days)>0?pick(`${n(activePlan.duration_days).toLocaleString("fa-IR")} روز`,`${n(activePlan.duration_days)} days`):pick("زمان نامحدود","Unlimited duration")}</span><span>{pick(`${Math.max(1,n(activePlan.device_limit)||1).toLocaleString("fa-IR")} اتصال`,`${Math.max(1,n(activePlan.device_limit)||1)} devices`)}</span><span>{planProtocols(activePlan).map(key=>protocolLabels[key]).join(" · ")||"—"}</span></div>}

        <div className="setting-grid compact-create-grid">
          <label className="field"><span>{pick("حجم GB","Traffic GB")}</span><input inputMode="decimal" type="number" min={0.1} step="0.1" value={draft.traffic_gb} onChange={event=>setDraft(current=>({...current,traffic_gb:event.target.value}))} placeholder={pick("خالی = نامحدود","empty = unlimited")}/><small>{pick("از پلن پر می‌شود؛ برای نامحدود پاکش کنید","Filled from plan; clear for unlimited")}</small></label>
          <label className="field"><span>{pick("مدت روز","Duration days")}</span><input inputMode="numeric" type="number" min={1} step={1} value={draft.duration_days} onChange={event=>setDraft(current=>({...current,duration_days:event.target.value}))} placeholder={pick("خالی = نامحدود","empty = unlimited")}/><small>{pick("از پلن پر می‌شود؛ برای نامحدود پاکش کنید","Filled from plan; clear for unlimited")}</small></label>
          <label className="field"><span>{pick("اتصال همزمان","Concurrent devices")}</span><input inputMode="numeric" type="number" min={1} step={1} value={draft.device_limit} onChange={event=>setDraft(current=>({...current,device_limit:event.target.value}))}/></label>
          <label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" autoComplete="off" value={draft.username} onChange={event=>setDraft(current=>({...current,username:event.target.value}))} placeholder={pick("خالی = خودکار","empty = automatic")}/></label>
          <label className="field"><span>{pick("رمز عبور","Password")}</span><input dir="ltr" autoComplete="new-password" value={draft.password} onChange={event=>setDraft(current=>({...current,password:event.target.value}))} placeholder={pick("خالی = خودکار","empty = automatic")}/></label>
        </div>
        <div className="modalActions"><button type="button" className="ghost" onClick={()=>setModal(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy==="create"||!draft.user_id||!draft.plan_id}>{busy==="create"?pick("در حال ساخت…","Creating…"):pick("ساخت و صدور اکانت","Create & provision")}</button></div>
      </form>
    </Modal>}

    {modal==="edit"&&selected&&<Modal title={pick("ویرایش اشتراک","Edit subscription")} sub={`MV-${n(selected.id)}`} onClose={()=>!busy&&setModal(null)} wide>
      <form onSubmit={saveEdit}><div className="setting-grid"><label className="field"><span>{pick("پلن","Plan")}</span><select value={draft.plan_id} onChange={event=>setDraft(current=>({...current,plan_id:Number(event.target.value)}))}>{plans.map(plan=><option key={n(plan.id)} value={n(plan.id)}>{s(plan.name)||`#${plan.id}`}</option>)}</select></label><label className="field"><span>{pick("حجم کل GB","Total traffic GB")}</span><input type="number" min={0} step="0.1" value={draft.traffic_gb} onChange={event=>setDraft(current=>({...current,traffic_gb:event.target.value}))} placeholder={pick("خالی = نامحدود","empty = unlimited")}/></label><label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" value={draft.username} onChange={event=>setDraft(current=>({...current,username:event.target.value}))}/></label><label className="field"><span>{pick("رمز جدید","New password")}</span><input dir="ltr" autoComplete="new-password" value={draft.password} onChange={event=>setDraft(current=>({...current,password:event.target.value}))} placeholder={pick("خالی = بدون تغییر","empty = unchanged")}/></label></div><div className="manage-section-head"><div><b>{pick("پروتکل‌ها","Protocols")}</b><small>{draft.protocols.length.toLocaleString("fa-IR")} {pick("انتخاب","selected")}</small></div></div><div className="protocol-toggle-grid">{protocolKeys.map(key=>{const supported=nodes.some(node=>node.status==="online"&&Boolean((node as unknown as RuntimeRow)[`enable_${key}`]));const checked=draft.protocols.includes(key);return <label key={key} className="toggle module-toggle compact-toggle"><span>{protocolLabels[key]}<small>{supported?pick("قابل استفاده","Available"):pick("روی سرور آنلاین فعال نیست","Not enabled on an online server")}</small></span><input type="checkbox" disabled={!supported} checked={checked} onChange={event=>setDraft(current=>({...current,protocols:event.target.checked?[...new Set([...current.protocols,key])]:current.protocols.filter(item=>item!==key)}))}/><i/></label>;})}</div><div className="modalActions"><button type="button" className="ghost" onClick={()=>setModal(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy==="edit"||!draft.plan_id||!draft.protocols.length}>{busy==="edit"?"…":pick("ذخیره تغییرات","Save changes")}</button></div></form>
    </Modal>}

    {modal==="extend"&&selected&&<Modal title={pick("تمدید اشتراک","Renew subscription")} sub={`MV-${n(selected.id)} · ${expiryCell(selected)}`} onClose={()=>!busy&&setModal(null)}><div className="setting-grid"><label className="field"><span>{pick("روز اضافه","Add days")}</span><input type="number" min={0} value={extendDays} onChange={event=>setExtendDays(Math.max(0,Number(event.target.value)||0))}/></label><label className="field"><span>{pick("حجم اضافه GB","Add traffic GB")}</span><input type="number" min={0} step="0.1" value={extendTraffic} onChange={event=>setExtendTraffic(Math.max(0,Number(event.target.value)||0))}/></label></div><div className="modalActions"><button className="ghost" onClick={()=>setModal(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy==="extend"||(!extendDays&&!extendTraffic)} onClick={saveExtend}>{busy==="extend"?"…":pick("اعمال تمدید","Apply renewal")}</button></div></Modal>}

    {modal==="connect"&&selected&&<Modal title={pick("اطلاعات اتصال","Connection information")} sub={`MV-${n(selected.id)}`} onClose={()=>setModal(null)} wide>
      <Notice error={error} ok={ok}/>
      {busy==="connection"?<div className="runtime-loading">…</div>:<>
        <div className="stats dashboard-stats modal-stats"><Stat label={pick("نام کاربری","Username")} value={s(account?.username||selected.account_username)||"—"}/><Stat label={pick("پروتکل‌ها","Protocols")} value={String(credentials.length)}/><Stat label={pick("سرورها","Servers")} value={String(credentials.reduce((sum,item)=>sum+list(item.items).length,0))}/></div>
        <div className="manage-actions"><button className="primary" disabled={!!busy} onClick={()=>void provision()}>{busy==="provision"?"…":pick("ساخت/بازسازی اتصال","Provision connection")}</button><button className="ghost" disabled={!!busy} onClick={()=>void refreshPasswords()}>{busy==="passwords"?"…":pick("رمز جدید Cisco/L2TP","Refresh Cisco/L2TP password")}</button>{shareLink&&<><button className="ghost" onClick={()=>copy(shareLink)}>{pick("کپی سابلینک","Copy sub-link")}</button><a className="ghost" href={shareLink} target="_blank" rel="noreferrer">{pick("صفحه اتصال","Connection page")}</a></>}</div>
        <div className="setting-grid"><div className="setting-box"><small>{pick("نام کاربری اکانت","Account username")}</small><div className="secret-row"><b dir="ltr">{s(account?.username||selected.account_username)||"—"}</b>{s(account?.username||selected.account_username)&&<button className="mini-btn" onClick={()=>copy(s(account?.username||selected.account_username))}>{pick("کپی","Copy")}</button>}</div></div><div className="setting-box"><small>{pick("رمز عبور اکانت","Account password")}</small><div className="secret-row"><b dir="ltr">{showPassword?s(account?.password)||"—":"••••••••"}</b><button className="mini-btn" onClick={()=>setShowPassword(value=>!value)}>{showPassword?pick("مخفی","Hide"):pick("نمایش","Show")}</button>{s(account?.password)&&<button className="mini-btn" onClick={()=>copy(s(account?.password))}>{pick("کپی","Copy")}</button>}</div></div></div>
        {credentials.length===0?<div className="runtime-empty">{pick("هنوز اطلاعات اتصال ساخته نشده است. «ساخت/بازسازی اتصال» را بزنید.","Connection data has not been provisioned yet.")}</div>:<><div className="runtime-tabs">{credentials.map(item=><button type="button" key={s(item.protocol)} className={activeProtocol===s(item.protocol)?"active":""} onClick={()=>setActiveProtocol(s(item.protocol))}>{protocolLabels[s(item.protocol)]||s(item.protocol)}</button>)}</div><div className="manage-card-section"><div className="manage-section-head"><div><b>{protocolLabels[s(selectedCredential?.protocol)]||s(selectedCredential?.protocol)}</b><small>{selectedItems.length.toLocaleString("fa-IR")} {pick("سرور قابل استفاده","available servers")}</small></div></div><div className="protocol-toggle-grid">{selectedItems.map((item,index)=>{const protocol=s(selectedCredential?.protocol);const server=s(item.server||item.server_ip);const port=s(item.port||item.ports);const username=s(item.username||selectedCredential?.username||account?.username);const password=s(item.password||account?.password);const config=s(item.config);const uri=s(item.uri);const psk=s(item.psk);const filename=s(item.filename)||`${protocol}-${n(selected.id)}-${index+1}.${protocol==="openvpn"?"ovpn":protocol==="wireguard"?"conf":"txt"}`;return <div className="setting-box" key={`${protocol}-${n(item.node_id)}-${index}`}><div className="card-head"><div><b>{s(item.node)||`${pick("سرور","Server")} ${index+1}`}</b><small dir="ltr">{server}{port?`:${port}`:""}</small></div><Badge tone="ok">{pick("آماده","Ready")}</Badge></div><div className="setting-grid">{server&&<div><small>{pick("سرور","Server")}</small><div className="secret-row"><code dir="ltr">{server}</code><button className="mini-btn" onClick={()=>copy(server)}>{pick("کپی","Copy")}</button></div></div>}{port&&<div><small>{pick("پورت / Transport","Port / Transport")}</small><b dir="ltr">{port}{s(item.transport)?` · ${s(item.transport)}`:""}</b></div>}{username&&<div><small>{pick("نام کاربری","Username")}</small><div className="secret-row"><code dir="ltr">{username}</code><button className="mini-btn" onClick={()=>copy(username)}>{pick("کپی","Copy")}</button></div></div>}{password&&<div><small>{pick("رمز عبور","Password")}</small><div className="secret-row"><code dir="ltr">{showPassword?password:"••••••••"}</code><button className="mini-btn" onClick={()=>copy(password)}>{pick("کپی","Copy")}</button></div></div>}{psk&&<div><small>PSK</small><div className="secret-row"><code dir="ltr">{psk}</code><button className="mini-btn" onClick={()=>copy(psk)}>{pick("کپی","Copy")}</button></div></div>}{s(item.address)&&<div><small>{pick("آدرس WireGuard","WireGuard address")}</small><code dir="ltr">{s(item.address)}</code></div>}{s(item.uuid)&&<div><small>UUID</small><div className="secret-row"><code dir="ltr">{s(item.uuid)}</code><button className="mini-btn" onClick={()=>copy(s(item.uuid))}>{pick("کپی","Copy")}</button></div></div>}</div>{(config||uri)&&<div className="manage-actions">{config&&<><button className="primary-soft" onClick={()=>copy(config)}>{pick("کپی کانفیگ","Copy config")}</button><button className="ghost" onClick={()=>downloadText(filename,config)}>{pick("دانلود فایل","Download file")}</button></>}{uri&&<button className="primary-soft" onClick={()=>copy(uri)}>{pick("کپی لینک V2Ray","Copy V2Ray URI")}</button>}</div>}{(protocol==="wireguard"&&config||protocol==="v2ray"&&uri)&&<div style={{display:"grid",placeItems:"center",marginTop:12}}><div style={{background:"white",padding:12,borderRadius:14}}><QRCodeSVG value={protocol==="wireguard"?config:uri} size={160}/></div></div>}</div>;})}</div></div></>}
      </>}
    </Modal>}

    <SubscriptionLinkDeliveryModal
      open={linkModalId!==null}
      link={linkModalLink}
      reference={linkModalId?`MV-${linkModalId}`:""}
      loading={linkModalLoading}
      error={linkModalError}
      onClose={closeSubscriptionLink}
    />
  </div></Shell>;
}
