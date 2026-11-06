"use client";

import {useEffect,useState} from "react";
import {
  adminApi,type XrayInboundDraft,type XrayInboundEditorState,
  type XrayInboundKey,type XrayInboundProfile,
} from "../lib/admin-api";
import {useI18n} from "../lib/i18n";
import styles from "./protocol-command-center.module.css";

const INBOUNDS:ReadonlyArray<{key:XrayInboundKey;label:string;detail:string}>= [
  {key:"tcp_tls",label:"VLESS · TCP + TLS",detail:"TCP / TLS"},
  {key:"ws_tls",label:"VLESS · WebSocket + TLS",detail:"WS / TLS"},
  {key:"xhttp_reality",label:"VLESS · XHTTP + REALITY",detail:"XHTTP / REALITY"},
];

export function XrayInboundEditorInProtocol({nodeId}:{nodeId:number}){
  const {pick}=useI18n();
  const [state,setState]=useState<XrayInboundEditorState|null>(null);
  const [draft,setDraft]=useState<XrayInboundDraft|null>(null);
  const [selected,setSelected]=useState<XrayInboundKey>("tcp_tls");
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");

  useEffect(()=>{
    let active=true;
    setState(null);setDraft(null);setError("");setNotice("");setSelected("tcp_tls");
    adminApi.xrayInboundEditor(nodeId).then(value=>{
      if(!active)return;
      setState(value);
      setDraft({
        ...value.defaults,...(value.draft||{}),
        inbounds:{
          ...value.defaults.inbounds,
          ...(value.draft?.inbounds||{}),
        } as Record<XrayInboundKey,XrayInboundProfile>,
      });
    }).catch(reason=>{if(active)setError(reason instanceof Error?reason.message:String(reason));});
    return()=>{active=false;};
  },[nodeId]);

  const profile=draft?.inbounds?.[selected];
  const edit=(key:keyof XrayInboundProfile,value:string)=>{
    setDraft(current=>{
      if(!current?.inbounds?.[selected])return current;
      const inbounds={...current.inbounds,[selected]:{...current.inbounds[selected],[key]:value}};
      const reality=inbounds.xhttp_reality;
      return {
        ...current,inbounds,
        reality_server_name:reality.server_name,
        reality_target:reality.target,
      };
    });
    setNotice("");
  };

  const save=async()=>{
    if(!draft||busy)return;
    setBusy("save");setError("");setNotice("");
    try{
      await adminApi.saveXrayInboundDraft(nodeId,draft);
      setNotice(pick("تنظیمات هر سه Inbound جداگانه ذخیره شد؛ هنوز روی سرور اعمال نشده‌اند.","All three inbound drafts saved independently; no server changes applied."));
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const apply=async()=>{
    if(!draft||busy)return;
    setBusy("apply");setError("");setNotice("");
    try{
      await adminApi.saveXrayInboundDraft(nodeId,draft);
      const result=await adminApi.applyXrayInboundDraft(nodeId);
      const updated=await adminApi.xrayInboundEditor(nodeId);
      setState(updated);
      setNotice(pick(
        "تنظیمات پشتیبانی‌شده هر سه Inbound اعمال و اعتبارسنجی شدند. تغییرات با دریافت مجدد ساب‌لینک نمایش داده می‌شوند.",
        "Supported settings for all three inbounds were applied and validated. The next subscription refresh reflects the change."
      )+" · "+result.reality_server_name);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy("");}
  };

  const field=(key:keyof XrayInboundProfile,label:string,placeholder:string)=>(
    <div className={styles.field}>
      <label>{label}</label>
      <input dir="ltr" value={profile?.[key]||""} placeholder={placeholder}
        onChange={event=>edit(key,event.target.value)}/>
    </div>
  );

  return <section className={styles.drawerSection}>
    <div className={styles.sectionHead}><div>
      <strong>{pick("ویرایش سه Inbound ویتوری","Edit three V2Ray inbounds")}</strong>
      <small>{pick("هر اتصال تنظیمات اختصاصی دارد؛ تغییر یک Inbound بقیه را عوض نمی‌کند.","Each inbound has its own settings; editing one does not modify the others.")}</small>
    </div></div>
    {error?<div className={styles.errorBox}>{error}</div>:null}
    {notice?<div className={styles.successBox}>{notice}</div>:null}
    {!draft||!profile?<div className={styles.readonlyRow}><span>{pick("در حال خواندن تنظیمات...","Loading inbounds...")}</span></div>:<>
      <div className={styles.presetGrid}>
        {INBOUNDS.map(item=><button key={item.key} type="button"
          className={`${styles.presetButton} ${selected===item.key?styles.presetButtonActive:""}`}
          disabled={Boolean(busy)} onClick={()=>{setSelected(item.key);setError("");setNotice("");}}>
          {item.label}
        </button>)}
      </div>
      <div className={styles.sectionHead}><div>
        <strong>{INBOUNDS.find(item=>item.key===selected)?.label}</strong>
        <small>{pick("تنظیمات همین Inbound","Settings for this inbound")}</small>
      </div></div>
      <div className={styles.formGrid}>
        {field("connection_domain",pick("دامنه اتصال","Connection domain"),"v2ray.example.com")}
        {field("server_name",selected==="xhttp_reality"?"REALITY / SNI":"TLS / SNI",
          selected==="xhttp_reality"?"www.varzesh3.com":"v2ray.example.com")}
        {selected!=="tcp_tls"?field("path",pick("مسیر","Path"),"/"):null}
        {selected==="xhttp_reality"?field("target",pick("مقصد REALITY","REALITY target"),"www.varzesh3.com:443"):null}
        <div className={styles.field}>
          <label>Transport</label>
          <input dir="ltr" value={profile.transport.toUpperCase()} disabled readOnly/>
        </div>
        <div className={styles.field}>
          <label>{pick("امنیت","Security")}</label>
          <input dir="ltr" value={profile.security.toUpperCase()} disabled readOnly/>
        </div>
      </div>
      <div className={styles.actionRow}>
        <button type="button" className={styles.primaryButton} disabled={Boolean(busy)} onClick={()=>void save()}>
          {busy==="save"?"…":pick("ذخیره تنظیمات سه Inbound","Save inbound drafts")}
        </button>
        <button type="button" className={styles.secondaryButton} disabled={Boolean(busy)} onClick={()=>void apply()}>
          {busy==="apply"?"…":pick("اعمال و تست سه Inbound","Apply & test inbounds")}
        </button>
      </div>
      <div className={styles.warningBox}>
        {pick("تغییر SNIهای TLS فقط با گواهی معتبر، و تغییر Path و REALITY فقط پس از اعتبارسنجی اعمال می‌شوند. تغییر دامنه اتصال و Transport فعلاً در وضعیت موجود باقی می‌مانند.",
          "TLS SNI requires a matching certificate; paths and REALITY require validation. Connection domain and transport remain unchanged.")}
      </div>
    </>}
  </section>;
}
