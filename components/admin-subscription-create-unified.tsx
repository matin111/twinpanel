"use client";

import {FormEvent,useCallback,useEffect,useMemo,useState} from "react";
import {createPortal} from "react-dom";
import {adminApi,type AdminNode,type AdminUser,type RuntimeRow} from "../lib/admin-api";
import {createSubscriptionFastV1} from "../lib/subscription-create-fast-api";
import {subscriptionProtocolApi,type SubscriptionProtocolDefinition} from "../lib/subscription-protocol-api";
import {useI18n} from "../lib/i18n";

const num=(value:unknown)=>{const n=Number(value??0);return Number.isFinite(n)?n:0;};
const clean=(value:string)=>{const raw=value.trim();if(!raw)return null;const n=Number(raw);return Number.isFinite(n)?n:null;};
const box={border:"1px solid rgba(148,163,184,.16)",background:"rgba(15,23,42,.46)",borderRadius:16};
const tinyButton={height:32,padding:"0 11px",borderRadius:10,fontSize:12};

export function AdminSubscriptionCreateUnified(){
  const {pick}=useI18n();
  const [mounted,setMounted]=useState(false);
  const [open,setOpen]=useState(false);
  const [loading,setLoading]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [users,setUsers]=useState<AdminUser[]>([]);
  const [plans,setPlans]=useState<RuntimeRow[]>([]);
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [catalog,setCatalog]=useState<SubscriptionProtocolDefinition[]>([]);
  const [userId,setUserId]=useState(0);
  const [userSearch,setUserSearch]=useState("");
  const [planId,setPlanId]=useState(0);
  const [traffic,setTraffic]=useState("");
  const [duration,setDuration]=useState("");
  const [deviceLimit,setDeviceLimit]=useState("1");
  const [username,setUsername]=useState("");
  const [password,setPassword]=useState("");
  const [protocols,setProtocols]=useState<string[]>([]);
  const [nodeIds,setNodeIds]=useState<number[]>([]);

  const exitNodes=useMemo(()=>nodes.filter(node=>String(node.node_type||"").toLowerCase()==="exit"&&String(node.status||"online").toLowerCase()!=="retired"),[nodes]);
  const eligibleUsers=useMemo(()=>users.filter(user=>user.role!=="admin"&&user.is_active!==false),[users]);
  const filteredUsers=useMemo(()=>{
    const query=userSearch.trim().toLowerCase();
    if(!query)return eligibleUsers;
    return eligibleUsers.filter(user=>[user.full_name,user.email,user.phone,`#${user.id}`,String(user.id)].some(value=>String(value||"").toLowerCase().includes(query)));
  },[eligibleUsers,userSearch]);

  const applyPlan=(id:number,rows=plans)=>{
    setPlanId(id);
    const plan=rows.find(item=>num(item.id)===id);
    if(!plan){setTraffic("");setDuration("");setDeviceLimit("1");return;}
    setTraffic(num(plan.traffic_gb)>0?String(num(plan.traffic_gb)):"");
    setDuration(plan.duration_days!==null&&plan.duration_days!==undefined?String(Math.max(0,Math.trunc(num(plan.duration_days)))):"");
    setDeviceLimit(String(Math.max(1,Math.trunc(num(plan.device_limit)||1))));
  };

  const openCreate=useCallback(async()=>{
    if(busy)return;
    setOpen(true);setLoading(true);setError("");setUsername("");setPassword("");setUserSearch("");
    try{
      const [userRows,planRows,nodeRows,catalogPayload]=await Promise.all([adminApi.users(),adminApi.plans(),adminApi.nodes(),subscriptionProtocolApi.catalog()]);
      if(!Array.isArray(catalogPayload.protocols)||catalogPayload.protocols.length===0)throw new Error(pick("کاتالوگ پروتکل‌ها دریافت نشد","Protocol catalog could not be loaded"));
      const exits=nodeRows.filter(node=>String(node.node_type||"").toLowerCase()==="exit"&&String(node.status||"online").toLowerCase()!=="retired");
      setUsers(userRows);setPlans(planRows);setNodes(nodeRows);setCatalog(catalogPayload.protocols);
      setUserId(userRows.find(user=>user.role!=="admin"&&user.is_active!==false)?.id||0);
      applyPlan(0,planRows);
      setProtocols(catalogPayload.protocols.filter(item=>item.family==="classic").map(item=>item.key));
      setNodeIds(exits.map(node=>node.id));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setLoading(false);}
  },[busy,pick]);

  useEffect(()=>{
    setMounted(true);
    let frame=0;
    let button:HTMLButtonElement|null=null;
    const intercept=(event:MouseEvent)=>{event.preventDefault();event.stopPropagation();event.stopImmediatePropagation();void openCreate();};
    const locate=()=>{
      button=document.querySelector<HTMLButtonElement>(".legacy-subscriptions-page .page-head button.primary");
      if(!button){frame=requestAnimationFrame(locate);return;}
      button.setAttribute("data-unified-subscription-create","true");
      button.addEventListener("click",intercept,true);
    };
    frame=requestAnimationFrame(locate);
    return()=>{cancelAnimationFrame(frame);button?.removeEventListener("click",intercept,true);button?.removeAttribute("data-unified-subscription-create");};
  },[openCreate]);

  const toggleProtocol=(key:string)=>setProtocols(current=>current.includes(key)?current.filter(item=>item!==key):[...current,key]);
  const toggleNode=(id:number)=>setNodeIds(current=>current.includes(id)?current.filter(item=>item!==id):[...current,id]);

  const submitNow=async()=>{
    if(busy||loading)return;
    const trafficValue=traffic.trim()===""?0:clean(traffic),durationValue=duration.trim()===""?null:clean(duration),deviceValue=clean(deviceLimit);
    if(!userId){setError(pick("کاربر را انتخاب کنید","Select a user"));return;}
    if(trafficValue===null||trafficValue<0){setError(pick("حجم معتبر نیست","Invalid traffic"));return;}
    if(durationValue===null||durationValue<0||!Number.isInteger(durationValue)){setError(pick("مدت معتبر نیست","Invalid duration"));return;}
    if(deviceValue===null||deviceValue<1||!Number.isInteger(deviceValue)){setError(pick("اتصال همزمان معتبر نیست","Invalid device limit"));return;}
    if(!protocols.length){setError(pick("حداقل یک پروتکل انتخاب کنید","Select at least one protocol"));return;}
    if(!nodeIds.length){setError(pick("حداقل یک سرور انتخاب کنید","Select at least one server"));return;}

    setBusy(true);setError("");
    try{
      const result=await createSubscriptionFastV1({
        user_id:userId,plan_id:planId||null,node_ids:[...nodeIds],protocols:[...protocols],
        traffic_gb:trafficValue,duration_days:durationValue,device_limit:deviceValue,
        ...(username.trim()?{username:username.trim()}:{}),...(password.trim()?{password:password.trim()}:{})
      });
      if(result?.ok===false)throw new Error(result.message||pick("ثبت اکانت انجام نشد","Account creation failed"));
      setOpen(false);
      window.setTimeout(()=>window.location.reload(),450);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const submit=(event:FormEvent)=>{event.preventDefault();void submitNow();};

  if(!mounted||!open)return null;

  const choice=(checked:boolean,label:string,sub:string,onToggle:()=>void)=><button type="button" onClick={onToggle} style={{display:"flex",alignItems:"center",justifyContent:"space-between",gap:10,minHeight:42,padding:"9px 11px",borderRadius:12,border:checked?"1px solid rgba(124,92,255,.62)":"1px solid rgba(148,163,184,.14)",background:checked?"rgba(109,74,255,.13)":"rgba(15,23,42,.26)",color:"inherit",cursor:"pointer",textAlign:"right"}}><span style={{display:"grid",gap:2,minWidth:0}}><b style={{fontSize:12,fontWeight:700,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{label}</b>{sub&&<small dir="ltr" style={{fontSize:10,opacity:.58,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{sub}</small>}</span><span aria-hidden="true" style={{width:20,height:20,borderRadius:999,border:checked?"6px solid #7c5cff":"2px solid rgba(148,163,184,.42)",background:checked?"white":"transparent",flex:"0 0 auto"}}/></button>;

  return createPortal(<div className="runtime-modal manual-subscription-modal" role="dialog" aria-modal="true">
    <button type="button" className="runtime-modal-bg" onClick={()=>!busy&&setOpen(false)}/>
    <div className="runtime-modal-card" style={{width:"min(920px,calc(100vw - 24px))",maxHeight:"86dvh",padding:0,overflow:"hidden",borderRadius:20,boxShadow:"0 28px 80px rgba(0,0,0,.42)"}}>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",gap:16,padding:"14px 16px",borderBottom:"1px solid rgba(148,163,184,.12)",background:"rgba(15,23,42,.82)",position:"sticky",top:0,zIndex:5}}>
        <div><b style={{fontSize:16}}>{pick("ساخت اشتراک","Create subscription")}</b><div style={{fontSize:11,opacity:.58,marginTop:3}}>{pick("همه انتخاب‌ها در یک صفحه؛ ساخت اکانت بعد از ثبت در پس‌زمینه ادامه پیدا می‌کند.","Everything in one compact view; provisioning continues in the background.")}</div></div>
        <button type="button" className="icon-button" disabled={busy} onClick={()=>setOpen(false)}>×</button>
      </div>

      <form onSubmit={submit} style={{display:"grid",gridTemplateRows:"1fr auto",minHeight:0,maxHeight:"calc(86dvh - 64px)"}}>
        <div style={{overflowY:"auto",padding:"14px",display:"grid",gap:12}}>
          {error&&<div className="runtime-error" style={{margin:0}}>{error}</div>}

          <section style={{...box,padding:12}}>
            <div style={{display:"grid",gridTemplateColumns:"repeat(2,minmax(0,1fr))",gap:10}}>
              <label className="field"><span>{pick("کاربر","User")}</span><input value={userSearch} disabled={loading} onChange={e=>setUserSearch(e.target.value)} placeholder={pick("جستجو با نام، ایمیل یا ID","Search by name, email or ID")}/><select value={userId} disabled={loading} onChange={e=>setUserId(Number(e.target.value))}><option value={0}>{pick("انتخاب کاربر","Select user")}</option>{filteredUsers.map(user=><option key={user.id} value={user.id}>{[user.full_name,user.email,`#${user.id}`].filter(Boolean).join(" · ")}</option>)}</select><small style={{opacity:.55}}>{pick(`${filteredUsers.length} کاربر`,`${filteredUsers.length} users`)}</small></label>
              <label className="field"><span>{pick("پلن (اختیاری)","Plan (optional)")}</span><select value={planId} disabled={loading} onChange={e=>applyPlan(Number(e.target.value))}><option value={0}>{pick("بدون پلن — ساخت دستی","No plan — manual")}</option>{plans.filter(plan=>plan.is_active!==false).map(plan=><option key={num(plan.id)} value={num(plan.id)}>{String(plan.name||`#${num(plan.id)}`)}</option>)}</select><small style={{opacity:.55}}>{planId?pick("مقادیر پلن قابل ویرایش هستند","Plan values remain editable"):pick("حجم و مدت را دستی وارد کنید","Enter traffic and duration manually")}</small></label>
            </div>
          </section>

          <section style={{...box,padding:12}}>
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",gap:10,marginBottom:10}}><div><b>{pick("پروتکل‌ها","Protocols")}</b><small style={{marginInlineStart:8,opacity:.55}}>{protocols.length}/15</small></div><div style={{display:"flex",gap:6}}><button type="button" className="ghost" style={tinyButton} onClick={()=>setProtocols(catalog.map(item=>item.key))}>{pick("همه","All")}</button><button type="button" className="ghost" style={tinyButton} onClick={()=>setProtocols([])}>{pick("هیچکدام","None")}</button></div></div>
            <div style={{display:"grid",gridTemplateColumns:"repeat(3,minmax(0,1fr))",gap:7}}>{catalog.map(item=><div key={item.key}>{choice(protocols.includes(item.key),item.title,item.family==="classic"?pick("کلاسیک","Classic"):pick("مدرن","Modern"),()=>toggleProtocol(item.key))}</div>)}</div>
          </section>

          <section style={{...box,padding:12}}>
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",gap:10,marginBottom:10}}><div><b>{pick("سرورها","Servers")}</b><small style={{marginInlineStart:8,opacity:.55}}>{nodeIds.length}/{exitNodes.length}</small></div><div style={{display:"flex",gap:6}}><button type="button" className="ghost" style={tinyButton} onClick={()=>setNodeIds(exitNodes.map(node=>node.id))}>{pick("همه","All")}</button><button type="button" className="ghost" style={tinyButton} onClick={()=>setNodeIds([])}>{pick("هیچکدام","None")}</button></div></div>
            <div style={{display:"grid",gridTemplateColumns:"repeat(2,minmax(0,1fr))",gap:7}}>{exitNodes.map(node=><div key={node.id}>{choice(nodeIds.includes(node.id),node.name,node.public_ip||node.country_code||"",()=>toggleNode(node.id))}</div>)}</div>
          </section>

          <section style={{...box,padding:12}}>
            <div style={{display:"grid",gridTemplateColumns:"repeat(5,minmax(0,1fr))",gap:9}}>
              <label className="field"><span>{pick("حجم GB","Traffic GB")}</span><input type="number" min={0} step="0.1" value={traffic} onChange={e=>setTraffic(e.target.value)} placeholder={pick("خالی = نامحدود","Empty = unlimited")}/><small>{pick("خالی یا صفر = حجم نامحدود","Empty or 0 = unlimited traffic")}</small></label>
              <label className="field"><span>{pick("مدت روز","Days")}</span><input type="number" min={0} step={1} value={duration} onChange={e=>setDuration(e.target.value)} placeholder={pick("خالی = نامحدود","Empty = unlimited")}/><small>{pick("خالی یا صفر = زمان نامحدود","Empty or 0 = unlimited duration")}</small></label>
              <label className="field"><span>{pick("اتصال","Devices")}</span><input type="number" min={1} step={1} value={deviceLimit} onChange={e=>setDeviceLimit(e.target.value)}/></label>
              <label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" value={username} onChange={e=>setUsername(e.target.value)} placeholder={pick("خودکار","Auto")}/></label>
              <label className="field"><span>{pick("رمز عبور","Password")}</span><input dir="ltr" value={password} onChange={e=>setPassword(e.target.value)} placeholder={pick("خودکار","Auto")}/></label>
            </div>
          </section>
        </div>

        <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",gap:10,padding:"11px 14px",borderTop:"1px solid rgba(148,163,184,.12)",background:"rgba(15,23,42,.92)",position:"sticky",bottom:0,zIndex:5}}>
          <small style={{opacity:.55}}>{pick(`${protocols.length} پروتکل • ${nodeIds.length} سرور`,`${protocols.length} protocols • ${nodeIds.length} servers`)}</small>
          <div style={{display:"flex",gap:8}}><button type="button" className="ghost" disabled={busy} onClick={()=>setOpen(false)}>{pick("انصراف","Cancel")}</button><button type="button" className="primary" disabled={busy||loading} onClick={()=>void submitNow()}>{busy?pick("در حال ثبت…","Submitting…"):pick("ساخت اکانت","Create account")}</button></div>
        </div>
      </form>
    </div>
  </div>,document.body);
}