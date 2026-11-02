"use client";

import {API_BASE} from "./api";
import {getCustomerToken} from "./customer-api";
import type {AdminNode} from "./admin-api";

export async function updateNodeIdentity(
  id:number,
  payload:{name:string;country_code:string},
):Promise<AdminNode>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const response=await fetch(`${API_BASE}/v1/nodes/${id}`,{
    method:"PATCH",
    headers:{
      Authorization:`Bearer ${token}`,
      "Content-Type":"application/json",
    },
    body:JSON.stringify(payload),
    cache:"no-store",
  });
  const text=await response.text();
  let parsed:unknown=null;
  try{parsed=text?JSON.parse(text):null;}catch{parsed=text;}
  if(!response.ok){
    if(parsed&&typeof parsed==="object"&&"detail" in parsed){
      throw new Error(String((parsed as {detail:unknown}).detail));
    }
    throw new Error(typeof parsed==="string"&&parsed?parsed:`API error ${response.status}`);
  }
  return parsed as AdminNode;
}
