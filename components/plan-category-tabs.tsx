"use client";

import {useEffect,useState} from "react";
import {createPortal} from "react-dom";

export const DEFAULT_PLAN_CATEGORY="۱ کاربره";

type CategoryPlan={device_limit?:number|null};

type Props={
  categories:string[];
  active:string;
  onChange:(category:string)=>void;
  counts?:Record<string,number>;
  portalToStorePlans?:boolean;
};

function normalizedDeviceLimit(value:unknown){
  const parsed=Number(value||1);
  if(!Number.isFinite(parsed)||parsed<1)return 1;
  return Math.max(1,Math.trunc(parsed));
}

export function normalizePlanCategory(value:unknown){
  const deviceLimit=normalizedDeviceLimit(value);
  return `${deviceLimit.toLocaleString("fa-IR")} کاربره`;
}

export function planCategories<T extends CategoryPlan>(plans:T[]){
  const limits=[...new Set(plans.map(plan=>normalizedDeviceLimit(plan.device_limit)))].sort((a,b)=>a-b);
  return limits.map(limit=>normalizePlanCategory(limit));
}

export function planCategoryCounts<T extends CategoryPlan>(plans:T[]){
  return plans.reduce<Record<string,number>>((result,plan)=>{
    const category=normalizePlanCategory(plan.device_limit);
    result[category]=(result[category]||0)+1;
    return result;
  },{});
}

export function filterPlansByCategory<T extends CategoryPlan>(plans:T[],category:string){
  if(!category)return plans;
  return plans.filter(plan=>normalizePlanCategory(plan.device_limit)===category);
}

function UserIcon(){
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" stroke="currentColor" strokeWidth="1.8"/>
    <path d="M4.75 20c.8-3.35 3.28-5 7.25-5s6.45 1.65 7.25 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
  </svg>;
}

function Tabs({categories,active,onChange,counts}:Omit<Props,"portalToStorePlans">){
  if(categories.length<=1)return null;

  return <div
    data-plan-category-tabs="true"
    style={{
      width:"100%",
      display:"grid",
      gridTemplateColumns:"repeat(auto-fit,minmax(150px,1fr))",
      gap:10,
      margin:"20px 0 26px",
      padding:8,
      border:"1px solid rgba(148,163,184,.16)",
      borderRadius:18,
      background:"rgba(127,127,127,.045)",
      backdropFilter:"blur(10px)",
    }}
  >
    {categories.map(category=>{
      const selected=category===active;
      const count=counts?.[category]??0;
      return <button
        key={category}
        type="button"
        aria-pressed={selected}
        onClick={()=>onChange(category)}
        style={{
          position:"relative",
          appearance:"none",
          minHeight:64,
          display:"flex",
          alignItems:"center",
          gap:11,
          border:selected?"1px solid rgba(255,255,255,.14)":"1px solid rgba(148,163,184,.16)",
          borderRadius:14,
          padding:"11px 13px",
          font:"inherit",
          textAlign:"start",
          cursor:"pointer",
          color:selected?"#fff":"inherit",
          background:selected
            ?"linear-gradient(135deg,var(--store-chat-accent,#7c3aed),color-mix(in srgb,var(--store-chat-accent,#7c3aed) 72%,#111827))"
            :"rgba(255,255,255,.035)",
          boxShadow:selected?"0 10px 28px color-mix(in srgb,var(--store-chat-accent,#7c3aed) 24%,transparent)":"0 1px 0 rgba(255,255,255,.03) inset",
          transform:selected?"translateY(-1px)":"none",
          transition:"transform .18s ease,box-shadow .18s ease,border-color .18s ease,background .18s ease",
        }}
      >
        <span style={{
          width:38,height:38,borderRadius:12,display:"inline-flex",alignItems:"center",justifyContent:"center",flex:"0 0 auto",
          background:selected?"rgba(255,255,255,.14)":"rgba(127,127,127,.09)",
          border:"1px solid rgba(255,255,255,.08)",
        }}><UserIcon/></span>

        <span style={{display:"flex",flexDirection:"column",gap:3,minWidth:0,flex:1}}>
          <strong style={{fontSize:14.5,fontWeight:900,lineHeight:1.25,whiteSpace:"nowrap"}}>{category}</strong>
          <small style={{fontSize:11.5,opacity:selected?.82:.58,lineHeight:1.2}}>{count.toLocaleString("fa-IR")} پلن موجود</small>
        </span>

        {selected&&<span style={{
          width:8,height:8,borderRadius:999,background:"#fff",boxShadow:"0 0 0 4px rgba(255,255,255,.12)",flex:"0 0 auto"
        }}/>} 
      </button>;
    })}
  </div>;
}

export function PlanCategoryTabs(props:Props){
  const [target,setTarget]=useState<Element|null>(null);
  useEffect(()=>{
    if(!props.portalToStorePlans){setTarget(null);return;}
    let frame=0;
    const locate=()=>{
      const next=document.querySelector("#plans > :first-child");
      if(next)setTarget(next);
      else frame=window.requestAnimationFrame(locate);
    };
    locate();
    return()=>{if(frame)window.cancelAnimationFrame(frame);};
  },[props.portalToStorePlans,props.categories.join("|")]);

  const tabs=<Tabs categories={props.categories} active={props.active} onChange={props.onChange} counts={props.counts}/>;
  if(props.portalToStorePlans)return target?createPortal(tabs,target):null;
  return tabs;
}
