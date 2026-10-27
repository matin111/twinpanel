"use client";

import type {AdminTunnel} from "./admin-api";
import {getCustomerToken} from "./customer-api";

// TWINPANEL_SERVER_PAIR_SELECTION_NO_INSTALL_V293
// This client is deliberately single-purpose. Server selection must only
// register/reuse the logical Iran -> Exit pair. It must never fall back to
// create-managed or any transport installer/repair endpoint.

export type ServerPairSelectionInput={
  iran_node_id:number;
  exit_node_id:number;
  priority?:number;
};

function errorText(payload:unknown,status:number){
  if(typeof payload==="string"&&payload.trim())return payload.trim();
  if(payload&&typeof payload==="object"){
    const item=payload as {detail?:unknown;message?:unknown};
    if(typeof item.detail==="string")return item.detail;
    if(typeof item.message==="string")return item.message;
    if(item.detail&&typeof item.detail==="object"){
      const detail=item.detail as {message?:unknown;error?:unknown};
      return [detail.message,detail.error].filter(Boolean).map(String).join(" — ")||`API error ${status}`;
    }
  }
  return `API error ${status}`;
}

async function selectServerPair(payload:ServerPairSelectionInput):Promise<AdminTunnel>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");

  const response=await fetch("/v1/tunnels/register",{
    method:"POST",
    headers:{
      "Authorization":`Bearer ${token}`,
      "Content-Type":"application/json",
    },
    body:JSON.stringify({
      iran_node_id:Number(payload.iran_node_id),
      exit_node_id:Number(payload.exit_node_id),
      priority:Number(payload.priority||100),
      transport:"ssh_tun",
      is_active:false,
    }),
    cache:"no-store",
  });

  const raw=await response.text();
  let body:unknown=null;
  if(raw){try{body=JSON.parse(raw);}catch{body=raw;}}
  if(!response.ok)throw new Error(errorText(body,response.status));
  return body as AdminTunnel;
}

export const tunnelServerPairApi={select:selectServerPair};
