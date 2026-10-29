"use client";

import {useEffect,useState} from "react";
import {createPortal} from "react-dom";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";

type SystemHealth={
  hostname?:string;
  cpu?:{percent?:number};
  memory?:{percent?:number;used_bytes?:number;total_bytes?:number};
  disk?:{percent?:number;used_bytes?:number;total_bytes?:number};
  uptime_seconds?:number;
};

function percent(value:unknown){
  const n=Number(value);
  return Number.isFinite(n)?Math.max(0,Math.min(100,n)):null;
}

function formatUptime(value:number|undefined){
  if(!Number.isFinite(Number(value)))return "—";
  const total=Math.max(0,Math.floor(Number(value)));
  const days=Math.floor(total/86400);
  const hours=Math.floor((total%86400)/3600);
  return days>0?`${days}d ${hours}h`:`${hours}h`;
}

function Resource({label,value}:{label:string;value:number|null}){
  const safe=value??0;
  return <div className="dash-server-resource">
    <div><span>{label}</span><b>{value==null?"—":`${Math.round(value)}%`}</b></div>
    <i><em style={{width:`${safe}%`}}/></i>
  </div>;
}

export function AdminDashboardServerCard(){
  const {pick}=useI18n();
  const [health,setHealth]=useState<SystemHealth|null>(null);
  const [mount,setMount]=useState<HTMLElement|null>(null);

  useEffect(()=>{
    let created:HTMLElement|null=null;
    const attach=()=>{
      const kpis=document.querySelector<HTMLElement>(".dash27 .dash27-kpis");
      if(!kpis||!kpis.parentElement)return false;
      const existing=document.querySelector<HTMLElement>(".dash27-server-host");
      if(existing){setMount(existing);return true;}
      created=document.createElement("section");
      created.className="dash27-server-host";
      kpis.insertAdjacentElement("afterend",created);
      setMount(created);
      return true;
    };
    if(!attach()){
      const observer=new MutationObserver(()=>{if(attach())observer.disconnect();});
      observer.observe(document.body,{childList:true,subtree:true});
      return ()=>{observer.disconnect();if(created?.isConnected)created.remove();};
    }
    return ()=>{if(created?.isConnected)created.remove();};
  },[]);

  useEffect(()=>{
    const token=getCustomerToken();
    if(!token)return;
    let active=true;
    const load=async()=>{
      try{
        const response=await fetch(`${API_BASE}/v1/admin/system-health`,{
          headers:{Authorization:`Bearer ${token}`},cache:"no-store"
        });
        if(!response.ok)return;
        const payload=await response.json() as SystemHealth;
        if(active)setHealth(payload);
      }catch{}
    };
    void load();
    const timer=window.setInterval(()=>void load(),15000);
    return ()=>{active=false;window.clearInterval(timer);};
  },[]);

  if(!mount)return null;
  const cpu=percent(health?.cpu?.percent);
  const ram=percent(health?.memory?.percent);
  const disk=percent(health?.disk?.percent);

  return createPortal(
    <div className="dash-server-card">
      <div className="dash-server-head">
        <h2>{pick("سرور","Server")}</h2>
        <b>{health?.hostname||"—"}</b>
      </div>
      <div className="dash-server-grid">
        <Resource label="CPU" value={cpu}/>
        <Resource label="RAM" value={ram}/>
        <Resource label="Disk" value={disk}/>
        <div className="dash-server-uptime"><span>Uptime</span><b>{formatUptime(health?.uptime_seconds)}</b></div>
      </div>
    </div>,
    mount
  );
}
