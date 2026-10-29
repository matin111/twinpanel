"use client";

import {getCustomerToken} from "./customer-api";

export type SmartTransportName=
  |"tp27_fast"
  |"spoof_wg"
  |"tp6_fast"
  |"kernel_ipip"
  |"kernel_vxlan"
  |"tp27_masque"
  |"tp27_tcp_direct"
  |"kernel_gre"
  |"gost_tun"
  |"amneziawg"
  |"netrix";

export type SmartTransportBenchmark={
  measured_at_epoch?:number;
  download_mbps?:number;
  upload_mbps?:number;
  weighted_mbps?:number;
  download_weight?:number;
  upload_weight?:number;
  streams?:number;
  source?:string;
};

export type SpoofWGConfiguration={
  iran_spoof_ip?:string;
  exit_spoof_ip?:string;
  send_transport?:string;
  recv_transport?:string;
  xdp?:boolean;
  configured?:boolean;
};

export type SpoofCompatibilityNode={
  node_id?:number;
  name?:string;
  public_ip?:string;
  raw_socket?:boolean;
  raw_socket_error?:string;
  tun_device?:boolean;
  wg_tools?:boolean;
  wireguard_kernel?:boolean;
  route_to_peer?:boolean;
  route_detail?:string;
  ping_peer?:boolean;
  ping_detail?:string;
  rp_filter_all?:string;
  ip_forward?:string;
  input_policy?:string;
  critical?:Record<string,boolean>;
  compatible?:boolean;
};

export type SpoofUnderlayVerdict=
  |"known_incompatible_active"
  |"known_incompatible_observed"
  |"qualified_online"
  |"eligible_unproven"
  |"configuration_required"
  |"prerequisite_blocked";

export type SpoofCompatibilityResult={
  ok?:boolean;
  tunnel_id:number;
  transport:"spoof_wg";
  mode?:string;
  active_transport?:string|null;
  preferred_transport?:string|null;
  production_path_unchanged?:boolean;
  core?:{
    ok?:boolean;
    version?:string;
    sha256?:string;
  };
  iran:SpoofCompatibilityNode;
  exit:SpoofCompatibilityNode;
  compatible:boolean;
  configured:boolean;
  ready_for_install:boolean;
  blockers:string[];
  source_spoofing_verified:false;
  limitation:string;
  preflight_version?:210;
  underlay_verdict?:SpoofUnderlayVerdict;
  underlay_reason?:string|null;
  underlay_evidence_source?:string;
  retry_blocked?:boolean;
  quarantine_until_epoch?:number|null;
};

export type SmartTransportCandidate={
  transport:SmartTransportName;
  label?:string;
  family?:string;
  iran_profile?:string;
  description?:string;
  enabled?:boolean;
  status?:string;
  latency_ms?:number|null;
  last_error?:string|null;
  last_healthy_at?:string|null;
  auto_managed?:boolean;
  qualified?:boolean;
  selectable?:boolean;
  manual_selectable?:boolean;
  manual_block_reason?:string|null;
  manual_selection_requires_fresh_probe?:boolean;
  stable_seconds?:number;
  required_stable_seconds?:number;
  auto_block_reason?:string|null;
  quarantine_until_epoch?:number|null;
  benchmark?:SmartTransportBenchmark|null;
  benchmark_fresh?:boolean;
  benchmark_age_seconds?:number|null;
  runtime?:Record<string,unknown>;
  configuration?:SpoofWGConfiguration;
  configured?:boolean;
  configuration_required?:boolean;
  auto_install?:boolean;
  encrypted?:boolean;
  upstream_version?:string;
  xdp?:boolean;
  [key:string]:unknown;
};

export type SmartTransportState={
  ok?:boolean;
  tunnel_id:number;
  mode?:string;
  active_transport?:string|null;
  preferred_transport?:string|null;
  production_default?:string;
  promotion_policy?:string;
  transports:SmartTransportCandidate[];
};

