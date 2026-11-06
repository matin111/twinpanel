"use client";

import {useEffect,useMemo,useState} from "react";

import {adminApi,type AdminNode,type XrayDomainState,type XrayInboundDraft,type XrayInboundEditorState} from "../lib/admin-api";
import {Badge,Card} from "./ui";
import {useI18n} from "../lib/i18n";

const clean=(value:unknown)=>String(value??"").trim();

export function NodeXrayDomainRuntimeV33(){
  const {pick}=useI18n();
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [selectedId,setSelectedId]=useState(0);
  const [domain,setDomain]=useState("");
  const [meta,setMeta]=useState<XrayDomainState|null>(null);
  const [inbound,setInbound]=useState<XrayInboundEditorState|null>(null);
  const [inboundDraft,setInboundDraft]=useState<XrayInboundDraft|null>(null);
  const [inboundBusy,setInboundBusy]=useState(false);
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
  useEffect(()=>{
    let cancelled=false;
    setInbound(null);setInboundDraft(null);
    if(!selectedId)return;
    adminApi.xrayInboundEditor(selectedId).then(state=>{
      if(cancelled)return;
      setInbound(state);
      setInboundDraft(state.draft||state.defaults);
    }).catch(reason=>{
      if(!cancelled)setError(reason instanceof Error?reason.message:String(reason));
    });
    return()=>{cancelled=true;};
  },[selectedId]);

  const saveInbound=async()=>{
    if(!selectedId||!inboundDraft||inboundBusy)return;
    setInboundBusy(true);setError("");setOk("");
    try{
      await adminApi.saveXrayInboundDraft(selectedId,inboundDraft);
      const current=await adminApi.xrayInboundEditor(selectedId);
      setInbound(current);setInboundDraft(current.draft||current.defaults);
      setOk(pick("پیش‌نویس تنظیمات ذخیره شد. برای اعمال روی سرور هنوز انتشار امن لازم است.","Inbound draft saved. Safe server apply is still required."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setInboundBusy(false);}
  };

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
    {selected&&inboundDraft?<Card>
      <div className="card-head">
        <div>
          <b>{pick("تنظیمات پیشرفته Inbound ویتوری","Advanced V2Ray inbound settings")}</b>
          <small>{pick("مشابه ویرایشگر سنایی: تنظیمات پیش‌فرض قابل تغییرند. ذخیره پیش‌نویس باعث تغییر لینک یا ریستارت Xray نمی‌شود.","3x-ui-style editor: drafts are editable. Saving does not change live links or restart Xray.")}</small>
        </div>
        <Badge tone="warn">{pick("پیش‌نویس، اعمال‌نشده","Draft / not applied")}</Badge>
      </div>
      <div className="setting-grid">
        {([
          ["connection_domain",pick("دامنه اتصال","Connection domain"),"v2ray.example.com"],
          ["tls_server_name",pick("دامنه TLS / SNI","TLS domain / SNI"),"v2ray.example.com"],
          ["reality_server_name",pick("REALITY Server Name / SNI","REALITY Server Name / SNI"),"www.varzesh3.com"],
          ["reality_target",pick("مقصد REALITY","REALITY target"),"www.varzesh3.com:443"],
        ] as const).map(([key,title,placeholder])=><label key={key} className="field">
          <span>{title}</span>
          <input dir="ltr" value={inboundDraft[key]} placeholder={placeholder} onChange={event=>setInboundDraft(current=>current?{...current,[key]:event.target.value}:current)}/>
        </label>)}
        <label className="field">
          <span>{pick("نوع اتصال / Transport","Transport")}</span>
          <select value={inboundDraft.transport} onChange={event=>setInboundDraft(current=>current?{...current,transport:event.target.value}:current)}>
            {(inbound?.transports||["tcp","ws","xhttp","grpc","httpupgrade"]).map(value=><option key={value} value={value}>{value.toUpperCase()}</option>)}
          </select>
        </label>
        <label className="field">
          <span>{pick("امنیت اتصال","Security")}</span>
          <select value={inboundDraft.security} onChange={event=>setInboundDraft(current=>current?{...current,security:event.target.value}:current)}>
            {(inbound?.securities||["tls","reality"]).map(value=><option key={value} value={value}>{value.toUpperCase()}</option>)}
          </select>
        </label>
      </div>
      <div className="action-row">
        <button type="button" className="primary" disabled={inboundBusy||Boolean(busy)} onClick={()=>void saveInbound()}>
          {inboundBusy?"…":pick("ذخیره پیش‌نویس","Save draft")}
        </button>
      </div>
      <small>{pick("فعال‌سازی تنظیمات پس از تست سرور، اعتبارسنجی Xray و تطبیق ساب‌لینک انجام می‌شود؛ فعلاً این فرم فقط پیش‌نویس را نگه می‌دارد.","Activation requires server validation and subscription reconciliation; this form saves drafts only.")}</small>
    </Card>:null}
  </div>;
}
