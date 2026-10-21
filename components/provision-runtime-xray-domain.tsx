"use client";

import {FormEvent,useEffect,useState} from "react";
import {Badge,Card,Shell} from "./ui";
import {adminApi,AdminNode} from "../lib/admin-api";
import {AnyRow,parityApi,ProvisionInstallPayload,ProvisionProtocolSettings} from "../lib/admin-parity-api";
import {useI18n} from "../lib/i18n";


type ProvisionDraft=ProvisionInstallPayload;

const noProtocols:ProvisionProtocolSettings={
  install_cisco:false,
  cisco_port:443,
  install_openvpn:false,
  openvpn_port:1194,
  openvpn_transport:"udp",
  install_wireguard:false,
  wireguard_port:51820,
  install_l2tp:false,
  install_v2ray:false,
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
  ...noProtocols,
};

function Notice({error,warning,ok}:{error:string;warning:string;ok:string}){
  return <>
    {error&&<div className="runtime-error">{error}</div>}
    {warning&&<div className="runtime-warning">{warning}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}
  </>;
}

function StatusBadge({value}:{value:unknown}){
  const state=String(value||"unknown").toLowerCase();
  return <Badge tone={["online","active","ok","healthy","paired"].includes(state)?"ok":["offline","failed","error","revoked"].includes(state)?"bad":"warn"}>{String(value||"—")}</Badge>;
}

