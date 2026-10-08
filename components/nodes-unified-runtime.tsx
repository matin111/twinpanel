"use client";

import {FormEvent,useState} from "react";
import {LegacyNodesRuntimePage} from "./legacy-nodes-exact";
import {parityApi,ProvisionInstallPayload,ProvisionProtocolSettings} from "../lib/admin-parity-api";
import {useI18n} from "../lib/i18n";

const defaultProtocols:ProvisionProtocolSettings={
  install_cisco:true,
  cisco_port:443,
  install_openvpn:true,
  openvpn_port:1194,
  openvpn_transport:"udp",
  install_wireguard:true,
  wireguard_port:51820,
  install_l2tp:true,
  install_v2ray:true,
  xray_port:8443,
};

const defaultInstall:ProvisionInstallPayload={
  host:"",
  port:22,
  username:"root",
  password:"",
  name:"",
  node_type:"exit",
  country_code:"DE",
  capacity_users:1000,
  ...defaultProtocols,
};

type AnyResult=Record<string,unknown>;

function Toggle({label,checked,onChange,disabled=false}:{label:string;checked:boolean;onChange:(value:boolean)=>void;disabled?:boolean}){
  return <label className="toggle module-toggle"><span>{label}</span><input type="checkbox" checked={checked} disabled={disabled} onChange={e=>onChange(e.target.checked)}/><i/></label>;
}