export type ModernProtocolInventoryItem={
  protocol:string;
  name?:string;
  category?:string;
  core?:string;
  adapter?:string;
  runtime_status?:string;
  installable?:boolean;
  port?:number;
  transport?:string;
  service?:string;
  status?:string;
  last_error?:string|null;
  checked_at?:string|null;
  [key:string]:unknown;
};

export type ModernProtocolInventoryNode={
  id:number;
  name?:string;
  public_ip?:string;
  public_domain?:string|null;
  status?:string;
  protocols?:ModernProtocolInventoryItem[];
};

export type ModernProtocolInventory={
  ok?:boolean;
  schema_version?:number;
  catalog?:unknown;
  nodes?:ModernProtocolInventoryNode[];
};

export const MODERN_TRANSPORT_AUTHORITY_REFRESH_EVENT="twinpanel-modern-transport-authority-refresh-v207";
export const SPOOF_UNDERLAY_REASON_V210="underlay_incompatible:reverse_carrier_not_reaching_iran";

function notifyAuthorityRefresh(){
  if(typeof window!=="undefined")window.dispatchEvent(new Event(MODERN_TRANSPORT_AUTHORITY_REFRESH_EVENT));
}

function requestBase(){
  if(typeof window!=="undefined")return window.location.origin;
  return "";
}

function errorText(payload:unknown,status:number){
  if(typeof payload==="string"&&payload.trim())return payload.trim();
  if(payload&&typeof payload==="object"){
    const value=payload as {detail?:unknown;message?:unknown};
    if(typeof value.message==="string")return value.message;
    if(typeof value.detail==="string")return value.detail;
    if(value.detail&&typeof value.detail==="object"){
      const detail=value.detail as {message?:unknown;error?:unknown};
      return [detail.message,detail.error].filter(Boolean).map(String).join(" — ")||`API error ${status}`;
    }
  }
  return `API error ${status}`;
}

