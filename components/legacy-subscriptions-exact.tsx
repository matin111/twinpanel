"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {QRCodeSVG} from "qrcode.react";
import {Badge,Card,Shell,Stat} from "./ui";
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

type ModalKind="create"|"edit"|"extend"|"sublink"|"connect"|null;

type Draft={
  user_id:number;
  plan_id:number;
  traffic_gb:number;
  duration_days:number;
  username:string;
  password:string;
  protocols:string[];
};

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
  const [draft,setDraft]=useState<Draft>({user_id:0,plan_id:0,traffic_gb:100,duration_days:30,username:"",password:"",protocols:[]});

  const load=async(silent=false)=>{
    if(!silent)setLoading(true);
    setError("");
    try{
      const [subscriptions,userRows,planRows,nodeRows]=await Promise.all([adminApi.subscriptions(),adminApi.users(),adminApi.plans(),adminApi.nodes()]);
      setRows(subscriptions);
      setUsers(userRows);
      setPlans(planRows);
      setNodes(nodeRows);
      setSelected(current=>current?(subscriptions.find(item=>n(item.id)===n(current.id))||current):null);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{if(!silent)setLoading(false);}
  };

  useEffect(()=>{void load();const timer=window.setInterval(()=>void load(true),15000);return()=>window.clearInterval(timer);},[]);

  const userMap=useMemo(()=>new Map(users.map(user=>[user.id,user])),[users]);
  const planMap=useMemo(()=>new Map(plans.map(plan=>[n(plan.id),plan])),[plans]);
  const filtered=useMemo(()=>rows.filter(item=>{
    const q=query.trim().toLowerCase();
    const user=userMap.get(n(item.user_id));
    const plan=planMap.get(n(item.plan_id));
    const matches=!q||`${item.id??""} ${item.account_username??""} ${item.customer_name??""} ${item.customer_email??""} ${user?.full_name??""} ${user?.email??""} ${plan?.name??item.plan_name??""}`.toLowerCase().includes(q);
    return matches&&(status==="all"||s(item.status).toLowerCase()===status);
  }),[rows,query,status,userMap,planMap]);

  const stats=useMemo(()=>({
    total:rows.length,
    active:rows.filter(item=>s(item.status).toLowerCase()==="active").length,
    expired:rows.filter(item=>s(item.status).toLowerCase()==="expired").length,
    suspended:rows.filter(item=>s(item.status).toLowerCase()==="suspended").length
  }),[rows]);

  const act=async(key:string,label:string,fn:()=>Promise<unknown>,close=false)=>{
    if(busy)return;
    setBusy(key);setError("");setOk("");
    try{
      await fn();
      setOk(label);
      await load(true);
      if(close)setModal(null);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const openCreate=()=>{
    const plan=plans.find(item=>item.is_active!==false)||plans[0];
    const user=users.find(item=>item.role!=="admin"&&item.is_active!==false)||users.find(item=>item.role!=="admin");
    setDraft({user_id:user?.id||0,plan_id:n(plan?.id),traffic_gb:n(plan?.traffic_gb)||100,duration_days:n(plan?.duration_days)||30,username:"",password:"",protocols:[]});
    setUserSearch("");setSelected(null);setConnection(null);setModal("create");
  };

  const choosePlan=(id:number)=>{
    const plan=plans.find(item=>n(item.id)===id);
    setDraft(current=>({...current,plan_id:id,traffic_gb:n(plan?.traffic_gb)||current.traffic_gb,duration_days:n(plan?.duration_days)||current.duration_days}));
  };

  const createSubscription=(event:FormEvent)=>{
    event.preventDefault();
    if(!draft.user_id||!draft.plan_id){setError(pick("کاربر و پلن را انتخاب کنید","Select user and plan"));return;}
    void act("create",pick("اشتراک ساخته و اکانت صادر شد","Subscription created and account provisioned"),async()=>{
      const created=await adminApi.createSubscription({user_id:draft.user_id,plan_id:draft.plan_id,node_ids:[],protocols:[],traffic_gb:draft.traffic_gb,duration_days:draft.duration_days,...(draft.username.trim()?{username:draft.username.trim()}:{}),...(draft.password.trim()?{password:draft.password.trim()}:{})});
      try{await adminApi.provisionSubscription(n(created.id));}catch(reason){setOk(pick("اشتراک ساخته شد؛ صدور اتصال کامل نشد","Subscription created; connection provisioning needs attention"));}
    },true);
  };

  const openEdit=(item:RuntimeRow)=>{
    setSelected(item);setConnection(null);
    setDraft({
      user_id:n(item.user_id),
      plan_id:n(item.plan_id),
      traffic_gb:n(item.traffic_limit_gb)||(n(item.traffic_limit_bytes)/GB),
      duration_days:30,
      username:s(item.account_username),
      password:"",
      protocols:strings(item.protocols)
    });
    setModal("edit");
  };

  const saveEdit=(event:FormEvent)=>{
    event.preventDefault();if(!selected)return;
    void act("edit",pick("اشتراک و اطلاعات اتصال بروزرسانی شد","Subscription and connection info updated"),()=>adminApi.editSubscription(n(selected.id),{plan_id:draft.plan_id,traffic_gb:draft.traffic_gb,node_ids:[],protocols:draft.protocols,account_username:draft.username.trim()||undefined,account_password:draft.password.trim()||undefined}),true);
  };

  const openExtend=(item:RuntimeRow)=>{setSelected(item);setExtendDays(30);setExtendTraffic(10);setModal("extend");};
  const saveExtend=()=>{if(!selected)return;void act("extend",pick("اشتراک تمدید شد","Subscription extended"),()=>legacyAdminApi.extendSubscription(n(selected.id),{add_days:extendDays,add_traffic_gb:extendTraffic}),true);};

  const toggleStatus=async(item:RuntimeRow)=>{
    const activate=s(item.status).toLowerCase()!=="active";
    await act(`status-${item.id}`,activate?pick("اشتراک فعال شد","Subscription activated"):pick("اشتراک معلق شد","Subscription suspended"),()=>adminApi.setSubscriptionActive(n(item.id),activate));
  };

  const remove=async(item:RuntimeRow)=>{
    const user=userMap.get(n(item.user_id));
    if(!window.confirm(pick(`اشتراک ${user?.full_name||user?.email||`#${item.id}`} حذف شود؟ این عملیات قابل بازگشت نیست.`,`Delete subscription #${item.id}? This cannot be undone.`)))return;
    await act(`delete-${item.id}`,pick("اشتراک حذف شد","Subscription deleted"),()=>adminApi.deleteSubscription(n(item.id)));
  };

  const loadConnection=async(item:RuntimeRow,kind:"connect"|"sublink")=>{
    setSelected(item);setConnection(null);setModal(kind);setBusy("connection");setError("");
    try{
      const data=await adminApi.subscriptionConnectionInfo(n(item.id));
      setConnection(data);
      const first=(Array.isArray(data.credentials)?data.credentials:[])[0] as RuntimeRow|undefined;
      setActiveProtocol(s(first?.protocol)||"cisco");
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const provision=async()=>{if(!selected)return;setBusy("provision");setError("");try{await adminApi.provisionSubscription(n(selected.id));setConnection(await adminApi.subscriptionConnectionInfo(n(selected.id)));setOk(pick("اطلاعات اتصال ساخته شد","Connection info provisioned"));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}};
  const refreshPasswords=async()=>{if(!selected)return;setBusy("passwords");setError("");try{await adminApi.refreshSubscriptionPasswords(n(selected.id));setConnection(await adminApi.subscriptionConnectionInfo(n(selected.id)));setOk(pick("رمز Cisco/L2TP بازسازی شد","Cisco/L2TP password refreshed"));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy("");}};

  const userMatches=users.filter(user=>user.role!=="admin"&&(!userSearch.trim()||`${user.full_name||""} ${user.email||""} ${user.phone||""}`.toLowerCase().includes(userSearch.trim().toLowerCase()))).slice(0,12);
  const globalNodes=nodes.filter(node=>node.status!=="retired");
  const credentials=connection&&Array.isArray(connection.credentials)?connection.credentials as RuntimeRow[]:[];
  const account=connection&&connection.account&&typeof connection.account==="object"?connection.account as RuntimeRow:null;
  const shareLink=absoluteLink(s(connection?.subscription_link));
  const selectedCredential=credentials.find(item=>s(item.protocol)===activeProtocol)||credentials[0]||null;
  const selectedItems=selectedCredential?list(selectedCredential.items):[];

  return <Shell active="/admin/subscriptions"><div className="page legacy-subscriptions-page">
    <div className="page-head"><div><h1>{pick("اشتراک‌ها","Subscriptions")}</h1><small>{pick("مدیریت اشتراک، تمدید، وضعیت، سابلینک و اتصال","Subscriptions, renewals, status, public links and connection delivery")}</small></div><button className="primary" onClick={openCreate}>＋ {pick("اشتراک جدید","New subscription")}</button></div>
    <Notice error={error} ok={ok}/>

    <div className="stats dashboard-stats">
      <Stat label={pick("کل اشتراک‌ها","Total subscriptions")} value={stats.total.toLocaleString("fa-IR")}/>
      <Stat label={pick("اشتراک‌های فعال","Active")} value={stats.active.toLocaleString("fa-IR")}/>
      <Stat label={pick("منقضی","Expired")} value={stats.expired.toLocaleString("fa-IR")}/>
      <Stat label={pick("معلق","Suspended")} value={stats.suspended.toLocaleString("fa-IR")}/>
    </div>

    <Card>
      <div className="runtime-toolbar">
        <label>⌕ <input value={query} onChange={event=>setQuery(event.target.value)} placeholder={pick("نام، ایمیل، نام کاربری یا کد اشتراک…","Name, email, username or subscription code…")}/></label>
        <select value={status} onChange={event=>setStatus(event.target.value as typeof status)}><option value="all">{pick("همه","All")}</option><option value="active">{pick("فعال","Active")}</option><option value="expired">{pick("منقضی","Expired")}</option><option value="suspended">{pick("معلق","Suspended")}</option><option value="pending">{pick("در انتظار","Pending")}</option></select>
        <button className="ghost" disabled={loading} onClick={()=>void load()}>{loading?"…":pick("بروزرسانی","Refresh")}</button>
      </div>

      {loading&&rows.length===0?<div className="runtime-loading">…</div>:<div className="table"><table><thead><tr><th>{pick("کاربر","User")}</th><th>{pick("پلن","Plan")}</th><th>{pick("نام کاربری","Username")}</th><th>{pick("ترافیک","Traffic")}</th><th>{pick("ساخت","Created")}</th><th>{pick("انقضا","Expires")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map(item=>{
        const user=userMap.get(n(item.user_id));const plan=planMap.get(n(item.plan_id));const limit=n(item.traffic_limit_bytes);const used=n(item.traffic_used_bytes);const percent=limit>0?Math.min(100,Math.round(used/limit*100)):0;
        return <tr key={n(item.id)}>
          <td><div className="user-cell"><b>{user?.full_name||s(item.customer_name)||`#${item.user_id}`}</b><small dir="ltr">{user?.email||s(item.customer_email)||"—"}</small></div></td>
          <td><div className="user-cell"><b>{s(item.plan_name)||s(plan?.name)||`#${item.plan_id}`}</b><small dir="ltr">MV-{n(item.id)}</small></div></td>
          <td><div className="secret-row"><b dir="ltr">{s(item.account_username)||"—"}</b>{s(item.account_username)&&<button className="mini-btn" onClick={()=>copy(s(item.account_username))}>{pick("کپی","Copy")}</button>}</div></td>
          <td><div className="user-cell"><b dir="ltr">{formatBytes(used)} / {formatBytes(limit)}</b><small>{percent.toLocaleString("fa-IR")}٪</small></div></td>
          <td>{formatDate(item.created_at)}</td><td>{formatDate(item.expires_at)}</td>
          <td><Badge tone={tone(item.status)}>{statusLabel(item.status)}</Badge></td>
          <td><div className="row-actions"><button className="danger" disabled={!!busy} onClick={()=>void remove(item)}>{pick("حذف","Delete")}</button><button disabled={!!busy} onClick={()=>void toggleStatus(item)}>{s(item.status).toLowerCase()==="active"?pick("تعلیق","Suspend"):pick("فعال‌سازی","Activate")}</button><button onClick={()=>openEdit(item)}>{pick("ویرایش","Edit")}</button><button onClick={()=>openExtend(item)}>{pick("تمدید","Renew")}</button><button className="primary-soft" onClick={()=>void loadConnection(item,"sublink")}>{pick("سابلینک","Sub-link")}</button><button className="primary-soft" onClick={()=>void loadConnection(item,"connect")}>{pick("اتصال","Connect")}</button></div></td>
        </tr>;
      })}</tbody></table>{filtered.length===0&&<div className="runtime-empty">{pick("اشتراکی پیدا نشد","No subscriptions found")}</div>}</div>}
    </Card>

    {modal==="create"&&<Modal title={pick("ساخت اشتراک","Create subscription")} sub={pick("ساخت و صدور اکانت در یک مرحله","Create and provision the account in one flow")} onClose={()=>!busy&&setModal(null)} wide>
      <form onSubmit={createSubscription}>
        <div className="manage-section-head"><div><b>{pick("کاربر","User")}</b><small>{pick("نام، ایمیل یا موبایل را جستجو کنید","Search name, email or mobile")}</small></div></div>
        <label className="field"><span>{pick("جستجوی کاربر","User search")}</span><input value={userSearch} onChange={event=>setUserSearch(event.target.value)} placeholder={pick("جستجو…","Search…")}/></label>
        <div className="protocol-toggle-grid">{userMatches.map(user=><button type="button" key={user.id} className={`ghost ${draft.user_id===user.id?"active":""}`} onClick={()=>setDraft(current=>({...current,user_id:user.id}))}><b>{user.full_name||user.email||`#${user.id}`}</b><small dir="ltr">{user.phone||user.email||"—"}</small>{draft.user_id===user.id&&<em>✓</em>}</button>)}</div>

        <div className="setting-grid">
          <label className="field"><span>{pick("پلن","Plan")}</span><select value={draft.plan_id} onChange={event=>choosePlan(Number(event.target.value))}>{plans.filter(plan=>plan.is_active!==false).map(plan=><option key={n(plan.id)} value={n(plan.id)}>{s(plan.name)||`#${plan.id}`}</option>)}</select></label>
          <label className="field"><span>{pick("حجم GB","Traffic GB")}</span><input type="number" min={1} step="0.1" value={draft.traffic_gb} onChange={event=>setDraft(current=>({...current,traffic_gb:Math.max(1,Number(event.target.value)||1)}))}/></label>
          <label className="field"><span>{pick("مدت روز","Duration days")}</span><input type="number" min={1} value={draft.duration_days} onChange={event=>setDraft(current=>({...current,duration_days:Math.max(1,Number(event.target.value)||1)}))}/></label>
          <label className="field"><span>{pick("نام کاربری اکانت","Account username")}</span><input dir="ltr" autoComplete="off" value={draft.username} onChange={event=>setDraft(current=>({...current,username:event.target.value}))} placeholder={pick("خالی = خودکار","empty = automatic")}/></label>
          <label className="field"><span>{pick("رمز عبور اکانت","Account password")}</span><input dir="ltr" autoComplete="new-password" value={draft.password} onChange={event=>setDraft(current=>({...current,password:event.target.value}))} placeholder={pick("خالی = خودکار","empty = automatic")}/></label>
        </div>

        <div className="manage-section-head"><div><b>{pick("سرورهای اشتراک","Subscription servers")}</b><small>{pick("تمام نودهای ثبت‌شده سراسری هستند؛ Backend پروتکل‌های مجاز پلن را خودکار انتخاب می‌کند","All registered nodes are global; backend automatically selects plan protocols")}</small></div><Badge tone="violet">{globalNodes.length.toLocaleString("fa-IR")} {pick("سرور","servers")}</Badge></div>
        <div className="protocol-toggle-grid">{globalNodes.map(node=><div className="setting-box" key={node.id}><b>{node.name}</b><small dir="ltr">{node.public_ip||"—"}</small><Badge tone={node.status==="online"?"ok":"bad"}>{node.status==="online"?pick("آنلاین","Online"):pick("آفلاین","Offline")}</Badge></div>)}</div>
        <div className="modalActions"><button type="button" className="ghost" onClick={()=>setModal(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy==="create"||!draft.user_id||!draft.plan_id}>{busy==="create"?pick("در حال ساخت…","Creating…"):pick("ساخت و صدور اکانت","Create & provision")}</button></div>
      </form>
    </Modal>}

    {modal==="edit"&&selected&&<Modal title={pick("ویرایش اشتراک","Edit subscription")} sub={`MV-${n(selected.id)}`} onClose={()=>!busy&&setModal(null)} wide>
      <form onSubmit={saveEdit}>
        <div className="setting-grid">
          <label className="field"><span>{pick("پلن","Plan")}</span><select value={draft.plan_id} onChange={event=>setDraft(current=>({...current,plan_id:Number(event.target.value)}))}>{plans.map(plan=><option key={n(plan.id)} value={n(plan.id)}>{s(plan.name)||`#${plan.id}`}</option>)}</select></label>
          <label className="field"><span>{pick("حجم کل GB","Total traffic GB")}</span><input type="number" min={1} step="0.1" value={draft.traffic_gb} onChange={event=>setDraft(current=>({...current,traffic_gb:Math.max(1,Number(event.target.value)||1)}))}/></label>
          <label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" value={draft.username} onChange={event=>setDraft(current=>({...current,username:event.target.value}))}/></label>
          <label className="field"><span>{pick("رمز جدید","New password")}</span><input dir="ltr" autoComplete="new-password" value={draft.password} onChange={event=>setDraft(current=>({...current,password:event.target.value}))} placeholder={pick("خالی = بدون تغییر","empty = unchanged")}/></label>
        </div>
        <div className="manage-section-head"><div><b>{pick("پروتکل‌ها","Protocols")}</b><small>{draft.protocols.length.toLocaleString("fa-IR")} {pick("انتخاب","selected")}</small></div></div>
        <div className="protocol-toggle-grid">{protocolKeys.map(key=>{const supported=nodes.some(node=>node.status==="online"&&Boolean((node as unknown as RuntimeRow)[`enable_${key}`]));const checked=draft.protocols.includes(key);return <label key={key} className="toggle module-toggle compact-toggle"><span>{protocolLabels[key]}<small>{supported?pick("قابل استفاده","Available"):pick("روی سرور آنلاین فعال نیست","Not enabled on an online server")}</small></span><input type="checkbox" disabled={!supported} checked={checked} onChange={event=>setDraft(current=>({...current,protocols:event.target.checked?[...new Set([...current.protocols,key])]:current.protocols.filter(item=>item!==key)}))}/><i/></label>;})}</div>
        <div className="modalActions"><button type="button" className="ghost" onClick={()=>setModal(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy==="edit"||!draft.plan_id||!draft.protocols.length}>{busy==="edit"?"…":pick("ذخیره تغییرات","Save changes")}</button></div>
      </form>
    </Modal>}

    {modal==="extend"&&selected&&<Modal title={pick("تمدید اشتراک","Renew subscription")} sub={`MV-${n(selected.id)} · ${formatDate(selected.expires_at)}`} onClose={()=>!busy&&setModal(null)}>
      <div className="setting-grid"><label className="field"><span>{pick("روز اضافه","Add days")}</span><input type="number" min={0} value={extendDays} onChange={event=>setExtendDays(Math.max(0,Number(event.target.value)||0))}/></label><label className="field"><span>{pick("حجم اضافه GB","Add traffic GB")}</span><input type="number" min={0} step="0.1" value={extendTraffic} onChange={event=>setExtendTraffic(Math.max(0,Number(event.target.value)||0))}/></label></div>
      <div className="modalActions"><button className="ghost" onClick={()=>setModal(null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy==="extend"||(!extendDays&&!extendTraffic)} onClick={saveExtend}>{busy==="extend"?"…":pick("اعمال تمدید","Apply renewal")}</button></div>
    </Modal>}

    {modal==="sublink"&&selected&&<Modal title={pick("لینک اشتراک","Subscription link")} sub={`MV-${n(selected.id)}`} onClose={()=>setModal(null)}>
      <Notice error={error} ok={ok}/>
      {busy==="connection"?<div className="runtime-loading">…</div>:shareLink?<div className="setting-grid"><div className="setting-box" style={{display:"grid",placeItems:"center",gap:12}}><small>{pick("کد QR","QR code")}</small><div style={{background:"white",padding:14,borderRadius:16}}><QRCodeSVG value={shareLink} size={190}/></div></div><div className="setting-box"><small>{pick("لینک اشتراک","Subscription link")}</small><code dir="ltr" style={{wordBreak:"break-all"}}>{shareLink}</code><div className="row-actions"><button className="primary-soft" onClick={()=>copy(shareLink)}>{pick("کپی","Copy")}</button><a className="primary" href={shareLink} target="_blank" rel="noreferrer">{pick("باز کردن","Open")}</a></div></div></div>:<div className="runtime-empty">{pick("لینک اشتراک موجود نیست","Subscription link is not available")}</div>}
    </Modal>}

    {modal==="connect"&&selected&&<Modal title={pick("اطلاعات اتصال","Connection information")} sub={`MV-${n(selected.id)}`} onClose={()=>setModal(null)} wide>
      <Notice error={error} ok={ok}/>
      {busy==="connection"?<div className="runtime-loading">…</div>:<>
        <div className="stats dashboard-stats modal-stats"><Stat label={pick("نام کاربری","Username")} value={s(account?.username||selected.account_username)||"—"}/><Stat label={pick("پروتکل‌ها","Protocols")} value={String(credentials.length)}/><Stat label={pick("سرورها","Servers")} value={String(credentials.reduce((sum,item)=>sum+list(item.items).length,0))}/></div>
        <div className="manage-actions"><button className="primary" disabled={!!busy} onClick={()=>void provision()}>{busy==="provision"?"…":pick("ساخت/بازسازی اتصال","Provision connection")}</button><button className="ghost" disabled={!!busy} onClick={()=>void refreshPasswords()}>{busy==="passwords"?"…":pick("رمز جدید Cisco/L2TP","Refresh Cisco/L2TP password")}</button>{shareLink&&<><button className="ghost" onClick={()=>copy(shareLink)}>{pick("کپی سابلینک","Copy sub-link")}</button><a className="ghost" href={shareLink} target="_blank" rel="noreferrer">{pick("صفحه اتصال","Connection page")}</a></>}</div>
        <div className="setting-grid"><div className="setting-box"><small>{pick("نام کاربری اکانت","Account username")}</small><div className="secret-row"><b dir="ltr">{s(account?.username||selected.account_username)||"—"}</b>{s(account?.username||selected.account_username)&&<button className="mini-btn" onClick={()=>copy(s(account?.username||selected.account_username))}>{pick("کپی","Copy")}</button>}</div></div><div className="setting-box"><small>{pick("رمز عبور اکانت","Account password")}</small><div className="secret-row"><b dir="ltr">{showPassword?s(account?.password)||"—":"••••••••"}</b><button className="mini-btn" onClick={()=>setShowPassword(value=>!value)}>{showPassword?pick("مخفی","Hide"):pick("نمایش","Show")}</button>{s(account?.password)&&<button className="mini-btn" onClick={()=>copy(s(account?.password))}>{pick("کپی","Copy")}</button>}</div></div></div>

        {credentials.length===0?<div className="runtime-empty">{pick("هنوز اطلاعات اتصال ساخته نشده است. «ساخت/بازسازی اتصال» را بزنید.","Connection data has not been provisioned yet.")}</div>:<>
          <div className="runtime-tabs">{credentials.map(item=><button type="button" key={s(item.protocol)} className={activeProtocol===s(item.protocol)?"active":""} onClick={()=>setActiveProtocol(s(item.protocol))}>{protocolLabels[s(item.protocol)]||s(item.protocol)}</button>)}</div>
          <div className="manage-card-section"><div className="manage-section-head"><div><b>{protocolLabels[s(selectedCredential?.protocol)]||s(selectedCredential?.protocol)}</b><small>{selectedItems.length.toLocaleString("fa-IR")} {pick("سرور قابل استفاده","available servers")}</small></div></div>
            <div className="protocol-toggle-grid">{selectedItems.map((item,index)=>{
              const protocol=s(selectedCredential?.protocol);const server=s(item.server||item.server_ip);const port=s(item.port||item.ports);const username=s(item.username||selectedCredential?.username||account?.username);const password=s(item.password||account?.password);const config=s(item.config);const uri=s(item.uri);const psk=s(item.psk);const filename=s(item.filename)||`${protocol}-${n(selected.id)}-${index+1}.${protocol==="openvpn"?"ovpn":protocol==="wireguard"?"conf":"txt"}`;
              return <div className="setting-box" key={`${protocol}-${n(item.node_id)}-${index}`}><div className="card-head"><div><b>{s(item.node)||`${pick("سرور","Server")} ${index+1}`}</b><small dir="ltr">{server}{port?`:${port}`:""}</small></div><Badge tone="ok">{pick("آماده","Ready")}</Badge></div>
                <div className="setting-grid">
                  {server&&<div><small>{pick("سرور","Server")}</small><div className="secret-row"><code dir="ltr">{server}</code><button className="mini-btn" onClick={()=>copy(server)}>{pick("کپی","Copy")}</button></div></div>}
                  {port&&<div><small>{pick("پورت / Transport","Port / Transport")}</small><b dir="ltr">{port}{s(item.transport)?` · ${s(item.transport)}`:""}</b></div>}
                  {username&&<div><small>{pick("نام کاربری","Username")}</small><div className="secret-row"><code dir="ltr">{username}</code><button className="mini-btn" onClick={()=>copy(username)}>{pick("کپی","Copy")}</button></div></div>}
                  {password&&<div><small>{pick("رمز عبور","Password")}</small><div className="secret-row"><code dir="ltr">{showPassword?password:"••••••••"}</code><button className="mini-btn" onClick={()=>copy(password)}>{pick("کپی","Copy")}</button></div></div>}
                  {psk&&<div><small>PSK</small><div className="secret-row"><code dir="ltr">{psk}</code><button className="mini-btn" onClick={()=>copy(psk)}>{pick("کپی","Copy")}</button></div></div>}
                  {s(item.address)&&<div><small>{pick("آدرس WireGuard","WireGuard address")}</small><code dir="ltr">{s(item.address)}</code></div>}
                  {s(item.uuid)&&<div><small>UUID</small><div className="secret-row"><code dir="ltr">{s(item.uuid)}</code><button className="mini-btn" onClick={()=>copy(s(item.uuid))}>{pick("کپی","Copy")}</button></div></div>}
                </div>
                {(config||uri)&&<div className="manage-actions">{config&&<><button className="primary-soft" onClick={()=>copy(config)}>{pick("کپی کانفیگ","Copy config")}</button><button className="ghost" onClick={()=>downloadText(filename,config)}>{pick("دانلود فایل","Download file")}</button></>}{uri&&<button className="primary-soft" onClick={()=>copy(uri)}>{pick("کپی لینک V2Ray","Copy V2Ray URI")}</button>}</div>}
                {(protocol==="wireguard"&&config||protocol==="v2ray"&&uri)&&<div style={{display:"grid",placeItems:"center",marginTop:12}}><div style={{background:"white",padding:12,borderRadius:14}}><QRCodeSVG value={protocol==="wireguard"?config:uri} size={160}/></div></div>}
              </div>;
            })}</div>
          </div>
        </>}
      </>}
    </Modal>}
  </div></Shell>;
}