function ProvisionModal({onClose,onInstalled}:{onClose:()=>void;onInstalled:()=>void}){
  const {pick}=useI18n();
  const [draft,setDraft]=useState<ProvisionInstallPayload>(defaultInstall);
  const [busy,setBusy]=useState<""|"test"|"install">("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [result,setResult]=useState<AnyResult|null>(null);

  const setProtocol=(key:keyof ProvisionProtocolSettings,value:boolean|number|string)=>setDraft(current=>({...current,[key]:value} as ProvisionInstallPayload));

  const setNodeType=(value:"iran"|"exit")=>{
    setDraft(current=>({
      ...current,
      node_type:value,
      country_code:value==="iran"?"IR":current.country_code==="IR"?"DE":current.country_code,
      ...(value==="iran"?{
        install_cisco:false,
        install_openvpn:false,
        install_wireguard:false,
        install_l2tp:false,
        install_v2ray:false,
      }:{}),
    }));
  };

  const testSsh=async()=>{
    if(busy||!draft.host.trim()||!draft.password)return;
    setBusy("test");setError("");setOk("");setResult(null);
    try{
      const out=await parityApi.provisionTest({host:draft.host.trim(),port:draft.port,username:draft.username.trim()||"root",password:draft.password});
      setResult(out);
      setOk(pick(`اتصال SSH موفق بود${out.hostname?` · ${String(out.hostname)}`:""}`,`SSH connection passed${out.hostname?` · ${String(out.hostname)}`:""}`));
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  const submit=async(e:FormEvent)=>{
    e.preventDefault();
    if(busy)return;
    if(!draft.name.trim()||!draft.host.trim()||!draft.password){setError(pick("نام نود، IP/Host و رمز SSH الزامی است.","Node name, IP/Host and SSH password are required."));return;}

    setBusy("install");setError("");setOk("");setResult(null);
    try{
      const payload:ProvisionInstallPayload={
        ...draft,
        name:draft.name.trim(),
        host:draft.host.trim(),
        username:draft.username.trim()||"root",
        country_code:(draft.node_type==="iran"?"IR":draft.country_code.trim().toUpperCase()||"DE"),
      };
      const out=await parityApi.provisionInstall(payload) as AnyResult;
      setResult(out);

      const nodeId=Number(out.node_id||0);
      const complete=out.ok!==false;
      if(nodeId>0){
        onInstalled();
        setOk(complete
          ?pick(`نود با موفقیت اضافه و راه‌اندازی شد · ID ${nodeId}`,`Node added and provisioned successfully · ID ${nodeId}`)
          :pick(`نود ثبت شد · ID ${nodeId} — بخشی از سرویس‌ها نیاز به بررسی دارد.`,`Node registered · ID ${nodeId} — some services need attention.`));
      }else{
        setOk(pick("عملیات راه‌اندازی تکمیل شد.","Provisioning completed."));
      }
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy("");}
  };

  const isIran=draft.node_type==="iran";

  return <div className="runtime-modal" role="dialog" aria-modal="true">
    <button className="runtime-modal-bg" onClick={()=>!busy&&onClose()}/>
    <div className="runtime-modal-card wide">
      <div className="card-head"><div><b>{pick("افزودن و راه‌اندازی نود","Add & Provision Node")}</b></div><button type="button" className="icon-button" disabled={!!busy} onClick={onClose}>×</button></div>
      {error&&<div className="runtime-error">{error}</div>}
      {ok&&<div className="runtime-success">{ok}</div>}

      <form onSubmit={submit}>
        <div className="setting-grid">
          <label className="field"><span>{pick("نام نود","Node name")}</span><input required value={draft.name} onChange={e=>setDraft(d=>({...d,name:e.target.value}))}/></label>
          <label className="field"><span>IP / Host</span><input required dir="ltr" value={draft.host} onChange={e=>setDraft(d=>({...d,host:e.target.value}))}/></label>
          <label className="field"><span>{pick("نوع نود","Node type")}</span><select value={draft.node_type} onChange={e=>setNodeType(e.target.value as "iran"|"exit")}><option value="iran">Iran</option><option value="exit">Exit</option></select></label>
          <label className="field"><span>{pick("کشور","Country")}</span><input dir="ltr" maxLength={2} disabled={isIran} value={draft.country_code} onChange={e=>setDraft(d=>({...d,country_code:e.target.value.toUpperCase()}))}/></label>
          <label className="field"><span>SSH Port</span><input type="number" min={1} max={65535} value={draft.port} onChange={e=>setDraft(d=>({...d,port:Number(e.target.value)||22}))}/></label>
          <label className="field"><span>SSH Username</span><input dir="ltr" value={draft.username} onChange={e=>setDraft(d=>({...d,username:e.target.value}))}/></label>
          <label className="field"><span>SSH Password</span><input required dir="ltr" type="password" autoComplete="new-password" value={draft.password} onChange={e=>setDraft(d=>({...d,password:e.target.value}))}/></label>
          <label className="field"><span>{pick("ظرفیت کاربر","User capacity")}</span><input type="number" min={1} value={draft.capacity_users} onChange={e=>setDraft(d=>({...d,capacity_users:Number(e.target.value)||1}))}/></label>
        </div>

        {!isIran&&<div className="runtime-choice-section"><b>{pick("پروتکل‌ها و پورت‌ها","Protocols & ports")}</b><div className="protocol-toggle-grid">
          <Toggle label="Cisco / OpenConnect" checked={draft.install_cisco} onChange={v=>setProtocol("install_cisco",v)}/>
          <label className="field"><span>Cisco Port</span><input type="number" min={1} max={65535} value={draft.cisco_port} onChange={e=>setProtocol("cisco_port",Number(e.target.value))}/></label>
          <Toggle label="OpenVPN" checked={draft.install_openvpn} onChange={v=>setProtocol("install_openvpn",v)}/>
          <label className="field"><span>OpenVPN</span><div className="inline-fields"><input type="number" min={1} max={65535} value={draft.openvpn_port} onChange={e=>setProtocol("openvpn_port",Number(e.target.value))}/><select value={draft.openvpn_transport} onChange={e=>setProtocol("openvpn_transport",e.target.value)}><option value="udp">UDP</option><option value="tcp">TCP</option></select></div></label>
          <Toggle label="WireGuard" checked={draft.install_wireguard} onChange={v=>setProtocol("install_wireguard",v)}/>
          <label className="field"><span>WireGuard Port</span><input type="number" min={1} max={65535} value={draft.wireguard_port} onChange={e=>setProtocol("wireguard_port",Number(e.target.value))}/></label>
          <Toggle label="L2TP / IPsec" checked={draft.install_l2tp} onChange={v=>setProtocol("install_l2tp",v)}/>
          <Toggle label="V2Ray / Xray" checked={draft.install_v2ray} onChange={v=>setProtocol("install_v2ray",v)}/>
          <label className="field"><span>Xray Port</span><input type="number" min={1} max={65535} value={draft.xray_port} onChange={e=>setProtocol("xray_port",Number(e.target.value))}/></label>
        </div></div>}

        {result&&<div className="runtime-log" dir="ltr">{JSON.stringify(result,null,2)}</div>}

        <div className="runtime-modal-actions">
          <button type="button" className="ghost" disabled={!!busy} onClick={onClose}>{pick("بستن","Close")}</button>
          <button type="button" className="ghost" disabled={!!busy||!draft.host.trim()||!draft.password} onClick={()=>void testSsh()}>{busy==="test"?pick("در حال تست…","Testing…"):pick("تست SSH","Test SSH")}</button>
          <button type="submit" className="primary" disabled={!!busy||!draft.host.trim()||!draft.password||!draft.name.trim()}>{busy==="install"?pick("در حال نصب و راه‌اندازی…","Installing & provisioning…"):pick("نصب و راه‌اندازی","Install & Provision")}</button>
        </div>
      </form>
    </div>
  </div>;
}

export function NodesUnifiedRuntimePage({openProvisionInitially=false}:{openProvisionInitially?:boolean}){
  const [showProvision,setShowProvision]=useState(openProvisionInitially);
  const [pageKey,setPageKey]=useState(0);

  const captureProvisionLink=(event:React.MouseEvent<HTMLDivElement>)=>{
    const target=event.target;
    if(!(target instanceof Element))return;
    const link=target.closest('a[href="/admin/provision"]');
    if(!link)return;
    event.preventDefault();
    event.stopPropagation();
    setShowProvision(true);
  };

  return <div onClickCapture={captureProvisionLink}>
    <LegacyNodesRuntimePage key={pageKey}/>
    {showProvision&&<ProvisionModal onClose={()=>setShowProvision(false)} onInstalled={()=>setPageKey(key=>key+1)}/>} 
  </div>;
}
