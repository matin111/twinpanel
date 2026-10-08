"use client";

import {FormEvent,useEffect,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,AdminNode,AdminUser,RuntimeRow} from "../lib/admin-api";
import {legacyAdminApi} from "../lib/legacy-admin-api";
import {useI18n} from "../lib/i18n";

const GB=1024**3;
const s=(v:unknown)=>String(v??"");
const n=(v:unknown)=>{const x=Number(v??0);return Number.isFinite(x)?x:0;};
const date=(v:unknown)=>{if(!v)return "—";const d=new Date(String(v));return Number.isNaN(d.getTime())?String(v):d.toLocaleString("fa-IR");};
const tone=(v:unknown):"ok"|"warn"|"bad"|"violet"=>{const x=s(v).toLowerCase();return ["active","online","ok","healthy","configured"].includes(x)?"ok":["inactive","offline","failed","error","expired","canceled"].includes(x)?"bad":"warn";};
const protocolKeys=["cisco","openvpn","wireguard","l2tp","v2ray"];
const protocolLabels:Record<string,string>={cisco:"Cisco / OpenConnect",openvpn:"OpenVPN",wireguard:"WireGuard",l2tp:"L2TP / IPsec",v2ray:"V2Ray / Xray"};

type ModalKind="manage"|"create"|"edit"|"password"|"subedit"|"extend"|null;

function Notice({error,ok}:{error:string;ok:string}){return <>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}</>;}
function Check({label,checked,onChange}:{label:string;checked:boolean;onChange:(value:boolean)=>void}){return <label className="toggle module-toggle compact-toggle"><span>{label}</span><input type="checkbox" checked={checked} onChange={e=>onChange(e.target.checked)}/><i/></label>;}

