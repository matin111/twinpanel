"use client";

import {useEffect,useState,type CSSProperties} from "react";
import {createPortal} from "react-dom";

export const DEFAULT_PLAN_CATEGORY="۱ کاربره";

type CategoryPlan={device_limit?:number|null};
type TemplateKind="conversion"|"editorial"|"orbit"|"panel";

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
  return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" stroke="currentColor" strokeWidth="1.8"/>
    <path d="M4.75 20c.8-3.35 3.28-5 7.25-5s6.45 1.65 7.25 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
  </svg>;
}

function detectTemplate(plans:Element):TemplateKind{
  const named=plans.closest<HTMLElement>("[data-store-template]")?.dataset.storeTemplate||"";
  if(named==="editorial-grid-2027")return "editorial";
  if(named==="conversion-2027")return "conversion";
  if(plans.closest("[data-motion][data-shape][data-header]"))return "orbit";
  return "conversion";
}

function shellStyle(template:TemplateKind):CSSProperties{
  if(template==="editorial")return {
    width:"100%",margin:"0 auto",display:"flex",alignItems:"stretch",gap:0,
    borderTop:"1px solid rgba(148,163,184,.2)",borderBottom:"1px solid rgba(148,163,184,.2)",
    background:"transparent",overflowX:"auto",scrollbarWidth:"none",
  };
  if(template==="orbit")return {
    width:"100%",margin:"0 auto",display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:10,
    padding:10,border:"1px solid var(--orbit-dark-border,rgba(148,163,184,.16))",borderRadius:24,
    background:"color-mix(in srgb,var(--orbit-dark-surface,#11131a) 88%,transparent)",
    boxShadow:"0 18px 48px rgba(0,0,0,.18)",backdropFilter:"blur(16px)",
  };
  return {
    width:"min(100%,920px)",margin:"0 auto",display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",
    gap:12,padding:10,border:"1px solid rgba(148,163,184,.14)",borderRadius:20,
    background:"rgba(15,23,42,.34)",boxShadow:"0 14px 40px rgba(0,0,0,.12)",backdropFilter:"blur(14px)",
  };
}

function buttonStyle(template:TemplateKind,selected:boolean):CSSProperties{
  if(template==="editorial")return {
    position:"relative",appearance:"none",minWidth:180,minHeight:72,display:"flex",alignItems:"center",gap:11,
    padding:"13px 18px",border:0,borderInlineEnd:"1px solid rgba(148,163,184,.14)",borderRadius:0,
    font:"inherit",textAlign:"start",cursor:"pointer",color:"inherit",
    background:selected?"color-mix(in srgb,var(--brand-primary) 7%,transparent)":"transparent",
    boxShadow:selected?"inset 0 -2px 0 var(--brand-primary)":"none",
    transition:"background .18s ease,box-shadow .18s ease",
  };
  if(template==="orbit")return {
    position:"relative",appearance:"none",minHeight:78,display:"flex",alignItems:"center",gap:12,
    padding:"14px 16px",border:selected?"1px solid color-mix(in srgb,var(--brand-primary) 68%,white 10%)":"1px solid var(--orbit-dark-border,rgba(148,163,184,.15))",
    borderRadius:18,font:"inherit",textAlign:"start",cursor:"pointer",
    color:selected?"#fff":"inherit",
    background:selected?"linear-gradient(135deg,var(--brand-primary),color-mix(in srgb,var(--brand-secondary) 72%,#08090d))":"var(--orbit-dark-surface-alt,rgba(255,255,255,.03))",
    boxShadow:selected?"0 14px 34px color-mix(in srgb,var(--brand-primary) 26%,transparent)":"none",
    transform:selected?"translateY(-1px)":"none",transition:"all .18s ease",
  };
  return {
    position:"relative",appearance:"none",minHeight:72,display:"flex",alignItems:"center",gap:12,
    border:selected?"1px solid color-mix(in srgb,var(--brand-primary) 46%,rgba(255,255,255,.18))":"1px solid rgba(148,163,184,.15)",borderRadius:15,
    padding:"13px 15px",font:"inherit",textAlign:"start",cursor:"pointer",color:selected?"#fff":"inherit",
    background:selected?"linear-gradient(135deg,var(--brand-primary),var(--brand-secondary))":"rgba(255,255,255,.025)",
    boxShadow:selected?"0 12px 30px color-mix(in srgb,var(--brand-primary) 28%,transparent)":"0 1px 0 rgba(255,255,255,.03) inset",
    transform:selected?"translateY(-1px)":"none",transition:"all .18s ease",
  };
}