async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${requestBase()}${path}`,{...init,headers,cache:"no-store"});
  const raw=await response.text();
  let payload:unknown=null;
  if(raw){try{payload=JSON.parse(raw);}catch{payload=raw;}}
  if(!response.ok)throw new Error(errorText(payload,response.status));
  return payload as T;
}

async function installTransport(tunnelId:number,transport:SmartTransportName){
  try{
    return await request<Record<string,unknown>>(`/v1/tunnels/${tunnelId}/modern-transports/${encodeURIComponent(transport)}/install`,{method:"POST"});
  }catch(reason){
    // V207: the install request can briefly expose the authoritative DB row as
    // `installing` while the server performs qualification. If that request
    // ultimately fails, force the Smart Transports surface to remount/refetch
    // immediately instead of leaving the mid-install snapshot visible until a
    // later polling interval.
    notifyAuthorityRefresh();
    throw reason;
  }
}

async function checkSpoofCompatibilityV210(tunnelId:number):Promise<SpoofCompatibilityResult>{
  // V210 is intentionally read-only. It combines the existing host-prerequisite
  // probe with persisted Spoof candidate evidence. It does not install/repair a
  // transport, open a new carrier, forge source addresses, or mutate node state.
  const [prerequisite,state]=await Promise.all([
    request<SpoofCompatibilityResult>(`/v1/tunnels/${tunnelId}/modern-transports/spoof_wg/compatibility-check`,{method:"POST"}),
    request<SmartTransportState>(`/v1/tunnels/${tunnelId}/modern-transports`),
  ]);

  const row=(state.transports||[]).find(item=>String(item.transport||"").trim().toLowerCase()==="spoof_wg");
  const status=String(row?.status||"").trim().toLowerCase();
  const lastError=String(row?.last_error||"");
  const autoBlock=String(row?.auto_block_reason||"");
  const evidenceObserved=lastError.includes(SPOOF_UNDERLAY_REASON_V210)||autoBlock.includes(SPOOF_UNDERLAY_REASON_V210);

  const quarantineRaw=Number(row?.quarantine_until_epoch||0);
  const quarantineUntil=Number.isFinite(quarantineRaw)&&quarantineRaw>0?quarantineRaw:null;
  const quarantineActive=Boolean(quarantineUntil&&quarantineUntil>Date.now()/1000);
  const online=Boolean(row?.enabled&&status==="online");

  let verdict:SpoofUnderlayVerdict;
  let evidenceSource="host_prerequisites_only";

  if(!prerequisite.compatible){
    verdict="prerequisite_blocked";
    evidenceSource="host_prerequisites";
  }else if(evidenceObserved&&quarantineActive){
    verdict="known_incompatible_active";
    evidenceSource="v206_v208_failure_evidence";
  }else if(evidenceObserved){
    verdict="known_incompatible_observed";
    evidenceSource="v206_v208_failure_evidence";
  }else if(online){
    verdict="qualified_online";
    evidenceSource="existing_online_candidate";
  }else if(!prerequisite.configured){
    verdict="configuration_required";
    evidenceSource="configuration";
  }else{
    verdict="eligible_unproven";
  }

  const knownIncompatible=evidenceObserved;
  const blockers=Array.from(new Set([
    ...(Array.isArray(prerequisite.blockers)?prerequisite.blockers:[]),
    ...(knownIncompatible?[SPOOF_UNDERLAY_REASON_V210]:[]),
  ]));

  return {
    ...prerequisite,
    compatible:Boolean(prerequisite.compatible)&&!knownIncompatible,
    ready_for_install:Boolean(prerequisite.ready_for_install)&&!knownIncompatible,
    blockers,
    preflight_version:210,
    underlay_verdict:verdict,
    underlay_reason:knownIncompatible?SPOOF_UNDERLAY_REASON_V210:null,
    underlay_evidence_source:evidenceSource,
    retry_blocked:Boolean(knownIncompatible&&quarantineActive),
    quarantine_until_epoch:quarantineUntil,
    limitation:[
      prerequisite.limitation,
      "V210 also checks persisted V206/V208 failure evidence before the UI labels this pair Ready.",
      "A pair with eligible_unproven status has passed host prerequisites only; this read-only preflight does not generate spoofed traffic and cannot prove an untested provider underlay compatible.",
    ].filter(Boolean).join(" "),
  };
}

export const modernTransportApi={
  state:(tunnelId:number)=>request<SmartTransportState>(`/v1/tunnels/${tunnelId}/modern-transports`),
  protocolInventory:()=>request<ModernProtocolInventory>("/v1/settings/vpn/modern-protocols"),
  probe:(tunnelId:number,transport:SmartTransportName)=>request<Record<string,unknown>>(`/v1/tunnels/${tunnelId}/modern-transports/${encodeURIComponent(transport)}/probe`,{method:"POST"}),
  install:installTransport,
  remove:(tunnelId:number,transport:SmartTransportName)=>request<Record<string,unknown>>(`/v1/tunnels/${tunnelId}/modern-transports/${encodeURIComponent(transport)}`,{method:"DELETE"}),
  configureSpoof:(tunnelId:number,configuration:{iran_spoof_ip:string;exit_spoof_ip:string})=>request<Record<string,unknown>>(`/v1/tunnels/${tunnelId}/modern-transports/spoof_wg/config`,{method:"PUT",body:JSON.stringify(configuration)}),
  checkSpoofCompatibility:checkSpoofCompatibilityV210,
  setMode:(tunnelId:number,mode:"auto"|"manual",transport?:string)=>{
    if(mode==="manual"&&transport){
      return request<Record<string,unknown>>(`/v1/tunnels/${tunnelId}/modern-transports/${encodeURIComponent(transport)}/select-manual`,{method:"POST"});
    }
    return request<Record<string,unknown>>(`/v1/tunnels/${tunnelId}/transport-mode`,{method:"POST",body:JSON.stringify({mode})});
  },
};
