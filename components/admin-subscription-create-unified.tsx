"use client";

import {FormEvent,useCallback,useEffect,useMemo,useState} from "react";
import {createPortal} from "react-dom";
import {adminApi,type AdminNode,type AdminUser,type RuntimeRow} from "../lib/admin-api";
import {createSubscriptionFastV1} from "../lib/subscription-create-fast-api";
import {subscriptionProtocolApi,type SubscriptionProtocolDefinition} from "../lib/subscription-protocol-api";
import {useI18n} from "../lib/i18n";

const num=(value:unknown)=>{const n=Number(value??0);return Number.isFinite(n)?n:0;};
const clean=(value:string)=>{const raw=value.trim();if(!raw)return null;const n=Number(raw);return Number.isFinite(n)?n:null;};

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
  const [planId,setPlanId]=useState(0);
  const [traffic,setTraffic]=useState("");
  const [duration,setDuration]=useState("");
  const [deviceLimit,setDeviceLimit]=useState("1");
  const [username,setUsername]=useState("");
  const [password,setPassword]=useState("");
  const [protocols,setProtocols]=useState<string[]>([]);
  const [nodeIds,setNodeIds]=useState<number[]>([]);

  const exitNodes=useMemo(()=>nodes.filter(node=>String(node.node_type||"").toLowerCase()==="exit"&&String(node.status||"online").toLowerCase()!=="retired"),[nodes]);
  const classic=useMemo(()=>catalog.filter(item=>item.family==="classic"),[catalog]);
  const modern=useMemo(()=>catalog.filter(item=>item.family==="modern"),[catalog]);

  const applyPlan=(id:number,rows=plans)=>{
    setPlanId(id);
    const plan=rows.find(item=>num(item.id)===id);
    if(!plan){setTraffic("");setDuration("");setDeviceLimit("1");return;}
    setTraffic(String(num(plan.traffic_gb)));
    setDuration(String(Math.max(1,Math.trunc(num(plan.duration_days)||30))));
    setDeviceLimit(String(Math.max(1,Math.trunc(num(plan.device_limit)||1))));
  };

  const openCreate=useCallback(async()=>{
    if(busy)return;
    setOpen(true);setLoading(true);setError("");setUsername("");setPassword("");
    try{
      const [userRows,planRows,nodeRows,catalogPayload]=await Promise.all([adminApi.users(),adminApi.plans(),adminApi.nodes(),subscriptionProtocolApi.catalog()]);
      if(catalogPayload.protocols.length!==15)throw new Error(pick("کاتالوگ ۱۵ پروتکل کامل نیست","The 15-protocol catalog is incomplete"));
      const exits=nodeRows.filter(node=>String(node.node_type||"").toLowerCase()==="exit"&&String(node.status||"online").toLowerCase()!=="retired");
      setUsers(userRows);setPlans(planRows);setNodes(nodeRows);setCatalog(catalogPayload.protocols);
      setUserId(userRows.find(user=>user.role!=="admin"&&user.is_active!==false)?.id||0);
      const firstPlan=planRows.find(item=>item.is_active!==false)||planRows[0];
      const firstPlanId=num(firstPlan?.id);applyPlan(firstPlanId,planRows);
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

  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(busy||loading)return;
    const trafficValue=clean(traffic),durationValue=clean(duration),deviceValue=clean(deviceLimit);
    if(!userId){setError(pick("کاربر را انتخاب کنید","Select a user"));return;}
    if(!planId){setError(pick("پلن را انتخاب کنید","Select a plan"));return;}
    if(trafficValue===null||trafficValue<0){setError(pick("حجم معتبر نیست","Invalid traffic"));return;}
    if(durationValue===null||durationValue<=0||!Number.isInteger(durationValue)){setError(pick("مدت معتبر نیست","Invalid duration"));return;}
    if(deviceValue===null||deviceValue<1||!Number.isInteger(deviceValue)){setError(pick("اتصال همزمان معتبر نیست","Invalid device limit"));return;}
    if(!protocols.length){setError(pick("حداقل یک پروتکل انتخاب کنید","Select at least one protocol"));return;}
    if(!nodeIds.length){setError(pick("حداقل یک سرور انتخاب کنید","Select at least one server"));return;}
    setBusy(true);setError("");
    try{
      await createSubscriptionFastV1({user_id:userId,plan_id:planId,node_ids:[...nodeIds],protocols:[...protocols],traffic_gb:trafficValue,duration_days:durationValue,device_limit:deviceValue,...(username.trim()?{username:username.trim()}:{}),...(password.trim()?{password:password.trim()}:{})});
      setOpen(false);
      window.setTimeout(()=>window.location.reload(),700);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  if(!mounted||!open)return null;
  const group=(title:string,items:SubscriptionProtocolDefinition[])=><div className="runtime-choice-section"><div className="card-head"><b>{title}</b><small>{items.filter(item=>protocols.includes(item.key)).length}/{items.length}</small></div><div className="protocol-toggle-grid">{items.map(item=><label className="toggle module-toggle" key={item.key}><span>{item.title}</span><input type="checkbox" checked={protocols.includes(item.key)} onChange={()=>toggleProtocol(item.key)}/><i/></label>)}</div></div>;

  return createPortal(<div className="runtime-modal manual-subscription-modal" role="dialog" aria-modal="true">
    <button type="button" className="runtime-modal-bg" onClick={()=>!busy&&setOpen(false)}/>
    <div className="runtime-modal-card manage-card" style={{width:"min(980px,calc(100vw - 28px))",maxHeight:"88dvh"}}>
      <div className="card-head"><div><b>{pick("ساخت اشتراک","Create subscription")}</b><small>{pick("پروتکل‌ها و سرورها را برای همین اکانت انتخاب کنید.","Choose protocols and servers for this account.")}</small></div><button type="button" className="icon-button" disabled={busy} onClick={()=>setOpen(false)}>×</button></div>
      {error&&<div className="runtime-error">{error}</div>}
      <form className="subscription-create-form" onSubmit={submit}>
        <div className="setting-grid compact-create-grid">
          <label className="field"><span>{pick("کاربر","User")}</span><select value={userId} disabled={loading} onChange={e=>setUserId(Number(e.target.value))}><option value={0}>{pick("انتخاب کاربر","Select user")}</option>{users.filter(user=>user.role!=="admin"&&user.is_active!==false).map(user=><option key={user.id} value={user.id}>{user.full_name||user.email||`#${user.id}`}</option>)}</select></label>
          <label className="field"><span>{pick("پلن","Plan")}</span><select value={planId} disabled={loading} onChange={e=>applyPlan(Number(e.target.value))}><option value={0}>{pick("انتخاب پلن","Select plan")}</option>{plans.filter(plan=>plan.is_active!==false).map(plan=><option key={num(plan.id)} value={num(plan.id)}>{String(plan.name||`#${num(plan.id)}`)}</option>)}</select></label>
        </div>
        <div className="card-head"><div><b>{pick("پروتکل‌ها","Protocols")}</b><small>{protocols.length}/15</small></div><div className="row-actions"><button type="button" className="ghost" onClick={()=>setProtocols(catalog.map(item=>item.key))}>{pick("انتخاب همه","Select all")}</button><button type="button" className="ghost" onClick={()=>setProtocols([])}>{pick("لغو همه","Clear all")}</button></div></div>
        {group(pick("پروتکل‌های کلاسیک","Classic protocols"),classic)}
        {group(pick("پروتکل‌های جدید","Modern protocols"),modern)}
        <div className="runtime-choice-section"><div className="card-head"><div><b>{pick("سرورها","Servers")}</b><small>{nodeIds.length}/{exitNodes.length}</small></div><div className="row-actions"><button type="button" className="ghost" onClick={()=>setNodeIds(exitNodes.map(node=>node.id))}>{pick("انتخاب همه","Select all")}</button><button type="button" className="ghost" onClick={()=>setNodeIds([])}>{pick("لغو همه","Clear all")}</button></div></div><div className="protocol-toggle-grid">{exitNodes.map(node=><label className="toggle module-toggle" key={node.id}><span>{node.name}<small dir="ltr">{node.public_ip||node.country_code||""}</small></span><input type="checkbox" checked={nodeIds.includes(node.id)} onChange={()=>toggleNode(node.id)}/><i/></label>)}</div></div>
        <div className="setting-grid compact-create-grid">
          <label className="field"><span>{pick("حجم GB","Traffic GB")}</span><input type="number" min={0} step="0.1" value={traffic} onChange={e=>setTraffic(e.target.value)}/></label>
          <label className="field"><span>{pick("مدت روز","Duration days")}</span><input type="number" min={1} step={1} value={duration} onChange={e=>setDuration(e.target.value)}/></label>
          <label className="field"><span>{pick("اتصال همزمان","Concurrent devices")}</span><input type="number" min={1} step={1} value={deviceLimit} onChange={e=>setDeviceLimit(e.target.value)}/></label>
          <label className="field"><span>{pick("نام کاربری","Username")}</span><input dir="ltr" value={username} onChange={e=>setUsername(e.target.value)} placeholder={pick("خالی = خودکار","empty = automatic")}/></label>
          <label className="field"><span>{pick("رمز عبور","Password")}</span><input dir="ltr" value={password} onChange={e=>setPassword(e.target.value)} placeholder={pick("خالی = خودکار","empty = automatic")}/></label>
        </div>
        <div className="modalActions"><button type="button" className="ghost" disabled={busy} onClick={()=>setOpen(false)}>{pick("انصراف","Cancel")}</button><button className="primary" disabled={busy||loading||!userId||!planId||!protocols.length||!nodeIds.length}>{busy?pick("در حال ثبت…","Submitting…"):pick("ساخت و صدور اکانت","Create & provision")}</button></div>
      </form>
    </div>
  </div>,document.body);
}