export function LegacyUsersRuntimePage(){
  const {pick}=useI18n();
  const [items,setItems]=useState<(AdminUser&RuntimeRow)[]>([]);
  const [summary,setSummary]=useState<RuntimeRow>({});
  const [total,setTotal]=useState(0);
  const [q,setQ]=useState("");
  const [status,setStatus]=useState<"all"|"active"|"inactive"|"subscribed">("all");
  const [page,setPage]=useState(0);
  const limit=20;

  const [selected,setSelected]=useState<(AdminUser&RuntimeRow)|null>(null);
  const [subs,setSubs]=useState<RuntimeRow[]>([]);
  const [plans,setPlans]=useState<RuntimeRow[]>([]);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [subsLoading,setSubsLoading]=useState(false);

  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [loading,setLoading]=useState(true);
  const [modal,setModal]=useState<ModalKind>(null);
  const [targetSub,setTargetSub]=useState<RuntimeRow|null>(null);
  const [userDraft,setUserDraft]=useState({full_name:"",email:"",phone:"",password:""});
  const [subDraft,setSubDraft]=useState({plan_id:0,traffic_gb:0,node_ids:[] as number[],protocols:[] as string[],account_username:"",account_password:"",add_days:30,add_traffic_gb:10});

  const load=async()=>{
    setLoading(true);setError("");
    try{
      const [u,p,ns]=await Promise.all([
        legacyAdminApi.usersPage({limit,offset:page*limit,q,status}),
        adminApi.plans(),
        adminApi.nodes()
      ]);
      setItems(u.items as (AdminUser&RuntimeRow)[]);
      setSummary(u.summary);
      setTotal(u.total);
      setPlans(p);
      setNodes(ns);
      setSelected(current=>current?((u.items as (AdminUser&RuntimeRow)[]).find(x=>x.id===current.id)||current):null);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setLoading(false);}
  };

  useEffect(()=>{const t=window.setTimeout(()=>void load(),q?250:0);return()=>window.clearTimeout(t);},[q,status,page]);

  const loadSubscriptions=async(userId:number)=>{
    setSubsLoading(true);
    try{setSubs(await legacyAdminApi.subscriptionsByUser(userId));}
    catch(e){setError(e instanceof Error?e.message:String(e));setSubs([]);}
    finally{setSubsLoading(false);}
  };

  const openManage=async(u:AdminUser&RuntimeRow)=>{
    setSelected(u);setOk("");setError("");setModal("manage");
    await loadSubscriptions(u.id);
  };

  const act=async(key:string,label:string,fn:()=>Promise<unknown>,reloadSubs=true)=>{
    if(busy)return;
    setBusy(key);setError("");setOk("");
    try{
      await fn();setOk(label);await load();
      if(selected&&reloadSubs)await loadSubscriptions(selected.id);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  const openCreate=()=>{setSelected(null);setUserDraft({full_name:"",email:"",phone:"",password:""});setModal("create");};
  const openEdit=(user=selected)=>{if(!user)return;setSelected(user);setUserDraft({full_name:user.full_name||"",email:user.email||"",phone:s(user.phone),password:""});setModal("edit");};
  const openPassword=(user=selected)=>{if(!user)return;setSelected(user);setUserDraft(d=>({...d,password:""}));setModal("password");};

  const saveUser=(e:FormEvent)=>{
    e.preventDefault();
    if(modal==="create"){
      void act("create",pick("کاربر ساخته شد","User created"),()=>adminApi.createUser({email:userDraft.email.trim(),phone:userDraft.phone.trim()||undefined,password:userDraft.password,full_name:userDraft.full_name.trim()}),false).then(()=>setModal(null));
    }else if(modal==="edit"&&selected){
      void act("edit-user",pick("کاربر ویرایش شد","User updated"),()=>adminApi.updateUser(selected.id,{email:userDraft.email.trim(),phone:userDraft.phone.trim(),full_name:userDraft.full_name.trim()}),false).then(()=>setModal(null));
    }else if(modal==="password"&&selected){
      void act("password",pick("رمز عبور تغییر کرد","Password updated"),()=>adminApi.resetUserPassword(selected.id,userDraft.password),false).then(()=>setModal(null));
    }
  };

  const openSubEdit=(sub:RuntimeRow)=>{
    setTargetSub(sub);
    setSubDraft({
      plan_id:n(sub.plan_id),
      traffic_gb:n(sub.traffic_limit_gb)||(n(sub.traffic_limit_bytes)/GB),
      node_ids:Array.isArray(sub.node_ids)?sub.node_ids.map(Number):[],
      protocols:Array.isArray(sub.protocols)?sub.protocols.map(String):[],
      account_username:s(sub.account_username),
      account_password:"",
      add_days:30,
      add_traffic_gb:10
    });
    setModal("subedit");
  };

  const openExtend=(sub:RuntimeRow)=>{setTargetSub(sub);setSubDraft(d=>({...d,add_days:30,add_traffic_gb:10}));setModal("extend");};

  const saveSub=(e:FormEvent)=>{
    e.preventDefault();if(!targetSub)return;const id=n(targetSub.id);
    if(modal==="subedit"){
      void act("subedit",pick("اشتراک ویرایش شد","Subscription updated"),()=>adminApi.editSubscription(id,{plan_id:subDraft.plan_id,traffic_gb:subDraft.traffic_gb,node_ids:subDraft.node_ids,protocols:subDraft.protocols,account_username:subDraft.account_username||undefined,account_password:subDraft.account_password||undefined})).then(()=>setModal("manage"));
    }else if(modal==="extend"){
      void act("extend",pick("اشتراک تمدید شد","Subscription extended"),()=>adminApi.extendSubscription(id,{add_days:subDraft.add_days,traffic_gb:subDraft.add_traffic_gb})).then(()=>setModal("manage"));
    }
  };

  const removeUser=async(user:AdminUser&RuntimeRow)=>{
    if(!window.confirm(pick("کاربر و اشتراک‌های وابسته حذف شوند؟","Delete user and dependent subscriptions?")))return;
    await act("delete",pick("کاربر حذف شد","User deleted"),()=>adminApi.deleteUser(user.id),false);
    setModal(null);setSelected(null);setSubs([]);
  };

  const activeSubs=subs.filter(x=>s(x.status).toLowerCase()==="active").length;
  const allocatedGb=subs.reduce((a,x)=>a+n(x.traffic_limit_bytes),0)/GB;
  const usedGb=subs.reduce((a,x)=>a+n(x.traffic_used_bytes),0)/GB;

  return <Shell active="/admin/users"><div className="page legacy-users-page">
    <div className="page-head"><div><h1>{pick("کاربران","Users")}</h1><small>{pick("مدیریت کاربران و اشتراک‌های وابسته","Users and dependent subscriptions")}</small></div><button className="primary" onClick={openCreate}>＋ {pick("کاربر جدید","New user")}</button></div>
    <Notice error={error} ok={ok}/>
    <div className="stats dashboard-stats"><Stat label={pick("کل کاربران","Total users")} value={s(summary.total_users||total)}/><Stat label={pick("فعال","Active")} value={s(summary.active_users||0)}/><Stat label={pick("غیرفعال","Inactive")} value={s(summary.inactive_users||0)}/><Stat label={pick("دارای اشتراک","Subscribed")} value={s(summary.subscribed_users||0)}/></div>

    <Card>
      <div className="runtime-toolbar"><label>⌕ <input value={q} onChange={e=>{setQ(e.target.value);setPage(0);}} placeholder={pick("نام، ایمیل، موبایل یا شناسه…","Name, email, phone or ID…")}/></label><select value={status} onChange={e=>{setStatus(e.target.value as typeof status);setPage(0);}}><option value="all">{pick("همه","All")}</option><option value="active">{pick("فعال","Active")}</option><option value="inactive">{pick("غیرفعال","Inactive")}</option><option value="subscribed">{pick("دارای اشتراک","Subscribed")}</option></select><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
      {loading?<div className="runtime-loading">…</div>:<div className="table"><table><thead><tr><th>{pick("کاربر","User")}</th><th>{pick("ایمیل / موبایل","Contact")}</th><th>{pick("اشتراک‌ها","Subscriptions")}</th><th>{pick("ترافیک","Traffic")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{items.map(u=><tr key={u.id}><td><button className="text-button" onClick={()=>void openManage(u)}><b>{u.full_name||`#${u.id}`}</b><small>#{u.id}</small></button></td><td><div className="user-cell"><b dir="ltr">{u.email||"—"}</b><small dir="ltr">{s(u.phone)}</small></div></td><td>{n(u.subscription_count).toLocaleString("fa-IR")} <small>({n(u.active_count)} {pick("فعال","active")})</small></td><td>{(n(u.used_bytes)/GB).toFixed(1)} / {(n(u.limit_bytes)/GB).toFixed(1)} GB</td><td><Badge tone={u.is_active?"ok":"bad"}>{u.is_active?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge></td><td><div className="row-actions"><button className="primary-soft" onClick={()=>void openManage(u)}>{pick("مدیریت","Manage")}</button><button onClick={()=>openEdit(u)}>{pick("ویرایش","Edit")}</button><button onClick={()=>openPassword(u)}>{pick("رمز","Password")}</button><button onClick={()=>void act("toggle",pick("وضعیت تغییر کرد","Status updated"),()=>adminApi.toggleUser(u.id),false)}>{u.is_active?pick("غیرفعال","Disable"):pick("فعال","Enable")}</button><button className="danger" onClick={()=>void removeUser(u)}>{pick("حذف","Delete")}</button></div></td></tr>)}</tbody></table></div>}
      <div className="pager"><button disabled={page===0} onClick={()=>setPage(p=>Math.max(0,p-1))}>{pick("قبلی","Previous")}</button><span>{total?`${(page*limit+1).toLocaleString("fa-IR")}–${Math.min(total,(page+1)*limit).toLocaleString("fa-IR")}`:"۰"} / {total.toLocaleString("fa-IR")}</span><button disabled={(page+1)*limit>=total} onClick={()=>setPage(p=>p+1)}>{pick("بعدی","Next")}</button></div>
    </Card>

    {modal==="manage"&&selected&&<div className="runtime-modal user-manage-modal" role="dialog" aria-modal="true">
      <button className="runtime-modal-bg" onClick={()=>setModal(null)}/>
      <div className="runtime-modal-card manage-card">
        <div className="card-head"><div><b>{pick("مدیریت کاربر","User management")} — {selected.full_name||selected.email||`#${selected.id}`}</b><small>{selected.email} · {s(selected.phone)||"—"} · {pick("عضویت","Joined")}: {date(selected.created_at)}</small></div><button type="button" className="icon-button" onClick={()=>setModal(null)}>×</button></div>
        <Notice error={error} ok={ok}/>
        <div className="manage-actions"><button className="ghost" onClick={()=>openEdit()}>{pick("ویرایش کاربر","Edit user")}</button><button className="ghost" onClick={()=>openPassword()}>{pick("تغییر رمز","Reset password")}</button><button className="ghost" disabled={!!busy} onClick={()=>void act("manage-toggle",pick("وضعیت تغییر کرد","Status updated"),()=>adminApi.toggleUser(selected.id),false)}>{selected.is_active?pick("غیرفعال کردن","Disable user"):pick("فعال کردن","Enable user")}</button><button className="danger" disabled={!!busy} onClick={()=>void removeUser(selected)}>{pick("حذف کاربر","Delete user")}</button></div>
        <div className="stats dashboard-stats modal-stats"><Stat label={pick("اشتراک‌ها","Subscriptions")} value={String(subs.length)}/><Stat label={pick("فعال","Active")} value={String(activeSubs)}/><Stat label={pick("حجم کل","Allocated")} value={`${allocatedGb.toFixed(1)} GB`}/><Stat label={pick("مصرف کل","Used")} value={`${usedGb.toFixed(1)} GB`}/></div>
        <div className="manage-section-head"><div><b>{pick("اشتراک‌های کاربر","User subscriptions")}</b><small>{pick("تمام عملیات بدون خروج از مدیریت کاربر","All actions stay inside this dialog")}</small></div><button className="ghost" disabled={subsLoading} onClick={()=>void loadSubscriptions(selected.id)}>{subsLoading?"…":pick("بروزرسانی","Refresh")}</button></div>
        {subsLoading?<div className="runtime-loading">…</div>:subs.length?<div className="table modal-table"><table><thead><tr><th>{pick("اشتراک","Subscription")}</th><th>{pick("پلن","Plan")}</th><th>{pick("نام کاربری","Username")}</th><th>{pick("مصرف","Usage")}</th><th>{pick("انقضا","Expires")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{subs.map(sub=><tr key={n(sub.id)}><td>#{n(sub.id)}</td><td>{s(sub.plan_name)||`#${n(sub.plan_id)}`}</td><td dir="ltr">{s(sub.account_username)||"—"}</td><td>{(n(sub.traffic_used_bytes)/GB).toFixed(1)} / {(n(sub.traffic_limit_bytes)/GB).toFixed(1)} GB</td><td>{date(sub.expires_at)}</td><td><Badge tone={tone(sub.status)}>{s(sub.status)}</Badge></td><td><div className="row-actions"><button onClick={()=>openSubEdit(sub)}>{pick("ویرایش","Edit")}</button><button onClick={()=>openExtend(sub)}>{pick("تمدید","Extend")}</button><button disabled={!!busy} onClick={()=>void act("sub-toggle",pick("وضعیت اشتراک تغییر کرد","Subscription status updated"),()=>adminApi.setSubscriptionActive(n(sub.id),s(sub.status).toLowerCase()!=="active"))}>{s(sub.status).toLowerCase()==="active"?pick("تعلیق","Suspend"):pick("فعال","Activate")}</button><button className="danger" disabled={!!busy} onClick={()=>{if(window.confirm(pick("اشتراک حذف شود؟","Delete subscription?")))void act("sub-delete",pick("اشتراک حذف شد","Subscription deleted"),()=>adminApi.deleteSubscription(n(sub.id)));}}>{pick("حذف","Delete")}</button></div></td></tr>)}</tbody></table></div>:<div className="runtime-empty">{pick("این کاربر اشتراکی ندارد","This user has no subscriptions")}</div>}
      </div>
    </div>}

    {modal&&modal!=="manage"&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" onClick={()=>setModal(selected?"manage":null)}/><form className="runtime-modal-card wide" onSubmit={modal==="subedit"||modal==="extend"?saveSub:saveUser}><div className="card-head"><b>{modal==="create"?pick("کاربر جدید","New user"):modal==="edit"?pick("ویرایش کاربر","Edit user"):modal==="password"?pick("تغییر رمز","Reset password"):modal==="subedit"?pick("ویرایش اشتراک","Edit subscription"):pick("تمدید اشتراک","Extend subscription")}</b><button type="button" className="icon-button" onClick={()=>setModal(selected?"manage":null)}>×</button></div>
      {(modal==="create"||modal==="edit")&&<div className="setting-grid"><label className="field"><span>{pick("نام","Name")}</span><input value={userDraft.full_name} onChange={e=>setUserDraft(d=>({...d,full_name:e.target.value}))}/></label><label className="field"><span>{pick("ایمیل","Email")}</span><input dir="ltr" type="email" required value={userDraft.email} onChange={e=>setUserDraft(d=>({...d,email:e.target.value}))}/></label><label className="field"><span>{pick("موبایل","Phone")}</span><input dir="ltr" value={userDraft.phone} onChange={e=>setUserDraft(d=>({...d,phone:e.target.value}))}/></label>{modal==="create"&&<label className="field"><span>{pick("رمز عبور","Password")}</span><input dir="ltr" type="password" minLength={8} required value={userDraft.password} onChange={e=>setUserDraft(d=>({...d,password:e.target.value}))}/></label>}</div>}
      {modal==="password"&&<label className="field"><span>{pick("رمز جدید","New password")}</span><input dir="ltr" type="password" minLength={8} required value={userDraft.password} onChange={e=>setUserDraft(d=>({...d,password:e.target.value}))}/></label>}
      {modal==="subedit"&&<><div className="setting-grid"><label className="field"><span>{pick("پلن","Plan")}</span><select value={subDraft.plan_id} onChange={e=>setSubDraft(d=>({...d,plan_id:Number(e.target.value)}))}>{plans.map(p=><option key={s(p.id)} value={n(p.id)}>{s(p.name)||`#${p.id}`}</option>)}</select></label><label className="field"><span>{pick("حجم کل GB","Total traffic GB")}</span><input type="number" min={0} step="0.1" value={subDraft.traffic_gb} onChange={e=>setSubDraft(d=>({...d,traffic_gb:Number(e.target.value)}))}/></label><label className="field"><span>{pick("نام کاربری اکانت","Account username")}</span><input dir="ltr" value={subDraft.account_username} onChange={e=>setSubDraft(d=>({...d,account_username:e.target.value}))}/></label><label className="field"><span>{pick("رمز جدید اکانت (اختیاری)","New account password (optional)")}</span><input dir="ltr" type="password" value={subDraft.account_password} onChange={e=>setSubDraft(d=>({...d,account_password:e.target.value}))}/></label></div><div className="protocol-toggle-grid">{protocolKeys.map(k=><Check key={k} label={protocolLabels[k]} checked={subDraft.protocols.includes(k)} onChange={checked=>setSubDraft(d=>({...d,protocols:checked?[...new Set([...d.protocols,k])]:d.protocols.filter(x=>x!==k)}))}/>)}</div><div className="runtime-choice-section"><b>{pick("نودها","Nodes")}</b><div className="protocol-toggle-grid">{nodes.map(node=><Check key={node.id} label={`${node.name} · ${node.public_ip||""}`} checked={subDraft.node_ids.includes(node.id)} onChange={checked=>setSubDraft(d=>({...d,node_ids:checked?[...new Set([...d.node_ids,node.id])]:d.node_ids.filter(x=>x!==node.id)}))}/>)}</div></div></>}
      {modal==="extend"&&<div className="setting-grid"><label className="field"><span>{pick("افزودن روز","Add days")}</span><input type="number" min={0} value={subDraft.add_days} onChange={e=>setSubDraft(d=>({...d,add_days:Number(e.target.value)}))}/></label><label className="field"><span>{pick("افزودن حجم GB","Add traffic GB")}</span><input type="number" min={0} step="0.1" value={subDraft.add_traffic_gb} onChange={e=>setSubDraft(d=>({...d,add_traffic_gb:Number(e.target.value)}))}/></label></div>}
      <div className="runtime-modal-actions"><button type="button" className="ghost" onClick={()=>setModal(selected?"manage":null)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={!!busy}>{busy?"…":pick("ذخیره","Save")}</button></div></form></div>}
  </div></Shell>;
}
