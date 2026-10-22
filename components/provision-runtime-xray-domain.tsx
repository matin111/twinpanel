"use client";

import {FormEvent,useEffect,useMemo,useState} from "react";

import {Badge,Card,Shell} from "./ui";
import {adminApi,type AdminNode} from "../lib/admin-api";
import {parityApi,type AnyRow,type ProvisionInstallPayload} from "../lib/admin-parity-api";
import {legacyAdminApi} from "../lib/legacy-admin-api";
import {useI18n} from "../lib/i18n";


type NodeDraft={
  host:string;
  port:number;
  username:string;
  password:string;
  name:string;
  node_type:"iran"|"exit";
  country_code:string;
  capacity_users:number;
};

type BaselineState="idle"|"ready"|"failed";

const defaultDraft:NodeDraft={
  host:"",
  port:22,
  username:"root",
  password:"",
  name:"",
  node_type:"exit",
  country_code:"DE",
  capacity_users:1000,
};

const NO_PROTOCOLS={
  install_cisco:false,
  cisco_port:443,
  install_openvpn:false,
  openvpn_port:1194,
  openvpn_transport:"udp" as const,
  install_wireguard:false,
  wireguard_port:51820,
  install_l2tp:false,
  install_v2ray:false,
  xray_port:8443,
};

function buildInstallPayload(draft:NodeDraft):ProvisionInstallPayload{
  return {
    ...draft,
    country_code:draft.node_type==="iran"?"IR":draft.country_code.trim().toUpperCase(),
    ...NO_PROTOCOLS,
  };
}

function Notice({error,warning,ok}:{error:string;warning:string;ok:string}){
  return <>
    {error&&<div className="runtime-error">{error}</div>}
    {warning&&<div className="runtime-warning">{warning}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}
  </>;
}

function StatusBadge({value}:{value:unknown}){
  const state=String(value||"unknown").toLowerCase();
  return <Badge tone={["online","active","ok","healthy"].includes(state)?"ok":["offline","failed","error"].includes(state)?"bad":"warn"}>{String(value||"—")}</Badge>;
}

