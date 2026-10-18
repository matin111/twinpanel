"use client";

import {useEffect,useMemo,useState} from "react";

import {adminApi,type AdminNode,type XrayDomainState} from "../lib/admin-api";
import {Badge,Card} from "./ui";
import {useI18n} from "../lib/i18n";

const clean=(value:unknown)=>String(value??"").trim();

export function NodeXrayDomainRuntimeV33(){
  const {pick}=useI18n();
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [selectedId,setSelectedId]=useState(0);
  const [domain,setDomain]=useState("");
  const [meta,setMeta]=useState<XrayDomainState|null>(null);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const exits=useMemo(
    ()=>nodes.filter(node=>String(node.node_type||"").toLowerCase()==="exit"&&Boolean(node.enable_v2ray)),
    [nodes],
  );

  const selected=exits.find(node=>node.id===selectedId)||null;

  const loadNodes=async()=>{
    setLoading(true);
    setError("");
    try{
      const rows=await adminApi.nodes();
      setNodes(rows);
      const available=rows.filter(node=>String(node.node_type||"").toLowerCase()==="exit"&&Boolean(node.enable_v2ray));
      setSelectedId(current=>current&&available.some(node=>node.id===current)?current:(available[0]?.id||0));
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setLoading(false);
    }
  };

  const loadDomain=async(nodeId:number)=>{
    if(!nodeId){setMeta(null);setDomain("");return;}
    setError("");
    try{
      const state=await adminApi.xrayDomain(nodeId);
      setMeta(state);
      setDomain(clean(state.xray_domain));
    }catch(reason){
      setMeta(null);
      setDomain("");
      setError(reason instanceof Error?reason.message:String(reason));
    }
  };

  useEffect(()=>{void loadNodes();},[]);
  useEffect(()=>{void loadDomain(selectedId);},[selectedId]);

  const save=async(prepare:boolean)=>{
    if(!selected||busy)return;
    setBusy(prepare?"prepare":"save");
    setError("");
    setOk("");
    try{
      const saved=await adminApi.saveXrayDomain(selected.id,domain.trim());
      setMeta(saved);
      if(prepare&&domain.trim()){
        const prepared=await adminApi.prepareXrayDomain(selected.id,true);
        setMeta(current=>({...current,...prepared}));
        setOk(pick("دامنه اختصاصی Xray ذخیره شد و آماده‌سازی TLS انجام شد.","Dedicated Xray domain saved and TLS preparation completed."));
      }else{
        setOk(pick("دامنه اختصاصی Xray ذخیره شد.","Dedicated Xray domain saved."));
      }
      await loadDomain(selected.id);
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy("");
    }
  };

  if(!loading&&exits.length===0)return null;

  return <div className="page legacy-control-page xray-domain-node-v33">
    <Card>
      <div className="card-head">
        <div>
          <b>{pick("دامنه اختصاصی V2Ray / Xray","Dedicated V2Ray / Xray domain")}</b>
          <small>{pick("این دامنه از دامنه عمومی نود مستقل است و برای WebSocket TLS، HTTPUpgrade TLS و VLESS TCP TLS استفاده می‌شود.","This domain is independent from the Node public domain and is used for WebSocket TLS, HTTPUpgrade TLS and VLESS TCP TLS.")}</small>
        </div>
        <div className="action-row">
          {meta?.legacy_public_domain_fallback?<Badge tone="warn">{pick("Fallback دامنه عمومی","Public-domain fallback")}</Badge>:null}
          {meta?.tls_enabled?<Badge tone="ok">TLS</Badge>:null}
          <button type="button" className="ghost" disabled={loading||Boolean(busy)} onClick={()=>void loadNodes()}>{pick("بروزرسانی","Refresh")}</button>
        </div>
      </div>

      {error?<div className="runtime-error">{error}</div>:null}
      {ok?<div className="runtime-success">{ok}</div>:null}
      {loading?<div className="runtime-loading">{pick("در حال دریافت نودهای Xray...","Loading Xray nodes...")}</div>:null}

      {exits.length>0?<div className="setting-grid">
        <label className="field">
          <span>{pick("نود خروجی","Exit node")}</span>
          <select value={selectedId} onChange={event=>setSelectedId(Number(event.target.value))}>
            {exits.map(node=><option key={node.id} value={node.id}>{node.name} · {node.public_ip||"—"}</option>)}
          </select>
        </label>
        <label className="field span-two">
          <span>{pick("دامنه V2Ray / Xray","V2Ray / Xray domain")}</span>
          <input dir="ltr" value={domain} onChange={event=>setDomain(event.target.value)} placeholder="xray.example.com"/>
          <small>{pick("DNS باید به IP همین نود خروجی اشاره کند. ذخیره این مقدار دامنه عمومی نود را تغییر نمی‌دهد.","DNS must point to this Exit node IP. Saving this value does not change the Node public domain.")}</small>
        </label>
      </div>:null}

      {selected?<div className="runtime-info-list">
        <div><span>{pick("IP نود","Node IP")}</span><b dir="ltr">{selected.public_ip||"—"}</b></div>
        <div><span>{pick("دامنه موثر Xray","Effective Xray domain")}</span><b dir="ltr">{meta?.effective_xray_domain||"—"}</b></div>
      </div>:null}

      {selected?<div className="action-row">
        <button type="button" className="ghost" disabled={Boolean(busy)} onClick={()=>void save(false)}>{busy==="save"?"…":pick("ذخیره دامنه Xray","Save Xray domain")}</button>
        <button type="button" className="primary" disabled={Boolean(busy)||!domain.trim()} onClick={()=>void save(true)}>{busy==="prepare"?"…":pick("ذخیره و آماده‌سازی TLS","Save & prepare TLS")}</button>
      </div>:null}
    </Card>
  </div>;
}
