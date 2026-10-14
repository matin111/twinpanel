"use client";

import {FormEvent,useEffect,useState} from "react";
import {Badge,Card,Shell,Stat} from "./ui";
import {adminApi,AdminNode} from "../lib/admin-api";
import {AnyRow,parityApi,ProvisionInstallPayload,ProvisionProtocolSettings} from "../lib/admin-parity-api";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";


type ProvisionDraft=ProvisionInstallPayload&{
  xray_domain:string;
};

type XrayDomainState={
  ok?:boolean;
  node_id?:number;
  xray_domain?:string|null;
  effective_xray_domain?:string|null;
  legacy_public_domain_fallback?:boolean;
  public_domain?:string|null;
  tls_enabled?:boolean;
  available_profiles?:string[];
  message?:string;
};


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

const defaultInstall:ProvisionDraft={
  host:"",
  port:22,
  username:"root",
  password:"",
  name:"",
  node_type:"exit",
  country_code:"DE",
  capacity_users:1000,
  xray_domain:"",
  ...defaultProtocols,
};


function Notice({error,warning,ok}:{error:string;warning:string;ok:string}){
  return <>
    {error&&<div className="runtime-error">{error}</div>}
    {warning&&<div className="runtime-warning">{warning}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}
  </>;
}

function Toggle({label,checked,onChange}:{label:string;checked:boolean;onChange:(value:boolean)=>void}){
  return <label className="toggle module-toggle"><span>{label}</span><input type="checkbox" checked={checked} onChange={e=>onChange(e.target.checked)}/><i/></label>;
}

function StatusBadge({value}:{value:unknown}){
  const s=String(value||"unknown").toLowerCase();
  return <Badge tone={["online","active","ok","healthy","paired"].includes(s)?"ok":["offline","failed","error","revoked"].includes(s)?"bad":"warn"}>{String(value||"—")}</Badge>;
}

function errorText(payload:unknown,status:number){
  if(payload&&typeof payload==="object"){
    const item=payload as {detail?:unknown;message?:unknown};
    if(typeof item.detail==="string")return item.detail;
    if(typeof item.message==="string")return item.message;
    if(item.detail&&typeof item.detail==="object"&&"message" in item.detail)return String((item.detail as {message:unknown}).message);
  }
  return `API error ${status}`;
}

async function xrayRequest<T>(path:string,init:RequestInit={}):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const headers=new Headers(init.headers);
  headers.set("Authorization",`Bearer ${token}`);
  if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store"});
  let payload:unknown=null;
  try{payload=await response.json();}catch{}
  if(!response.ok)throw new Error(errorText(payload,response.status));
  return payload as T;
}

const getXrayDomain=(nodeId:number)=>xrayRequest<XrayDomainState>(`/v1/xray-modern-admin/nodes/${nodeId}/xray-domain`);
const saveXrayDomain=(nodeId:number,domain:string)=>xrayRequest<XrayDomainState>(`/v1/xray-modern-admin/nodes/${nodeId}/xray-domain`,{method:"PUT",body:JSON.stringify({domain})});
const prepareXrayDomain=(nodeId:number)=>xrayRequest<XrayDomainState>(`/v1/xray-modern-admin/nodes/${nodeId}/xray-domain/prepare`,{method:"POST",body:JSON.stringify({issue_certificate:true})});