export function ProvisionRuntimeXrayDomainPage(){
  const {pick}=useI18n();
  const [nodes,setNodes]=useState<AdminNode[]>([]);
  const [draft,setDraft]=useState<NodeDraft>(defaultDraft);
  const [result,setResult]=useState<AnyRow|null>(null);
  const [createdNodeId,setCreatedNodeId]=useState(0);
  const [createdNodeType,setCreatedNodeType]=useState<NodeDraft["node_type"]|null>(null);
  const [baselineV2ray,setBaselineV2ray]=useState<BaselineState>("idle");
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [warning,setWarning]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setError("");
    try{
      setNodes(await adminApi.nodes());
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }
  };

  useEffect(()=>{void load();},[]);

  const stats=useMemo(()=>({
    total:nodes.length,
    online:nodes.filter(node=>String(node.status).toLowerCase()==="online").length,
    iran:nodes.filter(node=>node.node_type==="iran").length,
    exit:nodes.filter(node=>node.node_type==="exit").length,
  }),[nodes]);

  const testConnection=async()=>{
    if(busy)return;
    setBusy("test");
    setError("");setWarning("");setOk("");
    try{
      const out=await parityApi.provisionTest({
        host:draft.host.trim(),
        port:draft.port,
        username:draft.username.trim()||"root",
        password:draft.password,
      });
      setResult(out);
      setOk(pick("اتصال SSH و سیستم‌عامل سرور تایید شد.","SSH connection and server OS verified."));
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy("");
    }
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();
    if(busy)return;
    const requestedNodeType=draft.node_type;
    setBusy("register");
    setError("");setWarning("");setOk("");
    setCreatedNodeId(0);
    setCreatedNodeType(null);
    setBaselineV2ray("idle");
    try{
      const output=await parityApi.provisionInstall(buildInstallPayload({
        ...draft,
        host:draft.host.trim(),
        username:draft.username.trim()||"root",
        name:draft.name.trim(),
      })) as AnyRow;
      setResult(output);
      const nodeId=Number(output.node_id||0);
      const validNodeId=Number.isFinite(nodeId)&&nodeId>0?nodeId:0;
      setCreatedNodeId(validNodeId);
      setCreatedNodeType(requestedNodeType);

      const failed=Array.isArray(output.failed_protocols)
        ? output.failed_protocols.map(String)
        : [];
      const baseNeedsAttention=output.ok===false||failed.length>0;
      let v2rayError="";

      if(requestedNodeType==="exit"){
        if(validNodeId){
          try{
            const v2rayRuntime=await legacyAdminApi.ensureClassicProtocol({
              node_id:validNodeId,
              protocol:"v2ray",
              port:NO_PROTOCOLS.xray_port,
            }) as AnyRow;
            setBaselineV2ray("ready");
            setResult({...output,v2ray_baseline:v2rayRuntime} as AnyRow);
          }catch(reason){
            v2rayError=reason instanceof Error?reason.message:String(reason);
            setBaselineV2ray("failed");
            setResult({...output,v2ray_baseline:{ok:false,error:v2rayError}} as AnyRow);
          }
        }else{
          v2rayError=pick("شناسه نود بعد از ثبت دریافت نشد.","The registered node id was not returned.");
          setBaselineV2ray("failed");
          setResult({...output,v2ray_baseline:{ok:false,error:v2rayError}} as AnyRow);
        }
      }

      if(requestedNodeType==="exit"&&v2rayError){
        setWarning(pick(
          `سرور Exit ثبت شد، اما نصب/Health Check خودکار Xray کامل نشد: ${v2rayError}${baseNeedsAttention?" همچنین زیرساخت پایه نیاز به بررسی دارد.":""} از صفحه «پروتکل‌ها» Repair را اجرا کنید.`,
          `Exit server registered, but automatic Xray install/health check did not complete: ${v2rayError}${baseNeedsAttention?" Base infrastructure also needs attention.":""} Run Repair from Protocol Studio.`,
        ));
      }else if(baseNeedsAttention){
        setWarning(pick(
          `سرور ثبت شد، اما بخشی از زیرساخت پایه نیاز به بررسی دارد${failed.length?`: ${failed.join(", ")}`:""}.${requestedNodeType==="exit"?" Xray با مسیر رسمی Protocol Studio نصب و Health Check شد.":""}`,
          `The server was registered, but part of the base infrastructure needs attention${failed.length?`: ${failed.join(", ")}`:""}.${requestedNodeType==="exit"?" Xray was installed and health-checked through the canonical Protocol Studio path.":""}`,
        ));
      }else if(requestedNodeType==="exit"){
        setOk(pick(
          "سرور Exit ثبت شد، دسترسی امن و Agent آماده شدند و Xray با مسیر رسمی Protocol Studio نصب و Health Check شد. سایر پروتکل‌ها را از صفحه «پروتکل‌ها» مدیریت کنید.",
          "Exit server registered with secure access and Agent ready; Xray was installed and health-checked through the canonical Protocol Studio path. Manage other protocols from Protocol Studio.",
        ));
      }else{
        setOk(pick(
          "سرور ایران ثبت شد و زیرساخت پایه آماده است. پروتکل‌های سرویس‌دهنده روی Exit از صفحه «پروتکل‌ها» مدیریت می‌شوند.",
          "Iran server registered with base infrastructure ready. Service protocols on Exit nodes are managed from Protocol Studio.",
        ));
      }

      setDraft(current=>({...current,password:""}));
      await load();
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{
      setBusy("");
    }
  };

  return <Shell active="/admin/provision">
    <div className="page legacy-control-page">
      <div className="page-head">
        <div>
          <h1>{pick("افزودن سرور","Add server")}</h1>
          <small>{pick(
            "این صفحه نود، SSH و زیرساخت پایه را آماده می‌کند. برای Exit، Xray بعد از ثبت با همان مسیر رسمی Protocol Studio به‌صورت خودکار نصب و Health Check می‌شود؛ سایر پروتکل‌ها در صفحه «پروتکل‌ها» مدیریت می‌شوند.",
            "This page prepares the node, SSH access and base infrastructure. For Exit nodes, Xray is automatically installed and health-checked through the same canonical Protocol Studio path; other protocols remain managed in Protocol Studio.",
          )}</small>
        </div>
        <div className="action-row">
          <a className="primary-soft" href="/admin/modern-protocols">{pick("پروتکل‌ها","Protocols")}</a>
          <button type="button" className="ghost" disabled={Boolean(busy)} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button>
        </div>
      </div>

      <Notice error={error} warning={warning} ok={ok}/>

      {createdNodeId>0&&<Card>
        <div className="module-row">
          <div className="grow">
            <b>{pick(
              createdNodeType==="exit"&&baselineV2ray!=="ready"?"سرور ثبت شد؛ Xray نیاز به بررسی دارد":"سرور آماده مدیریت است",
              createdNodeType==="exit"&&baselineV2ray!=="ready"?"Server registered; Xray needs attention":"Server is ready for management",
            )}</b>
            <small>{pick(
              createdNodeType==="exit"
                ? baselineV2ray==="ready"
                  ? "Xray baseline با مسیر رسمی Protocol Studio نصب و Health Check شده است."
                  : "ثبت پایه انجام شد، اما Convergence خودکار Xray کامل نشده است."
                : "نود ایران به‌صورت زیرساخت پایه ثبت شده و پروتکل سرویس‌دهنده روی آن نصب نشده است.",
              createdNodeType==="exit"
                ? baselineV2ray==="ready"
                  ? "The Xray baseline was installed and health-checked through the canonical Protocol Studio path."
                  : "Base registration completed, but automatic Xray convergence did not complete."
                : "The Iran node was registered as base infrastructure without service protocol installation.",
            )}</small>
          </div>
          <a className="primary" href={`/admin/modern-protocols?node=${createdNodeId}`}>{pick("مدیریت پروتکل‌ها","Manage protocols")}</a>
        </div>
      </Card>}

      {result!==null&&<Card>
        <details className="runtime-choice-section">
          <summary>{pick("جزئیات فنی آخرین عملیات","Technical details of the latest operation")}</summary>
          <pre className="runtime-log" dir="ltr">{JSON.stringify(result,null,2)}</pre>
        </details>
      </Card>}

      <div className="stats dashboard-stats">
        <div className="stat"><span>{pick("کل نودها","Total nodes")}</span><b>{stats.total.toLocaleString("fa-IR")}</b></div>
        <div className="stat"><span>{pick("آنلاین","Online")}</span><b>{stats.online.toLocaleString("fa-IR")}</b></div>
        <div className="stat"><span>{pick("ایران","Iran")}</span><b>{stats.iran.toLocaleString("fa-IR")}</b></div>
        <div className="stat"><span>{pick("خروجی","Exit")}</span><b>{stats.exit.toLocaleString("fa-IR")}</b></div>
      </div>

      <div className="module-grid two" style={{alignItems:"start"}}>
        <Card>
          <div className="card-head">
            <div>
              <b>{pick("مشخصات سرور جدید","New server details")}</b>
              <small>{pick("ثبت نود + SSH Key + Agent + Quota/Fabric base","Node registration + SSH key + Agent + Quota/Fabric base")}</small>
            </div>
          </div>

          <div className="runtime-warning">
            {pick(
              "انتخاب و تنظیم پروتکل‌ها عمداً از این فرم حذف شده تا یک منبع تنظیم واحد داشته باشیم. برای Exit فقط Xray baseline پس از ثبت، با همان API رسمی Protocol Studio خودکار Converge می‌شود؛ Cisco/OpenConnect، OpenVPN، WireGuard، L2TP و پروتکل‌های جدید همچنان از Protocol Studio مدیریت می‌شوند.",
              "Protocol selection and settings stay out of this form so the panel keeps one source of truth. For Exit nodes only, the Xray baseline automatically converges after registration through the canonical Protocol Studio API; Cisco/OpenConnect, OpenVPN, WireGuard, L2TP and modern protocols remain managed in Protocol Studio.",
            )}
          </div>

          <form onSubmit={submit}>
            <div className="setting-grid">
              <label className="field">
                <span>{pick("نام سرور","Server name")}</span>
                <input required value={draft.name} onChange={event=>setDraft(current=>({...current,name:event.target.value}))}/>
              </label>
              <label className="field">
                <span>IP / Host</span>
                <input required dir="ltr" value={draft.host} onChange={event=>setDraft(current=>({...current,host:event.target.value}))}/>
              </label>
              <label className="field">
                <span>{pick("نوع نود","Node type")}</span>
                <select value={draft.node_type} onChange={event=>setDraft(current=>{
                  const node_type=event.target.value as "iran"|"exit";
                  return {...current,node_type,country_code:node_type==="iran"?"IR":current.country_code==="IR"?"DE":current.country_code};
                })}>
                  <option value="iran">Iran</option>
                  <option value="exit">Exit</option>
                </select>
              </label>
              <label className="field">
                <span>{pick("کشور","Country")}</span>
                <input dir="ltr" maxLength={2} disabled={draft.node_type==="iran"} value={draft.node_type==="iran"?"IR":draft.country_code} onChange={event=>setDraft(current=>({...current,country_code:event.target.value.toUpperCase()}))}/>
              </label>
              <label className="field">
                <span>SSH Port</span>
                <input type="number" min={1} max={65535} value={draft.port} onChange={event=>setDraft(current=>({...current,port:Number(event.target.value)||22}))}/>
              </label>
              <label className="field">
                <span>SSH Username</span>
                <input required dir="ltr" value={draft.username} onChange={event=>setDraft(current=>({...current,username:event.target.value}))}/>
              </label>
              <label className="field">
                <span>SSH Password</span>
                <input required type="password" autoComplete="new-password" value={draft.password} onChange={event=>setDraft(current=>({...current,password:event.target.value}))}/>
              </label>
              <label className="field">
                <span>{pick("ظرفیت کاربر","User capacity")}</span>
                <input type="number" min={1} value={draft.capacity_users} onChange={event=>setDraft(current=>({...current,capacity_users:Number(event.target.value)||1}))}/>
              </label>
            </div>

            <div className="action-row" style={{marginTop:16}}>
              <button type="button" className="ghost" disabled={Boolean(busy)||!draft.host.trim()||!draft.password} onClick={()=>void testConnection()}>{busy==="test"?"…":pick("تست SSH","Test SSH")}</button>
              <button type="submit" className="primary" disabled={Boolean(busy)}>{busy==="register"?"…":pick("ثبت و آماده‌سازی سرور","Register & prepare server")}</button>
            </div>
          </form>
        </Card>

        <Card>
          <div className="card-head">
            <div><b>{pick("جریان جدید مدیریت","New management flow")}</b><small>{pick("ساده‌تر، قابل‌ردیابی و بدون تنظیم تکراری","Simpler, traceable and without duplicated settings")}</small></div>
          </div>
          <div className="runtime-info-list">
            <div><span>1</span><b>{pick("ثبت سرور و SSH","Register server & SSH")}</b></div>
            <div><span>2</span><b>{pick("آماده‌سازی Agent و زیرساخت پایه","Prepare Agent & base infrastructure")}</b></div>
            <div><span>3</span><b>{pick("Converge خودکار Xray برای Exit","Automatic Xray convergence for Exit")}</b></div>
            <div><span>4</span><b>{pick("سایر پروتکل‌ها + Health / Repair از Protocol Studio","Other protocols + Health / Repair in Protocol Studio")}</b></div>
          </div>
          <a className="primary" style={{display:"inline-block",marginTop:14}} href="/admin/modern-protocols">{pick("باز کردن صفحه پروتکل‌ها","Open Protocol Studio")}</a>
        </Card>
      </div>

      <Card>
        <div className="card-head"><div><b>{pick("نودهای ثبت‌شده","Registered nodes")}</b><small>{pick("برای مدیریت سرویس‌ها به صفحه پروتکل‌ها بروید.","Manage services from Protocol Studio.")}</small></div></div>
        <div className="table"><table><thead><tr><th>{pick("نود","Node")}</th><th>{pick("نوع","Type")}</th><th>IP</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Action")}</th></tr></thead>
          <tbody>{nodes.map(node=><tr key={node.id}>
            <td><b>{node.name}</b></td>
            <td>{node.node_type||"—"}</td>
            <td dir="ltr">{node.public_ip||"—"}</td>
            <td><StatusBadge value={node.status}/></td>
            <td>{node.node_type==="exit"?<a className="primary-soft" href={`/admin/modern-protocols?node=${node.id}`}>{pick("پروتکل‌ها","Protocols")}</a>:<a className="ghost" href="/admin/nodes">{pick("مدیریت نود","Manage node")}</a>}</td>
          </tr>)}</tbody>
        </table></div>
      </Card>
    </div>
  </Shell>;
}
