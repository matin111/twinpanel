"use client";

import {FormEvent,useEffect,useRef,useState} from "react";
import {Badge,Card,PageHead,Shell} from "./ui";
import {adminApi,AdminUser} from "../lib/admin-api";
import {customerApi,getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {AdminUsersWalletInline} from "./admin-users-wallet-inline";

const fmtDate=(value:string)=>{try{return new Date(value).toLocaleDateString("fa-IR");}catch{return "—";}};

export function AdminUsersRuntime(){
  const {pick}=useI18n();
  const [users,setUsers]=useState<AdminUser[]>([]);
  const [meId,setMeId]=useState<number|null>(null);
  const [q,setQ]=useState("");
  const [page,setPage]=useState(0);
  const [total,setTotal]=useState(0);
  const limit=20;
  const requestId=useRef(0);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [modal,setModal]=useState<"create"|"edit"|"password"|null>(null);
  const [selected,setSelected]=useState<AdminUser|null>(null);
  const [name,setName]=useState("");const [email,setEmail]=useState("");const [phone,setPhone]=useState("");const [password,setPassword]=useState("");
  const [busy,setBusy]=useState(false);const [message,setMessage]=useState("");

  const load=async()=>{
    const id=++requestId.current;
    setLoading(true);
    setError("");
    try{
      const response=await adminApi.usersFastPage({limit,offset:page*limit,q:q.trim()});
      if(id!==requestId.current)return;
      setUsers(response.items);
      setTotal(response.total);
    }catch(e){
      if(id===requestId.current)setError(e instanceof Error?e.message:String(e));
    }finally{
      if(id===requestId.current)setLoading(false);
    }
  };
  useEffect(()=>{
    const timer=window.setTimeout(()=>void load(),q.trim()?250:0);
    return()=>{window.clearTimeout(timer);requestId.current+=1;};
  },[q,page]);
  // The current administrator identity must not hold up the roster response.
  useEffect(()=>{
    void customerApi.me(getCustomerToken()||"").then(me=>setMeId(me.id)).catch(()=>{});
  },[]);

  const resetForm=()=>{setName("");setEmail("");setPhone("");setPassword("");setSelected(null);setMessage("");};
  const openCreate=()=>{resetForm();setModal("create");};
  const openEdit=(u:AdminUser)=>{setSelected(u);setName(u.full_name||"");setEmail(u.email||"");setPhone(u.phone||"");setPassword("");setMessage("");setModal("edit");};
  const openPassword=(u:AdminUser)=>{setSelected(u);setPassword("");setMessage("");setModal("password");};
  const close=()=>{setModal(null);resetForm();};

  const submit=async(e:FormEvent)=>{
    e.preventDefault();if(busy)return;setBusy(true);setMessage("");
    try{
      if(modal==="create"){
        if(password.length<8)throw new Error(pick("رمز حداقل ۸ کاراکتر باشد","Password must be at least 8 characters"));
        await adminApi.createUser({email:email.trim().toLowerCase(),phone:phone.trim()||undefined,password,full_name:name.trim()});
        setMessage(pick("کاربر ساخته شد","User created"));
      }else if(modal==="edit"&&selected){
        await adminApi.updateUser(selected.id,{email:email.trim().toLowerCase(),phone:phone.trim(),full_name:name.trim()});
        setMessage(pick("اطلاعات ذخیره شد","Changes saved"));
      }else if(modal==="password"&&selected){
        if(password.length<8)throw new Error(pick("رمز حداقل ۸ کاراکتر باشد","Password must be at least 8 characters"));
        await adminApi.resetUserPassword(selected.id,password);
        setMessage(pick("رمز عبور تغییر کرد","Password changed"));
      }
      await load();window.setTimeout(close,650);
    }catch(err){setMessage(err instanceof Error?err.message:String(err));}
    finally{setBusy(false);}
  };

  const toggle=async(u:AdminUser)=>{if(u.id===meId)return;try{await adminApi.toggleUser(u.id);await load();}catch(e){setError(e instanceof Error?e.message:String(e));}};
  const remove=async(u:AdminUser)=>{if(u.id===meId)return;if(!window.confirm(pick(`کاربر ${u.email||u.id} حذف شود؟`,`Delete ${u.email||u.id}?`)))return;try{await adminApi.deleteUser(u.id);await load();}catch(e){setError(e instanceof Error?e.message:String(e));}};

  return <Shell active="/admin/users"><div className="page admin-users-runtime">
    <div className="page-head"><div><h1>{pick("کاربران","Users")}</h1></div><button className="primary" onClick={openCreate}>＋ {pick("کاربر جدید","New user")}</button></div>
    <Card>
      <div className="runtime-toolbar"><label>⌕ <input value={q} onChange={e=>{setQ(e.target.value);setPage(0);}} placeholder={pick("نام، ایمیل یا شناسه...","Name, email or ID...")}/></label><span>{total.toLocaleString("fa-IR")} {pick("کاربر","users")}</span><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
      {error&&<div className="runtime-error">{error}</div>}
      {loading&&users.length===0?<div className="runtime-loading">{pick("در حال دریافت کاربران...","Loading users...")}</div>:
        <div className="admin-user-cards" aria-label={pick("فهرست کاربران","Users list")}>
          {users.map(u=><article className="admin-user-card" key={u.id}>
            <div className="admin-user-card-head">
              <div className="admin-user-identity">
                <span className="admin-user-avatar" aria-hidden="true">{(u.full_name||u.email||"U").trim().slice(0,1).toUpperCase()}</span>
                <div className="admin-user-names"><b dir="auto">{u.full_name||pick("بدون نام","No name")}</b><small dir="ltr">#{u.id}</small></div>
              </div>
              <Badge tone={u.is_active?"ok":"bad"}>{u.is_active?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge>
            </div>
            <div className="admin-user-contact">
              <div><small>{pick("ایمیل","Email")}</small><b dir="ltr" title={u.email||""}>{u.email||"—"}</b></div>
              <div><small>{pick("شماره تماس","Phone")}</small><b dir="ltr">{u.phone||"—"}</b></div>
            </div>
            <div className="admin-user-account-count"><small>{pick("تعداد اکانت‌ها","Accounts")}</small><b>{u.subscription_count ?? "—"}</b></div>
            <div className="admin-user-card-meta">
              <span><small>{pick("نقش","Role")}</small><Badge tone={u.role==="admin"?"violet":"ok"}>{u.role}</Badge></span>
              <span><small>{pick("تاریخ عضویت","Joined")}</small><b>{fmtDate(u.created_at)}</b></span>
            </div>
            <div className="admin-user-card-actions">
              <button type="button" className="admin-user-action edit" disabled={busy} onClick={()=>openEdit(u)}>✎ {pick("ویرایش","Edit")}</button>
              <button type="button" className="admin-user-action password" disabled={busy} onClick={()=>openPassword(u)}>⌑ {pick("رمز","Password")}</button>
              <button type="button" className="admin-user-action toggle" disabled={busy||meId===null||u.id===meId} onClick={()=>void toggle(u)}>{u.is_active?pick("غیرفعال","Disable"):pick("فعال","Enable")}</button>
              <button type="button" className="admin-user-action danger" disabled={busy||meId===null||u.id===meId||u.role==="admin"} onClick={()=>void remove(u)}>{pick("حذف","Delete")}</button>
            </div>
          </article>)}
          {!loading&&users.length===0&&<div className="runtime-empty">{pick("کاربری پیدا نشد","No users found")}</div>}
        </div>}
      <style>{`
        .admin-users-runtime .admin-user-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;direction:rtl}
        .admin-users-runtime .admin-user-card{min-width:0;overflow:hidden;padding:15px;border:1px solid rgba(119,118,240,.45);border-radius:19px;background:linear-gradient(145deg,rgba(52,44,106,.33),rgba(12,23,44,.94) 58%,rgba(11,21,40,.97));box-shadow:inset 0 1px rgba(255,255,255,.075),0 8px 23px rgba(0,0,0,.14);display:flex;flex-direction:column;gap:13px;transition:border-color .2s,transform .2s,box-shadow .2s;color:#e9efff}
        .admin-users-runtime .admin-user-card:hover{border-color:rgba(157,131,255,.82);transform:translateY(-2px);box-shadow:0 13px 28px rgba(0,0,0,.18)}
        .admin-users-runtime .admin-user-card-head,.admin-users-runtime .admin-user-identity{display:flex;align-items:center;justify-content:space-between;gap:10px;min-width:0}
        .admin-users-runtime .admin-user-identity{justify-content:flex-start;flex:1}
        .admin-users-runtime .admin-user-avatar{flex:none;width:39px;height:39px;display:grid;place-items:center;border:1px solid rgba(151,114,255,.65);border-radius:50%;color:#f0e6ff;background:linear-gradient(135deg,#6430b8,#263d91);font-weight:800}
        .admin-users-runtime .admin-user-names{display:grid;gap:3px;min-width:0}
        .admin-users-runtime .admin-user-names b{font-size:14px;overflow-wrap:anywhere}
        .admin-users-runtime .admin-user-names small,.admin-users-runtime .admin-user-contact small,.admin-users-runtime .admin-user-card-meta small{color:#aebbd5;font-size:11px}
        .admin-users-runtime .admin-user-contact{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,.75fr);gap:9px;padding:12px;border:1px solid rgba(139,158,206,.13);background:rgba(5,12,30,.2);border-radius:12px}
        .admin-users-runtime .admin-user-contact>div{display:grid;gap:5px;min-width:0}
        .admin-users-runtime .admin-user-contact b{font-size:12px;overflow-wrap:anywhere;text-align:start;direction:ltr}
        .admin-users-runtime .admin-user-account-count{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 12px;border:1px solid rgba(139,158,206,.2);border-radius:11px;background:rgba(13,25,51,.55)}
        .admin-users-runtime .admin-user-account-count small{color:#aebbd5;font-size:11px}
        .admin-users-runtime .admin-user-account-count b{font-size:16px;color:#a7d0ff}
        .admin-users-runtime .admin-user-card-meta{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}
        .admin-users-runtime .admin-user-card-meta>span{display:flex;align-items:center;gap:8px}
        .admin-users-runtime .admin-user-card-meta b{font-size:12px;font-weight:600}
        .admin-users-runtime .admin-user-card-actions{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin-top:auto}
        .admin-users-runtime .admin-user-action{min-width:0;min-height:38px;padding:5px 3px;border:1px solid rgba(128,147,204,.22);border-radius:9px;background:rgba(29,42,72,.48);color:#eef3ff;cursor:pointer;font:inherit;font-size:11px;white-space:nowrap}
        .admin-users-runtime .admin-user-action.edit{border-color:rgba(100,160,255,.4);color:#bed7ff}
        .admin-users-runtime .admin-user-action.password{border-color:rgba(173,141,255,.35)}
        .admin-users-runtime .admin-user-action.danger{border-color:rgba(244,93,115,.35);color:#ff9aa9}
        .admin-users-runtime .admin-user-action:hover:not(:disabled){background:rgba(91,74,167,.32);border-color:rgba(165,146,255,.7)}
        .admin-users-runtime .admin-user-action:disabled{opacity:.42;cursor:not-allowed}
        @media(max-width:1200px){.admin-users-runtime .admin-user-cards{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:720px){.admin-users-runtime .admin-user-cards{grid-template-columns:minmax(0,1fr);gap:10px}.admin-users-runtime .admin-user-card{padding:13px}.admin-users-runtime .admin-user-contact{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(prefers-reduced-motion:reduce){.admin-users-runtime .admin-user-card{transition:none}.admin-users-runtime .admin-user-card:hover{transform:none}}
      `}</style>
    </Card>
    <div className="runtime-toolbar" style={{justifyContent:"space-between",gap:12,marginTop:12}}>
      <span>{pick("صفحه","Page")} {(page+1).toLocaleString("fa-IR")} / {Math.max(1,Math.ceil(total/limit)).toLocaleString("fa-IR")}{loading?" · …":""}</span>
      <div className="row-actions">
        <button className="ghost" type="button" disabled={loading||page===0} onClick={()=>setPage(v=>Math.max(0,v-1))}>{pick("قبلی","Previous")}</button>
        <button className="ghost" type="button" disabled={loading||(page+1)*limit>=total} onClick={()=>setPage(v=>v+1)}>{pick("بعدی","Next")}</button>
      </div>
    </div>
    <AdminUsersWalletInline />
    {modal&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" onClick={close}/><form onSubmit={submit} className="runtime-modal-card"><div className="card-head"><b>{modal==="create"?pick("ساخت کاربر","Create user"):modal==="edit"?pick("ویرایش کاربر","Edit user"):pick("تغییر رمز","Change password")}</b><button type="button" className="icon-button" onClick={close}>×</button></div>{modal!=="password"&&<><label>{pick("نام","Name")}<input value={name} onChange={e=>setName(e.target.value)}/></label><label>{pick("ایمیل","Email")}<input dir="ltr" type="email" required value={email} onChange={e=>setEmail(e.target.value)}/></label><label>{pick("موبایل","Phone")}<input dir="ltr" value={phone} onChange={e=>setPhone(e.target.value)}/></label></>}{(modal==="create"||modal==="password")&&<label>{pick("رمز عبور جدید","New password")}<input type="password" minLength={8} required value={password} onChange={e=>setPassword(e.target.value)}/></label>}<div className="customer-only-note">{pick("از این فرم فقط حساب کاربر عادی ساخته می‌شود.","This form creates customer accounts only.")}</div>{message&&<div className="runtime-message">{message}</div>}<div className="runtime-modal-actions"><button type="button" className="ghost" onClick={close}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy}>{busy?"…":pick("ذخیره","Save")}</button></div></form></div>}
  </div></Shell>;
}
