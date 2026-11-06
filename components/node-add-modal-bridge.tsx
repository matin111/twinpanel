"use client";

import {FormEvent,useEffect,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {parityApi,type ProvisionInstallPayload} from "../lib/admin-parity-api";
import {useI18n} from "../lib/i18n";

type NodeDraft={host:string;port:number;username:string;password:string;name:string;node_type:"iran"|"exit";country_code:string;capacity_users:number;};
const defaultDraft:NodeDraft={host:"",port:22,username:"root",password:"",name:"",node_type:"exit",country_code:"DE",capacity_users:1000};
const NO_PROTOCOLS={install_cisco:false,cisco_port:443,install_openvpn:false,openvpn_port:1194,openvpn_transport:"udp" as const,install_wireguard:false,wireguard_port:51820,install_l2tp:false,install_v2ray:false,xray_port:8443};
function payloadOf(draft:NodeDraft):ProvisionInstallPayload{return {...draft,country_code:draft.node_type==="iran"?"IR":draft.country_code.trim().toUpperCase(),...NO_PROTOCOLS};}

export function NodeAddModalBridge(){
  const {pick}=useI18n();
  const [open,setOpen]=useState(false);
  const [draft,setDraft]=useState<NodeDraft>(defaultDraft);
  const [publishToAll,setPublishToAll]=useState(false);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  useEffect(()=>{
    const onClick=(event:MouseEvent)=>{
      const target=event.target as HTMLElement|null;
      const anchor=target?.closest?.('a[href="/admin/provision"]') as HTMLAnchorElement|null;
      if(!anchor)return;
      event.preventDefault();setError("");setOk("");setOpen(true);
    };
    document.addEventListener("click",onClick,true);
    return()=>document.removeEventListener("click",onClick,true);
  },[]);

  const test=async()=>{
    if(busy)return;
    setBusy("test");setError("");setOk("");
    try{await parityApi.provisionTest({host:draft.host.trim(),port:draft.port,username:draft.username.trim()||"root",password:draft.password});setOk(pick("اتصال SSH و سیستم‌عامل سرور تایید شد.","SSH connection and server OS verified."));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(busy)return;
    const token=getCustomerToken();
    if(!token){setError("AUTH_REQUIRED");return;}
    const payload={...payloadOf({...draft,host:draft.host.trim(),username:draft.username.trim()||"root",name:draft.name.trim()}),publish_to_all_users:draft.node_type==="exit"?publishToAll:false};
    setBusy("register");setError("");setOk("");
    try{
      const response=await fetch(`${API_BASE}/v1/nodes/install-background-v1`,{
        method:"POST",cache:"no-store",
        headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},
        body:JSON.stringify(payload),
      });
      const raw=await response.text();
      if(!response.ok)throw new Error(raw||`API error ${response.status}`);
      setOpen(false);
      setOk(pick("ثبت سرور شروع شد؛ آماده‌سازی و نمایش برای همه کاربران در پس‌زمینه ادامه دارد. صفحه را باز نگه ندارید؛ Job روی سرور ادامه می‌یابد.","Server registration started; preparation and publishing to all users continue in the backend."));
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy("");
    }
  };

  return <>
    {!open&&ok?<div className="runtime-success" style={{marginBottom:12}}>{ok}</div>:null}
    {!open&&error?<div className="runtime-error" style={{marginBottom:12}}>{error}</div>:null}
    {open?<div className="runtime-modal" role="dialog" aria-modal="true">
    <button type="button" className="runtime-modal-bg" aria-label="close" onClick={()=>setOpen(false)}/>
    <div className="runtime-modal-card" style={{width:"min(760px,100%)"}}>
      <div className="card-head"><div><b>{pick("افزودن سرور","Add server")}</b><small>{pick("ثبت نود، SSH و زیرساخت پایه","Node registration, SSH and base infrastructure")}</small></div><button type="button" className="icon-button" onClick={()=>setOpen(false)}>×</button></div>
      {error?<div className="runtime-error">{error}</div>:null}
      {ok?<div className="runtime-success">{ok}</div>:null}
      <form onSubmit={submit}>
        <div className="setting-grid">
          <label className="field"><span>{pick("نام سرور","Server name")}</span><input required value={draft.name} onChange={e=>setDraft(v=>({...v,name:e.target.value}))}/></label>
          <label className="field"><span>IP / Host</span><input required dir="ltr" value={draft.host} onChange={e=>setDraft(v=>({...v,host:e.target.value}))}/></label>
          <label className="field"><span>{pick("نوع نود","Node type")}</span><select value={draft.node_type} onChange={e=>setDraft(v=>{const node_type=e.target.value as "iran"|"exit";return {...v,node_type,country_code:node_type==="iran"?"IR":v.country_code==="IR"?"DE":v.country_code};})}><option value="iran">Iran</option><option value="exit">Exit</option></select></label>
          <label className="field"><span>{pick("کشور","Country")}</span><input dir="ltr" maxLength={2} value={draft.country_code} onChange={e=>setDraft(v=>({...v,country_code:e.target.value.toUpperCase()}))}/></label>
          <label className="field"><span>SSH Port</span><input type="number" min={1} max={65535} value={draft.port} onChange={e=>setDraft(v=>({...v,port:Number(e.target.value)||22}))}/></label>
          <label className="field"><span>SSH Username</span><input dir="ltr" value={draft.username} onChange={e=>setDraft(v=>({...v,username:e.target.value}))}/></label>
          <label className="field"><span>SSH Password</span><input type="password" autoComplete="new-password" required value={draft.password} onChange={e=>setDraft(v=>({...v,password:e.target.value}))}/></label>
          <label className="field"><span>{pick("ظرفیت کاربر","User capacity")}</span><input type="number" min={1} value={draft.capacity_users} onChange={e=>setDraft(v=>({...v,capacity_users:Number(e.target.value)||1}))}/></label>
        </div>
        {draft.node_type==="exit"?<div className="runtime-choice-section"><label className="toggle module-toggle"><span>{pick("نمایش برای همه کاربران سایت","Show for all site users")}</span><input type="checkbox" checked={publishToAll} onChange={e=>setPublishToAll(e.target.checked)}/><i/></label><small>{pick("با فعال‌کردن این گزینه، نود فقط به اشتراک‌های فعال قبلی که منقضی نشده‌اند و حجم دارند اضافه می‌شود. برای خریداران جدید، نود را جداگانه در پلن اقتصادی یا ویژه انتخاب کنید. کانفیگ‌های ناقص کاربران قبلی به‌صورت خودکار در صف پایدار ساخته می‌شوند و پیشرفت از مدیریت نود قابل مشاهده است.","When enabled, the node is assigned to eligible existing active subscriptions only. Select it separately in Economy/Premium plans for new purchases. Missing existing-account credentials are automatically queued and tracked under node management.")}</small></div>:null}
        <div className="runtime-warning">{pick("پروتکل‌ها بعد از ثبت از صفحه «پروتکل‌ها» مدیریت می‌شوند. برای Exit، Xray baseline به‌صورت خودکار آماده می‌شود.","Protocols are managed from Protocols after registration. Exit nodes automatically receive the Xray baseline.")}</div>
        <div className="action-row"><button type="button" className="ghost" disabled={Boolean(busy)||!draft.host||!draft.password} onClick={()=>void test()}>{busy==="test"?"…":pick("تست SSH","Test SSH")}</button><button className="primary" disabled={Boolean(busy)||!draft.host||!draft.password||!draft.name}>{busy==="register"?pick("در حال ثبت...","Registering..."):pick("ثبت و آماده‌سازی سرور","Register & prepare server")}</button></div>
      </form>
    </div>
  </div>:null}
  </>;
}