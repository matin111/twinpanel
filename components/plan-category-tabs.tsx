"use client";

import {useEffect,useState} from "react";
import {createPortal} from "react-dom";

export const DEFAULT_PLAN_CATEGORY="سایر پلن‌ها";

type CategoryPlan={category?:string|null};

type Props={
  categories:string[];
  active:string;
  onChange:(category:string)=>void;
  counts?:Record<string,number>;
  portalToStorePlans?:boolean;
};

export function normalizePlanCategory(value:unknown){
  const category=String(value||"").trim().replace(/\s+/g," ");
  return category||DEFAULT_PLAN_CATEGORY;
}

export function planCategories<T extends CategoryPlan>(plans:T[]){
  const seen=new Set<string>();
  const result:string[]=[];
  for(const plan of plans){
    const category=normalizePlanCategory(plan.category);
    if(seen.has(category))continue;
    seen.add(category);
    result.push(category);
  }
  return result;
}

export function planCategoryCounts<T extends CategoryPlan>(plans:T[]){
  return plans.reduce<Record<string,number>>((result,plan)=>{
    const category=normalizePlanCategory(plan.category);
    result[category]=(result[category]||0)+1;
    return result;
  },{});
}

export function filterPlansByCategory<T extends CategoryPlan>(plans:T[],category:string){
  if(!category)return plans;
  return plans.filter(plan=>normalizePlanCategory(plan.category)===category);
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
      >{category}{counts?.[category]!=null&&<span style={{marginInlineStart:7,opacity:.75,fontSize:".82em"}}>({counts[category]})</span>}</button>;
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
