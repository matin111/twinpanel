"use client";

import {useEffect,useState} from "react";
import {adminApi,type XrayInboundDraft,type XrayInboundEditorState} from "../lib/admin-api";
import {useI18n} from "../lib/i18n";
import styles from "./protocol-command-center.module.css";

export function XrayInboundEditorInProtocol({nodeId}:{nodeId:number}){
  const {pick}=useI18n();
  const [state,setState]=useState<XrayInboundEditorState|null>(null);
  const [draft,setDraft]=useState<XrayInboundDraft|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");

  useEffect(()=>{
    let active=true;
    setState(null);setDraft(null);setError("");setNotice("");
    adminApi.xrayInboundEditor(nodeId).then(value=>{
      if(!active)return;
      setState(value);setDraft(value.draft||value.defaults);
    }).catch(reason=>{if(active)setError(reason instanceof Error?reason.message:String(reason));});
    return()=>{active=false;};
  },[nodeId]);

  const save=async()=>{
    if(!draft||busy)return;
    setBusy(true);setError("");setNotice("");
    try{
      await adminApi.saveXrayInboundDraft(nodeId,draft);
      const updated=await adminApi.xrayInboundEditor(nodeId);
      setState(updated);setDraft(updated.draft||updated.defaults);
      setNotice(pick("تنظیمات به‌عنوان پیش‌نویس ذخیره شد؛ هنوز روی سرور یا ساب‌لینک اعمال نشده است.","Saved as a draft; the server and subscription links are unchanged."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const apply=async()=>{
    if(!draft||busy)return;
    setBusy(true);setError("");setNotice("");
    try{
      // Save the visible draft first; the server then validates the exact version.
      await adminApi.saveXrayInboundDraft(nodeId,draft);
      const result=await adminApi.applyXrayInboundDraft(nodeId);
      const updated=await adminApi.xrayInboundEditor(nodeId);
      setState(updated);setDraft(updated.draft||updated.defaults);
      setNotice(pick(
        "اعمال و تست REALITY موفق بود؛ ساب‌لینک‌ها از SNI جدید استفاده می‌کنند. TLS و Transport تغییر نکردند.",
        "REALITY apply and test passed; subscription SNI is updated. TLS and transport were not changed."
      )+" · "+result.reality_server_name);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const field=(key:keyof Pick<XrayInboundDraft,"connection_domain"|"tls_server_name"|"reality_server_name"|"reality_target">,label:string,placeholder:string)=>(
    <div className={styles.field} key={key}>
      <label>{label}</label>
      <input dir="ltr" value={draft?.[key]||""} placeholder={placeholder}
        onChange={event=>setDraft(current=>current?{...current,[key]:event.target.value}:current)}/>
    </div>
  );

  return <section className={styles.drawerSection}>
    <div className={styles.sectionHead}><div>
      <strong>{pick("Inbound ویتوری · تنظیمات پیشرفته","V2Ray inbound · Advanced settings")}</strong>
      <small>{pick("مانند سنایی؛ تنظیمات مستقل برای هر نود خروجی","3x-ui-style settings for each exit node")}</small>
    </div></div>
    {error?<div className={styles.errorBox}>{error}</div>:null}
    {notice?<div className={styles.successBox}>{notice}</div>:null}
    {!draft?<div className={styles.readonlyRow}><span>{pick("دریافت تنظیمات...","Loading settings...")}</span></div>:<>
      <div className={styles.formGrid}>
        {field("connection_domain",pick("دامنه اتصال","Connection domain"),"v2ray.example.com")}
        {field("tls_server_name","TLS / SNI","v2ray.example.com")}
        {field("reality_server_name","REALITY / SNI","www.varzesh3.com")}
        {field("reality_target",pick("مقصد REALITY","REALITY target"),"www.varzesh3.com:443")}
        <div className={styles.field}><label>Transport</label>
          <select value={draft.transport} onChange={event=>setDraft(current=>current?{...current,transport:event.target.value}:current)}>
            {(state?.transports||["tcp","ws","xhttp","grpc","httpupgrade"]).map(item=><option key={item} value={item}>{item.toUpperCase()}</option>)}
          </select>
        </div>
        <div className={styles.field}><label>{pick("نوع امنیت","Security")}</label>
          <select value={draft.security} onChange={event=>setDraft(current=>current?{...current,security:event.target.value}:current)}>
            {(state?.securities||["tls","reality"]).map(item=><option key={item} value={item}>{item.toUpperCase()}</option>)}
          </select>
        </div>
      </div>
      <div className={styles.actionRow}>
        <button type="button" className={styles.primaryButton} disabled={busy} onClick={()=>void save()}>
          {busy?"…":pick("ذخیره پیش‌نویس","Save draft")}
        </button>
        <button type="button" className={styles.secondaryButton} disabled={busy} onClick={()=>void apply()}>
          {busy?"…":pick("اعمال و تست REALITY","Apply & test REALITY")}
        </button>
      </div>
      <div className={styles.warningBox}>{pick("اعمال فعلاً فقط REALITY SNI و مقصد را روی Xray و ساب‌لینک‌ها هماهنگ می‌کند. دامنه اتصال، TLS و نوع Transport فقط پیش‌نویس می‌مانند.","Apply synchronizes REALITY SNI and target with Xray and subscriptions. Connection domain, TLS and transport remain drafts.")}</div>
    </>}
  </section>;
}
