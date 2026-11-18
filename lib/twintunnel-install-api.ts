"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";

export type TwinTunnelNodeCheck={
  node_id:number;
  name?:string;
  ok:boolean;
  revision?:string;
  mode?:string;
  selftest?:string;
  error?:string|null;
};

export type TwinTunnelInstallStatus={
  tunnel_id:number;
  engine:"twintunnel_udp_mux";
  status:"staged"|"not_staged";
  revision:string;
  installed_revision?:string|null;
  needs_update:boolean;
  backup_node_id?:number|null;
  nodes:TwinTunnelNodeCheck[];
  carrier_plan?:Array<{carrier:string;port:number}>;
  carrier_count?:number;
  carrier_state?:"not_installed";
  traffic_activated?:false;
  active_transport?:string|null;
  production_activated:false;
  can_activate:false;
  deployment_mode:"isolated_stage_only";
  reason:string;
  staged_at?:string|null;
};

async function request(path:string,method:"GET"|"POST"="GET",body?:object):Promise<TwinTunnelInstallStatus>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const base=typeof window!=="undefined"?window.location.origin:API_BASE;
  const response=await fetch(base+path,{
    method,
    headers:{"Authorization":"Bearer "+token,...(body?{"Content-Type":"application/json"}:{})},
    body:body?JSON.stringify(body):undefined,
    cache:"no-store",
  });
  const text=await response.text();
  let result:unknown=null;
  try{result=text?JSON.parse(text):null;}catch{result=text;}
  if(!response.ok){
    let error="TwinTunnel API error ("+response.status+")";
    if(typeof result==="string")error=result.slice(0,250);
    if(result&&typeof result==="object"&&"detail" in result){
      const detail=(result as {detail:unknown}).detail;
      error=typeof detail==="string"?detail:
        detail&&typeof detail==="object"&&"message" in detail
          ?String((detail as {message:unknown}).message):error;
      if(detail&&typeof detail==="object"&&"nodes" in detail){
        const nodes=(detail as {nodes?:unknown}).nodes;
        if(Array.isArray(nodes)){
          const failed=nodes.filter((n):n is {node_id?:number;name?:string;error?:string;ok?:boolean}=>
            Boolean(n)&&typeof n==="object"&&(n as {ok?:boolean}).ok===false);
          if(failed.length)error+=" — "+failed.map(n=>
            "Node #"+String(n.node_id||"?")+": "+String(n.error||"check failed").slice(0,80)).join("; ");
        }
      }
    }
    throw new Error(error);
  }
  return result as TwinTunnelInstallStatus;
}

export const twinTunnelInstallApi={
  status:(tunnelId:number)=>request("/v1/tunnels/"+tunnelId+"/twintunnel-install"),
  install:(tunnelId:number,backupNodeId?:number)=>
    request("/v1/tunnels/"+tunnelId+"/twintunnel-install","POST",{
      backup_node_id:backupNodeId||null,
      mode:"install",
    }),
  verify:(tunnelId:number,backupNodeId?:number)=>
    request("/v1/tunnels/"+tunnelId+"/twintunnel-install","POST",{
      backup_node_id:backupNodeId||null,
      mode:"verify",
    }),
};