export function ProvisionRuntimeXrayDomainPage(){
  const {pick}=useI18n();
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [draft,setDraft]=useState<ProvisionDraft>(defaultInstall);
  const [selected,setSelected]=useState(0);
  const [createdNodeId,setCreatedNodeId]=useState(0);
  const [result,setResult]=useState<unknown>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [warning,setWarning]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setError("");
    try{
      const data=await adminApi.nodes();
      setNodes(data);
      setSelected(current=>current&&data.some(row=>row.id===current)?current:(data[0]?.id||0));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
  };

  useEffect(()=>{void load();},[]);

  const act=async(label:string,fn:()=>Promise<unknown>,refresh=true)=>{
    if(busy)return;
    setBusy(true);setError("");setWarning("");setOk("");
    try{
      const out=await fn();
      setResult(out);
      setOk(label);
      if(refresh)await load();
      return out;
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const submit=(event:FormEvent)=>{
    event.preventDefault();
    if(busy)return;
    setBusy(true);setError("");setWarning("");setOk("");setCreatedNodeId(0);
    void parityApi.provisionInstall({
      ...draft,
      ...noProtocols,
    }).then(async output=>{
      const row=output as AnyRow;
      const nodeId=Number(row.node_id||0);
      setResult(output);
      setCreatedNodeId(Number.isFinite(nodeId)&&nodeId>0?nodeId:0);
      setOk(pick(
        "سرور ثبت و زیرساخت پایه آماده شد. پروتکل‌ها را از صفحه «پروتکل‌ها» نصب کنید.",
        "Server registered and base infrastructure prepared. Install protocols from the Protocols page.",
      ));
      setDraft(current=>({...defaultInstall,node_type:current.node_type,country_code:current.node_type==="iran"?"IR":"DE"}));
      await load();
    }).catch(reason=>{
      setError(reason instanceof Error?reason.message:String(reason));
    }).finally(()=>setBusy(false));
  };

  const selectedNode=nodes.find(node=>node.id===selected);
  const onlineNodes=nodes.filter(node=>String(node.status).toLowerCase()==="online").length;
  const iranNodes=nodes.filter(node=>node.node_type==="iran").length;
  const exitNodes=nodes.filter(node=>node.node_type==="exit").length;

  return <Shell active="/admin/provision"><div className="page">
    <div className="page-head">
      <div>
        <h1>{pick("افزودن سرور","Add server")}</h1>
        <small>{pick(
          "ابتدا فقط سرور و دسترسی امن آن ثبت می‌شود؛ نصب و تنظیم پروتکل‌ها از صفحه «پروتکل‌ها» انجام می‌شود.",
          "First register the server and its secure access; protocol installation and settings are managed from the Protocols page.",
        )}</small>
      </div>
      <button className="ghost" onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button>
    </div>

    <Notice error={error} warning={warning} ok={ok}/>

    {createdNodeId>0&&<Card>
      <div className="card-head">
        <div>
          <b>{pick("سرور آماده مدیریت است","Server is ready for management")}</b>
          <small>{pick("هیچ پروتکلی هنگام ثبت سرور به‌صورت خودکار نصب نشده است.","No access protocol was installed automatically while registering the server.")}</small>
        </div>
        <Badge tone="ok">#{createdNodeId}</Badge>
      </div>
      <div className="action-row">
        <a className="primary" href={`/admin/modern-protocols?node=${createdNodeId}`}>{pick("مدیریت پروتکل‌های این سرور","Manage this server's protocols")}</a>
        <a className="ghost" href="/admin/nodes">{pick("مشاهده نودها","View nodes")}</a>
      </div>
    </Card>}

    {result!==null&&<Card>
      <div className="card-head">
        <div><b>{pick("آخرین نتیجه عملیات","Latest operation result")}</b><small>{pick("جزئیات فنی برای Debug در صورت نیاز قابل مشاهده است.","Technical details remain available for debugging when needed.")}</small></div>
        <button className="mini-btn" onClick={()=>setResult(null)}>×</button>
      </div>
      <details className="runtime-choice-section">
        <summary>{pick("نمایش جزئیات فنی","Show technical details")}</summary>
        <pre className="runtime-log" dir="ltr">{JSON.stringify(result,null,2)}</pre>
      </details>
    </Card>}

    <Card>
      <div className="module-row">
        <div className="grow"><b>{pick("وضعیت نودها","Node status")}</b><small>{pick("خلاصه زیرساخت ثبت‌شده","Registered infrastructure summary")}</small></div>
        <Badge tone="warn">{pick("نودها","Nodes")} · {nodes.length}</Badge>
        <Badge tone="ok">{pick("آنلاین","Online")} · {onlineNodes}</Badge>
        <Badge tone="warn">{pick("ایران","Iran")} · {iranNodes}</Badge>
        <Badge tone="warn">{pick("خروجی","Exit")} · {exitNodes}</Badge>
      </div>
    </Card>

    <div className="module-grid two" style={{alignItems:"start"}}>
      <Card>
        <div className="card-head">
          <div>
            <b>{pick("ثبت سرور جدید","Register new server")}</b>
            <small>{pick("Node + SSH + Agent + Fabric؛ پروتکل‌ها جداگانه مدیریت می‌شوند.","Node + SSH + Agent + Fabric; protocols are managed separately.")}</small>
          </div>
        </div>
        <form onSubmit={submit}>
          <div className="setting-grid">
            <label className="field"><span>{pick("نام سرور","Server name")}</span><input required value={draft.name} onChange={event=>setDraft(current=>({...current,name:event.target.value}))}/></label>
            <label className="field"><span>IP / Host</span><input required dir="ltr" value={draft.host} onChange={event=>setDraft(current=>({...current,host:event.target.value}))}/></label>
            <label className="field"><span>{pick("نقش سرور","Server role")}</span><select value={draft.node_type} onChange={event=>setDraft(current=>({...current,node_type:event.target.value as "iran"|"exit",country_code:event.target.value==="iran"?"IR":current.country_code==="IR"?"DE":current.country_code}))}><option value="iran">Iran</option><option value="exit">Exit</option></select></label>
            <label className="field"><span>{pick("کشور","Country")}</span><input dir="ltr" maxLength={2} value={draft.country_code} onChange={event=>setDraft(current=>({...current,country_code:event.target.value.toUpperCase()}))}/></label>
            <label className="field"><span>SSH Port</span><input type="number" min={1} max={65535} value={draft.port} onChange={event=>setDraft(current=>({...current,port:Number(event.target.value)}))}/></label>
            <label className="field"><span>SSH Username</span><input dir="ltr" value={draft.username} onChange={event=>setDraft(current=>({...current,username:event.target.value}))}/></label>
            <label className="field"><span>SSH Password</span><input type="password" autoComplete="new-password" value={draft.password} onChange={event=>setDraft(current=>({...current,password:event.target.value}))}/></label>
            <label className="field"><span>{pick("ظرفیت کاربر","User capacity")}</span><input type="number" min={1} value={draft.capacity_users} onChange={event=>setDraft(current=>({...current,capacity_users:Number(event.target.value)}))}/></label>
          </div>

          <div className="runtime-warning">
            {pick(
              "پس از ثبت، برای Cisco/OpenConnect، OpenVPN، WireGuard، L2TP، V2Ray/Xray و پروتکل‌های مدرن وارد صفحه «پروتکل‌ها» شوید و فقط موارد موردنیاز این سرور را نصب کنید.",
              "After registration, open Protocols to install only the required Cisco/OpenConnect, OpenVPN, WireGuard, L2TP, V2Ray/Xray and modern protocols on this server.",
            )}
          </div>

          <div className="action-row">
            <button type="button" className="ghost" disabled={busy||!draft.host||!draft.password} onClick={()=>void act(pick("اتصال SSH موفق بود","SSH connection passed"),()=>parityApi.provisionTest({host:draft.host,port:draft.port,username:draft.username,password:draft.password}),false)}>{pick("تست SSH","Test SSH")}</button>
            <button className="primary" disabled={busy||!draft.host||!draft.password||!draft.name}>{busy?"…":pick("ثبت و آماده‌سازی سرور","Register & prepare server")}</button>
          </div>
        </form>
      </Card>

      <Card>
        <div className="card-head">
          <div>
            <b>{pick("نگهداری زیرساخت نود","Node infrastructure maintenance")}</b>
            <small>{pick("عملیات Agent و Tunnel Fabric؛ مدیریت پروتکل از این بخش خارج شده است.","Agent and Tunnel Fabric operations; protocol management has moved out of this section.")}</small>
          </div>
        </div>
        <label className="field"><span>{pick("نود","Node")}</span><select value={selected} onChange={event=>setSelected(Number(event.target.value))}>{nodes.map(node=><option key={node.id} value={node.id}>{node.name} · {node.public_ip} · {node.status}</option>)}</select></label>
        {selectedNode&&<div className="module-row"><div className="grow"><b>{selectedNode.name}</b><small dir="ltr">{selectedNode.public_ip}</small></div><StatusBadge value={selectedNode.status}/></div>}
        <div className="action-grid">
          {selectedNode?.node_type==="exit"&&<a className="primary" href={`/admin/modern-protocols?node=${selected}`}>{pick("مدیریت پروتکل‌ها","Manage protocols")}</a>}
          <button className="ghost" disabled={!selected||busy} onClick={()=>void act(pick("Agent ارتقا یافت","Agent upgraded"),()=>parityApi.provisionUpgradeAgent(selected))}>{pick("ارتقا Agent","Upgrade agent")}</button>
          <button className="ghost" disabled={!selected||busy} onClick={()=>void act(pick("Fabric نصب شد","Fabric installed"),()=>parityApi.provisionInstallFabric(selected))}>{pick("نصب / Repair Fabric","Install / repair Fabric")}</button>
          <button className="ghost" disabled={!selected||busy} onClick={()=>void act(pick("وضعیت Fabric دریافت شد","Fabric status loaded"),()=>parityApi.provisionFabricStatus(selected),false)}>{pick("وضعیت Fabric","Fabric status")}</button>
        </div>
      </Card>
    </div>
  </div></Shell>;
}
