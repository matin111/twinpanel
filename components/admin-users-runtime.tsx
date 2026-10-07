"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,PageHead,Shell} from "./ui";
import {adminApi,AdminUser} from "../lib/admin-api";
import {customerApi,getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

const fmtDate=(value:string)=>{try{return new Date(value).toLocaleDateString("fa-IR");}catch{return "—";}};

export function AdminUsersRuntime(){
  const {pick}=useI18n();
  const [users,setUsers]=useState<AdminUser[]>([]);
  const [meId,setMeId]=useState<number|null>(null);
  const [q,setQ]=useState("");
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [modal,setModal]=useState<"create"|"edit"|"password"|null>(null);
  const [selected,setSelected]=useState<AdminUser|null>(null);
  const [name,setName]=useState("");const [email,setEmail]=useState("");const [phone,setPhone]=useState("");const [password,setPassword]=useState("");
  const [busy,setBusy]=useState(false);const [message,setMessage]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    try{
      const [rows,me]=await Promise.all([adminApi.users(),customerApi.me(getCustomerToken()||"")]);
      setUsers(rows);setMeId(me.id);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setLoading(false);}
  };
  useEffect(()=>{void load();},[]);

  const filtered=useMemo(()=>{
    const needle=q.trim().toLowerCase();
    if(!needle)return users;
    return users.filter(u=>[u.full_name,u.email,u.phone,String(u.id)].some(v=>String(v||"").toLowerCase().includes(needle)));
  },[users,q]);

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
      <div className="runtime-toolbar"><label>⌕ <input value={q} onChange={e=>setQ(e.target.value)} placeholder={pick("نام، ایمیل یا شناسه...","Name, email or ID...")}/></label><span>{filtered.length.toLocaleString("fa-IR")} {pick("کاربر","users")}</span><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
      {error&&<div className="runtime-error">{error}</div>}
      {loading?<div className="runtime-loading">{pick("در حال دریافت کاربران...","Loading users...")}</div>:<div className="table"><table><thead><tr><th>{pick("کاربر","User")}</th><th>{pick("تماس","Contact")}</th><th>{pick("نقش","Role")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عضویت","Joined")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{filtered.map(u=><tr key={u.id}><td><div className="user-cell"><b>{u.full_name||pick("بدون نام","No name")}</b><small>#{u.id}</small></div></td><td><div className="user-cell"><b dir="ltr">{u.email||"—"}</b><small dir="ltr">{u.phone||""}</small></div></td><td><Badge tone={u.role==="admin"?"violet":"ok"}>{u.role}</Badge></td><td><Badge tone={u.is_active?"ok":"bad"}>{u.is_active?pick("فعال","Active"):pick("غیرفعال","Inactive")}</Badge></td><td>{fmtDate(u.created_at)}</td><td><div className="row-actions"><button onClick={()=>openEdit(u)}>{pick("ویرایش","Edit")}</button><button onClick={()=>openPassword(u)}>{pick("رمز","Password")}</button><button disabled={u.id===meId} onClick={()=>void toggle(u)}>{u.is_active?pick("غیرفعال","Disable"):pick("فعال","Enable")}</button><button className="danger" disabled={u.id===meId||u.role==="admin"} onClick={()=>void remove(u)}>{pick("حذف","Delete")}</button></div></td></tr>)}</tbody></table></div>}
    </Card>
    {modal&&<div className="runtime-modal" role="dialog" aria-modal="true"><button className="runtime-modal-bg" onClick={close}/><form onSubmit={submit} className="runtime-modal-card"><div className="card-head"><b>{modal==="create"?pick("ساخت کاربر","Create user"):modal==="edit"?pick("ویرایش کاربر","Edit user"):pick("تغییر رمز","Change password")}</b><button type="button" className="icon-button" onClick={close}>×</button></div>{modal!=="password"&&<><label>{pick("نام","Name")}<input value={name} onChange={e=>setName(e.target.value)}/></label><label>{pick("ایمیل","Email")}<input dir="ltr" type="email" required value={email} onChange={e=>setEmail(e.target.value)}/></label><label>{pick("موبایل","Phone")}<input dir="ltr" value={phone} onChange={e=>setPhone(e.target.value)}/></label></>}{(modal==="create"||modal==="password")&&<label>{pick("رمز عبور جدید","New password")}<input type="password" minLength={8} required value={password} onChange={e=>setPassword(e.target.value)}/></label>}<div className="customer-only-note">{pick("از این فرم فقط حساب کاربر عادی ساخته می‌شود.","This form creates customer accounts only.")}</div>{message&&<div className="runtime-message">{message}</div>}<div className="runtime-modal-actions"><button type="button" className="ghost" onClick={close}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy}>{busy?"…":pick("ذخیره","Save")}</button></div></form></div>}
  </div></Shell>;
}