export function ProvisionRuntimeXrayDomainPage(){
  const {pick}=useI18n();
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [draft,setDraft]=useState<ProvisionDraft>(defaultInstall);
  const [selected,setSelected]=useState(0);
  const [result,setResult]=useState<unknown>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [warning,setWarning]=useState("");
  const [ok,setOk]=useState("");
  const [selectedXrayDomain,setSelectedXrayDomain]=useState("");
  const [selectedXrayMeta,setSelectedXrayMeta]=useState<XrayDomainState|null>(null);

  const load=async()=>{
    setError("");
    try{
      const data=await adminApi.nodes();
      setNodes(data);
      setSelected(current=>current&&data.some(row=>row.id===current)?current:(data[0]?.id||0));
    }catch(e){setError(e instanceof Error?e.message:String(e));}
  };

  useEffect(()=>{void load();},[]);

  useEffect(()=>{
    if(!selected){setSelectedXrayDomain("");setSelectedXrayMeta(null);return;}
    const node=nodes.find(row=>row.id===selected);
    if(!node||node.node_type!=="exit"){setSelectedXrayDomain("");setSelectedXrayMeta(null);return;}
    let active=true;
    getXrayDomain(selected).then(data=>{
      if(!active)return;
      setSelectedXrayMeta(data);
      setSelectedXrayDomain(String(data.xray_domain||""));
    }).catch(()=>{
      if(active){setSelectedXrayMeta(null);setSelectedXrayDomain("");}
    });
    return()=>{active=false;};
  },[selected,nodes]);

  const act=async(label:string,fn:()=>Promise<unknown>,refresh=true)=>{
    if(busy)return;
    setBusy(true);setError("");setWarning("");setOk("");
    try{
      const out=await fn();
      setResult(out);
      setOk(label);
      if(refresh)await load();
      return out;
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  const setProtocol=(key:keyof ProvisionProtocolSettings,value:boolean|number|string)=>setDraft(current=>({...current,[key]:value} as ProvisionDraft));

  const submit=(e:FormEvent)=>{
    e.preventDefault();
    void act(
      pick("نود نصب شد","Node installed"),
      async()=>{
        const {xray_domain,...installPayload}=draft;
        const provisionResult=await parityApi.provisionInstall(installPayload);
        const output=provisionResult as AnyRow;
        const nodeId=Number(output.node_id||0);
        const domain=xray_domain.trim();

        if(
          nodeId>0
          && draft.node_type==="exit"
          && draft.install_v2ray
          && domain
        ){
          try{
            const saved=await saveXrayDomain(nodeId,domain);
            let prepared:XrayDomainState|null=null;
            let prepareWarning="";
            try{
              prepared=await prepareXrayDomain(nodeId);
            }catch(prepareError){
              prepareWarning=prepareError instanceof Error?prepareError.message:String(prepareError);
              setWarning(pick(
                `نود نصب شد و دامنه Xray ذخیره شد، اما SSL هنوز آماده نشد: ${prepareWarning}`,
                `Node installed and Xray domain saved, but TLS preparation is not ready yet: ${prepareWarning}`,
              ));
            }
            return {...output,xray_domain_setup:{saved,prepared,warning:prepareWarning||null}};
          }catch(domainError){
            const message=domainError instanceof Error?domainError.message:String(domainError);
            setWarning(pick(
              `نود نصب شد، اما ثبت دامنه Xray کامل نشد: ${message}`,
              `Node installed, but saving the Xray domain did not complete: ${message}`,
            ));
            return {...output,xray_domain_setup:{ok:false,error:message}};
          }
        }

        return output;
      },
    );
  };

  const saveExistingDomain=async(prepare:boolean)=>{
    if(!selected||busy)return;
    setBusy(true);setError("");setWarning("");setOk("");
    try{
      const saved=await saveXrayDomain(selected,selectedXrayDomain.trim());
      setSelectedXrayMeta(saved);
      if(prepare&&selectedXrayDomain.trim()){
        try{
          const prepared=await prepareXrayDomain(selected);
          setSelectedXrayMeta(current=>({...current,...prepared}));
          setOk(pick("دامنه Xray ذخیره و TLS آماده شد.","Xray domain saved and TLS prepared."));
        }catch(e){
          setWarning(pick(
            `دامنه ذخیره شد، اما آماده‌سازی TLS کامل نشد: ${e instanceof Error?e.message:String(e)}`,
            `Domain saved, but TLS preparation did not complete: ${e instanceof Error?e.message:String(e)}`,
          ));
        }
      }else{
        setOk(pick("دامنه Xray ذخیره شد.","Xray domain saved."));
      }
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  };

  const selectedNode=nodes.find(n=>n.id===selected);
  const showNewXrayDomain=draft.node_type==="exit"&&draft.install_v2ray;

  return <Shell active="/admin/provision"><div className="page">
    <div className="page-head"><div><h1>{pick("راه‌اندازی نود","Node Provisioning")}</h1></div><button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
    <Notice error={error} warning={warning} ok={ok}/>

    <div className="stats dashboard-stats">
      <Stat label={pick("نودها","Nodes")} value={String(nodes.length)} icon="▦"/>
      <Stat label={pick("آنلاین","Online")} value={String(nodes.filter(n=>String(n.status).toLowerCase()==="online").length)}/>
      <Stat label={pick("ایران","Iran")} value={String(nodes.filter(n=>n.node_type==="iran").length)}/>
      <Stat label={pick("خروجی","Exit")} value={String(nodes.filter(n=>n.node_type==="exit").length)}/>
    </div>

    <div className="module-grid two">
      <Card>
        <div className="card-head"><div><b>{pick("نصب نود جدید","Install new node")}</b><small>{pick("Provision امن با مدیریت خودکار پروتکل‌ها","Secure provisioning with automatic protocol management")}</small></div></div>
        <form onSubmit={submit}>
          <div className="setting-grid">
            <label className="field"><span>{pick("نام نود","Node name")}</span><input required value={draft.name} onChange={e=>setDraft(d=>({...d,name:e.target.value}))}/></label>
            <label className="field"><span>IP / Host</span><input required dir="ltr" value={draft.host} onChange={e=>setDraft(d=>({...d,host:e.target.value}))}/></label>
            <label className="field"><span>{pick("نوع","Type")}</span><select value={draft.node_type} onChange={e=>setDraft(d=>({...d,node_type:e.target.value as "iran"|"exit",country_code:e.target.value==="iran"?"IR":d.country_code==="IR"?"DE":d.country_code,xray_domain:e.target.value==="iran"?"":d.xray_domain}))}><option value="iran">Iran</option><option value="exit">Exit</option></select></label>
            <label className="field"><span>{pick("کشور","Country")}</span><input dir="ltr" maxLength={2} value={draft.country_code} onChange={e=>setDraft(d=>({...d,country_code:e.target.value.toUpperCase()}))}/></label>
            <label className="field"><span>SSH Port</span><input type="number" min={1} max={65535} value={draft.port} onChange={e=>setDraft(d=>({...d,port:Number(e.target.value)}))}/></label>
            <label className="field"><span>SSH Username</span><input dir="ltr" value={draft.username} onChange={e=>setDraft(d=>({...d,username:e.target.value}))}/></label>
            <label className="field"><span>SSH Password</span><input type="password" autoComplete="new-password" value={draft.password} onChange={e=>setDraft(d=>({...d,password:e.target.value}))}/></label>
            <label className="field"><span>{pick("ظرفیت کاربر","User capacity")}</span><input type="number" min={1} value={draft.capacity_users} onChange={e=>setDraft(d=>({...d,capacity_users:Number(e.target.value)}))}/></label>
            {showNewXrayDomain&&<label className="field span-two"><span>{pick("دامنه V2Ray / Xray","V2Ray / Xray domain")}</span><input dir="ltr" value={draft.xray_domain} onChange={e=>setDraft(d=>({...d,xray_domain:e.target.value}))} placeholder="xray.example.com"/><small>{pick("مستقل از دامنه عمومی نود؛ برای WebSocket TLS و HTTPUpgrade TLS. برای SSL خودکار، DNS باید به IP همین نود خروجی اشاره کند.","Independent from the Node public domain; used by WebSocket TLS and HTTPUpgrade TLS. For automatic TLS, DNS must point to this Exit node IP.")}</small></label>}
          </div>

          <div className="runtime-choice-section"><b>{pick("پروتکل‌ها و پورت‌ها","Protocols & ports")}</b><div className="protocol-toggle-grid">
            <Toggle label="Cisco / OpenConnect" checked={draft.install_cisco} onChange={v=>setProtocol("install_cisco",v)}/>
            <label className="field"><span>Cisco Port</span><input type="number" min={1} max={65535} value={draft.cisco_port} onChange={e=>setProtocol("cisco_port",Number(e.target.value))}/></label>
            <Toggle label="OpenVPN" checked={draft.install_openvpn} onChange={v=>setProtocol("install_openvpn",v)}/>
            <label className="field"><span>OpenVPN</span><div className="inline-fields"><input type="number" min={1} max={65535} value={draft.openvpn_port} onChange={e=>setProtocol("openvpn_port",Number(e.target.value))}/><select value={draft.openvpn_transport} onChange={e=>setProtocol("openvpn_transport",e.target.value)}><option value="udp">UDP</option><option value="tcp">TCP</option></select></div></label>
            <Toggle label="WireGuard" checked={draft.install_wireguard} onChange={v=>setProtocol("install_wireguard",v)}/>
            <label className="field"><span>WireGuard Port</span><input type="number" min={1} max={65535} value={draft.wireguard_port} onChange={e=>setProtocol("wireguard_port",Number(e.target.value))}/></label>
            <Toggle label="L2TP / IPsec" checked={draft.install_l2tp} onChange={v=>setProtocol("install_l2tp",v)}/>
            <Toggle label="V2Ray / Xray" checked={draft.install_v2ray} onChange={v=>setProtocol("install_v2ray",v)}/>
            <label className="field"><span>Xray Port</span><input type="number" min={1} max={65535} value={draft.xray_port} onChange={e=>setProtocol("xray_port",Number(e.target.value))}/></label>
          </div></div>

          <div className="action-row">
            <button type="button" className="ghost" disabled={busy||!draft.host||!draft.password} onClick={()=>void act(pick("اتصال SSH موفق بود","SSH connection passed"),()=>parityApi.provisionTest({host:draft.host,port:draft.port,username:draft.username,password:draft.password}),false)}>{pick("تست SSH","Test SSH")}</button>
            <button className="primary" disabled={busy||!draft.host||!draft.password||!draft.name}>{pick("نصب و راه‌اندازی","Install & Provision")}</button>
          </div>
        </form>
      </Card>

      <Card>
        <div className="card-head"><div><b>{pick("مدیریت نود موجود","Existing node operations")}</b><small>{pick("Health، Repair، Agent، Tunnel Fabric و دامنه Xray","Health, repair, agent, tunnel fabric and Xray domain")}</small></div></div>
        <label className="field"><span>{pick("نود","Node")}</span><select value={selected} onChange={e=>setSelected(Number(e.target.value))}>{nodes.map(n=><option key={n.id} value={n.id}>{n.name} · {n.public_ip} · {n.status}</option>)}</select></label>
        {selectedNode&&<div className="module-row"><div className="grow"><b>{selectedNode.name}</b><small dir="ltr">{selectedNode.public_ip}</small></div><StatusBadge value={selectedNode.status}/></div>}

        {selectedNode?.node_type==="exit"&&<div className="runtime-choice-section">
          <b>{pick("دامنه اختصاصی Xray","Dedicated Xray domain")}</b>
          <label className="field"><span>{pick("دامنه V2Ray / Xray","V2Ray / Xray domain")}</span><input dir="ltr" value={selectedXrayDomain} onChange={e=>setSelectedXrayDomain(e.target.value)} placeholder="xray.example.com"/></label>
          <div className="module-row"><div className="grow"><small>{pick("دامنه موثر","Effective domain")}</small><b dir="ltr">{selectedXrayMeta?.effective_xray_domain||"—"}</b></div>{selectedXrayMeta?.legacy_public_domain_fallback&&<Badge tone="warn">{pick("Fallback قدیمی","Legacy fallback")}</Badge>}{selectedXrayMeta?.tls_enabled&&<Badge tone="ok">TLS</Badge>}</div>
          <div className="action-row"><button type="button" className="ghost" disabled={busy} onClick={()=>void saveExistingDomain(false)}>{pick("ذخیره دامنه Xray","Save Xray domain")}</button><button type="button" className="primary" disabled={busy||!selectedXrayDomain.trim()} onClick={()=>void saveExistingDomain(true)}>{pick("ذخیره و آماده‌سازی SSL","Save & prepare TLS")}</button></div>
        </div>}

        <div className="action-grid">
          <button className="ghost" disabled={!selected||busy} onClick={()=>void act(pick("سلامت پروتکل‌ها دریافت شد","Protocol health loaded"),()=>parityApi.provisionProtocolHealth(selected))}>{pick("بررسی پروتکل‌ها","Protocol health")}</button>
          <button className="ghost" disabled={!selected||busy} onClick={()=>void act(pick("پروتکل‌ها تعمیر شدند","Protocols repaired"),()=>parityApi.provisionRepairSaved({node_id:selected,...defaultProtocols}))}>{pick("Repair پروتکل‌ها","Repair protocols")}</button>
          <button className="ghost" disabled={!selected||busy} onClick={()=>void act(pick("Agent ارتقا یافت","Agent upgraded"),()=>parityApi.provisionUpgradeAgent(selected))}>{pick("ارتقا Agent","Upgrade agent")}</button>
          <button className="ghost" disabled={!selected||busy} onClick={()=>void act(pick("Fabric نصب شد","Fabric installed"),()=>parityApi.provisionInstallFabric(selected))}>{pick("نصب Fabric","Install fabric")}</button>
          <button className="ghost" disabled={!selected||busy} onClick={()=>void act(pick("وضعیت Fabric دریافت شد","Fabric status loaded"),()=>parityApi.provisionFabricStatus(selected),false)}>{pick("وضعیت Fabric","Fabric status")}</button>
        </div>
      </Card>
    </div>

    {result!==null&&<Card><div className="card-head"><b>{pick("نتیجه عملیات","Operation result")}</b><button className="mini-btn" onClick={()=>setResult(null)}>×</button></div><pre className="runtime-log" dir="ltr">{JSON.stringify(result,null,2)}</pre></Card>}
  </div></Shell>;
}