function Tabs({categories,active,onChange,counts,template}:{categories:string[];active:string;onChange:(category:string)=>void;counts?:Record<string,number>;template:TemplateKind}){
  if(categories.length<=1)return null;
  return <div data-plan-category-tabs="true" data-template={template} style={shellStyle(template)}>
    {categories.map((category,index)=>{
      const selected=category===active;
      const count=counts?.[category]??0;
      const editorial=template==="editorial";
      const orbit=template==="orbit";
      return <button key={category} type="button" aria-pressed={selected} onClick={()=>onChange(category)} style={buttonStyle(template,selected)}>
        {editorial&&<span style={{fontSize:10,fontWeight:800,letterSpacing:".12em",opacity:.45,alignSelf:"flex-start",paddingTop:3}}>{String(index+1).padStart(2,"0")}</span>}
        <span style={{
          width:editorial?34:42,height:editorial?34:42,borderRadius:orbit?14:editorial?0:13,
          display:"inline-flex",alignItems:"center",justifyContent:"center",flex:"0 0 auto",
          background:editorial?"transparent":selected?"rgba(255,255,255,.14)":"rgba(127,127,127,.08)",
          border:editorial?"0":"1px solid rgba(255,255,255,.08)",
          color:editorial&&selected?"var(--brand-primary)":"inherit",
        }}><UserIcon/></span>
        <span style={{display:"flex",flexDirection:"column",gap:4,minWidth:0,flex:1}}>
          {orbit&&<small style={{fontSize:9.5,fontWeight:800,letterSpacing:".14em",opacity:.52}}>ACCESS TIER</small>}
          <strong style={{fontSize:editorial?15:15.5,fontWeight:900,lineHeight:1.2,whiteSpace:"nowrap"}}>{category}</strong>
          <small style={{fontSize:11.5,opacity:selected?.84:.58,lineHeight:1.2}}>{count.toLocaleString("fa-IR")} پلن موجود</small>
        </span>
        {selected&&!editorial&&<span style={{width:8,height:8,borderRadius:999,background:"currentColor",boxShadow:"0 0 0 4px rgba(255,255,255,.1)",flex:"0 0 auto"}}/>}
      </button>;
    })}
  </div>;
}

export function PlanCategoryTabs(props:Props){
  const [target,setTarget]=useState<Element|null>(null);
  const [template,setTemplate]=useState<TemplateKind>(props.portalToStorePlans?"conversion":"panel");

  useEffect(()=>{
    if(!props.portalToStorePlans){setTarget(null);setTemplate("panel");return;}
    let frame=0;
    let mount:HTMLDivElement|null=null;
    const locate=()=>{
      const plans=document.querySelector("#plans");
      if(!plans){frame=window.requestAnimationFrame(locate);return;}
      setTemplate(detectTemplate(plans));
      const existing=plans.querySelector<HTMLDivElement>(":scope > [data-plan-category-mount='true']");
      mount=existing||document.createElement("div");
      if(!existing){
        mount.dataset.planCategoryMount="true";
        mount.style.width="100%";
        mount.style.gridColumn="1 / -1";
        mount.style.flex="0 0 100%";
        mount.style.order="0";
        mount.style.margin="28px 0 32px";
        mount.style.position="relative";
        mount.style.zIndex="2";
        const heading=plans.firstElementChild;
        if(heading)heading.insertAdjacentElement("afterend",mount);
        else plans.appendChild(mount);
      }
      setTarget(mount);
    };
    locate();
    return()=>{
      if(frame)window.cancelAnimationFrame(frame);
      if(mount?.parentElement)mount.parentElement.removeChild(mount);
    };
  },[props.portalToStorePlans,props.categories.join("|")]);

  const tabs=<Tabs categories={props.categories} active={props.active} onChange={props.onChange} counts={props.counts} template={template}/>;
  if(props.portalToStorePlans)return target?createPortal(tabs,target):null;
  return tabs;
}
