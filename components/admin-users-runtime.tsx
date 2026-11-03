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
      {loading&&users.length===0?<div className="runtime-loading">{pick("در حال دریافت کاربران...","Loading users...")}</div>:<div className="table"><table><thead><tr><th>{pick("کاربر","User")}</th><th>{pick("تماس","Contact")}</th><th>{pick("نقش","Role")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عضویت","Joined")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{users.map(u=><tr key={u.id}><td><div className="user-cell"><b>{u.full_name||pick("بدون نام","No name")}</b><small>#{u.id}</small></div></td><td><div className="user-cell"><b dir="ltr">{u.email||"—"}</b><small dir="ltr">{u.phone||""}</small></div></td><td><Badge tone={u.role==="admin"?"violet":"ok"}>{u.role}</Badge></td><td><Badge tone={u.is_active?"ok":"bad"}>{u.is_active?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge></td><td>{fmtDate(u.created_at)}</td><td><div className="row-actions"><button onClick={()=>openEdit(u)}>{pick("ویرایش","Edit")}</button><button onClick={()=>openPassword(u)}>{pick("رمز","Password")}</button><button disabled={meId===null||u.id===meId} onClick={()=>void toggle(u)}>{u.is_active?pick("غیرفعال","Disable"):pick("فعال","Enable")}</button><button className="danger" disabled={meId===null||u.id===meId||u.role==="admin"} onClick={()=>void remove(u)}>{pick("حذف","Delete")}</button></div></td></tr>)}</tbody></table></div>}
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
