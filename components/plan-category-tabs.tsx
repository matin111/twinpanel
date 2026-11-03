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

function Tabs({categories,active,onChange,counts}:Omit<Props,"portalToStorePlans">){
  if(categories.length<=1)return null;
  return <div data-plan-category-tabs="true" style={{display:"flex",flexWrap:"wrap",gap:8,alignItems:"center",justifyContent:"center",margin:"18px 0 22px",padding:"6px"}}>
    {categories.map(category=>{
      const selected=category===active;
      return <button
        key={category}
        type="button"
        aria-pressed={selected}
        onClick={()=>onChange(category)}
        style={{
          appearance:"none",border:selected?"1px solid transparent":"1px solid rgba(148,163,184,.28)",
          borderRadius:999,padding:"10px 15px",font:"inherit",fontWeight:800,cursor:"pointer",
          color:selected?"#fff":"inherit",background:selected?"var(--store-chat-accent,#7c3aed)":"rgba(127,127,127,.08)",
          boxShadow:selected?"0 8px 24px rgba(124,58,237,.22)":"none",transition:"all .18s ease",
        }}
      >👤 {category}{counts?.[category]!=null&&<span style={{marginInlineStart:7,opacity:.75,fontSize:".82em"}}>({counts[category]})</span>}</button>;
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
