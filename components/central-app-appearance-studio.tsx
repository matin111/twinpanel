"use client";

import {useEffect,useState,type CSSProperties} from "react";
import {appearanceApi,type AppAppearance,type AppearanceReseller} from "../lib/central-app-appearance-api";
import {useI18n} from "../lib/i18n";
import styles from "./central-app-appearance.module.css";

type Role="admin"|"reseller";
const DEFAULT:AppAppearance={
  primary_color:"#7C3AED",secondary_color:"#4F46E5",button_color:"#7C3AED",
  background_color:"#101018",surface_color:"#20202A",background_style:"gradient",
  background_image_url:null,theme_mode:"dark",
};
const PRESETS=[
  {name:["بنفش شب","Midnight violet"],colors:["#7C3AED","#4F46E5","#7C3AED","#101018","#20202A"]},
  {name:["آبی اقیانوسی","Ocean blue"],colors:["#2563EB","#0891B2","#2563EB","#0B1729","#16263B"]},
  {name:["سبز زمردی","Emerald"],colors:["#059669","#0D9488","#059669","#091E1B","#15312D"]},
  {name:["صورتی مدرن","Modern rose"],colors:["#DB2777","#7C3AED","#DB2777","#1B1020","#302137"]},
  {name:["روشن و مینیمال","Light minimal"],colors:["#4F46E5","#0891B2","#4F46E5","#F4F6FC","#FFFFFF"]},
] as const;
const COLOR_FIELDS=[
  ["primary_color","رنگ اصلی","Primary color"],
  ["secondary_color","رنگ ثانویه","Secondary color"],
  ["button_color","رنگ دکمه اتصال","Connect button"],
  ["background_color","رنگ پس‌زمینه","Background color"],
  ["surface_color","رنگ کارت‌ها","Card color"],
] as const;
const HEX=/^#[0-9a-fA-F]{6}$/;
const safe=(color:string,fallback:string)=>HEX.test(color)?color:fallback;
const brightness=(hex:string)=>{const v=safe(hex,"#101018");const parts=[1,3,5].map(i=>parseInt(v.slice(i,i+2),16));return (parts[0]*299+parts[1]*587+parts[2]*114)/1000;};

export function CentralAppAppearanceStudio({role}:{role:Role}){
  const {pick}=useI18n();
  const [selected,setSelected]=useState(0);
  const [resellers,setResellers]=useState<AppearanceReseller[]>([]);
  const [draft,setDraft]=useState<AppAppearance>(DEFAULT);
  const [loaded,setLoaded]=useState(false);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");

  useEffect(()=>{
    if(role!=="admin")return;
    let active=true;
    appearanceApi.listResellers().then(rows=>{if(active)setResellers(rows);}).catch(()=>{});
    return()=>{active=false;};
  },[role]);
  useEffect(()=>{
    let active=true;
    setLoaded(false);
    setMessage("");
    setError("");
    appearanceApi.load(role,selected).then(value=>{
      if(active){setDraft(value);setLoaded(true);}
    }).catch(reason=>{
      if(active){setError(String(reason));setLoaded(false);}
    });
    return()=>{active=false;};
  },[role,selected]);

  const edit=<K extends keyof AppAppearance>(field:K,value:AppAppearance[K])=>
    setDraft(old=>({...old,[field]:value}));
  const verify=()=>{
    for(const [key] of COLOR_FIELDS){
      if(!HEX.test(draft[key]))return pick("کد رنگ باید شش‌رقمی باشد.","Colors must use six-digit HEX codes.");
    }
    if(draft.background_style==="image"&&!draft.background_image_url?.startsWith("https://"))
      return pick("آدرس تصویر پس‌زمینه باید HTTPS باشد.","Background image must use an HTTPS URL.");
    return "";
  };
  const save=async()=>{
    if(busy||!loaded)return;
    const invalid=verify();if(invalid){setError(invalid);return;}
    setBusy(true);setError("");setMessage("");
    try{
      const value=await appearanceApi.save(role,draft,selected);
      setDraft(value);
      setMessage(pick("ظاهر اپ ذخیره شد؛ کاربران با بازخوانی حساب تغییرات را می‌بینند.","App appearance saved; customers see it when their account refreshes."));
    }catch(reason){setError(String(reason));}finally{setBusy(false);}
  };
  const reset=async()=>{
    if(busy||!loaded)return;
    if(!window.confirm(pick("تنظیمات اپ این حساب به حالت پیش‌فرض برگردد؟","Reset this account's app appearance to defaults?")))return;
    setBusy(true);setError("");setMessage("");
    try{setDraft(await appearanceApi.reset(role,selected));setMessage(pick("تم به پیش‌فرض برگشت.","Appearance reset."));}
    catch(reason){setError(String(reason));}finally{setBusy(false);}
  };

  const light= draft.theme_mode==="light" ||
    (draft.theme_mode==="system"&&brightness(draft.background_color)>160);
  const text=light?"#111827":"#F8FAFC";
  const muted=light?"#475569":"#CBD5E1";
  const bg=safe(draft.background_color,DEFAULT.background_color);
  const primary=safe(draft.primary_color,DEFAULT.primary_color);
  const secondary=safe(draft.secondary_color,DEFAULT.secondary_color);
  const surface=safe(draft.surface_color,DEFAULT.surface_color);
  const button=safe(draft.button_color,DEFAULT.button_color);
  const imageOk=draft.background_style==="image"&&/^https:\/\//.test(draft.background_image_url||"");
  const background=imageOk?`linear-gradient(#10101860,#10101860),url("${draft.background_image_url}")`:
    draft.background_style==="gradient"?`linear-gradient(145deg,${bg},${secondary}44,${bg})`:bg;
  const previewStyle={
    background,backgroundSize:"cover",backgroundPosition:"center",
    color:text,
  } as CSSProperties;

  return <section className={styles.root} data-testid="twinconnect-appearance-editor">
    <div className={styles.heading}>
      <div><h3>{pick("شخصی‌سازی ظاهر اپ TwinConnect","TwinConnect app appearance")}</h3>
        <p>{pick("رنگ‌ها و پس‌زمینه فقط روی اپ مشتریان این مالک اثر می‌گذارند، نه ظاهر پنل یا سایر نمایندگان.","These colors and backgrounds affect only this owner's client app, not the panel or other resellers.")}</p>
      </div>
      <span className={styles.tag}>{pick("اپ مشترک · برند مستقل","One app · Independent brand")}</span>
    </div>
    {role==="admin"&&<label className={styles.field}>
      <span>{pick("انتخاب مالک ظاهر اپ","Choose appearance owner")}</span>
      <select value={selected} disabled={busy} onChange={e=>setSelected(Number(e.target.value))}>
        <option value={0}>{pick("مدیر اصلی","Panel administrator")}</option>
        {resellers.map(row=><option key={row.id} value={row.id}>{row.name} · #{row.id}</option>)}
      </select>
    </label>}
    {error&&<p className={styles.error} role="alert">{error}</p>}
    {message&&<p className={styles.success} role="status">{message}</p>}
    {!loaded?<p className={styles.loading}>{pick("در حال دریافت تنظیمات اپ...","Loading app appearance...")}</p>:
    <div className={styles.layout}>
      <div className={styles.editor}>
        <div className={styles.sectionTitle}>{pick("پالت رنگ‌ها","Color palette")}</div>
        <div className={styles.presets}>
          {PRESETS.map((entry,index)=><button key={index} type="button" disabled={busy}
            title={pick(entry.name[0],entry.name[1])}
            onClick={()=>setDraft(prev=>({
              ...prev,primary_color:entry.colors[0],secondary_color:entry.colors[1],
              button_color:entry.colors[2],background_color:entry.colors[3],
              surface_color:entry.colors[4],theme_mode:index===4?"light":"dark",
            }))} style={{background:`linear-gradient(135deg,${entry.colors[0]},${entry.colors[1]})`}}
            aria-label={pick(entry.name[0],entry.name[1])}/>)}
        </div>
        <div className={styles.colors}>
          {COLOR_FIELDS.map(([key,fa,en])=><label className={styles.field} key={key}>
            <span>{pick(fa,en)}</span>
            <div className={styles.colorRow}>
              <input aria-label={pick(fa,en)} type="color" value={safe(draft[key],DEFAULT[key])}
                onChange={e=>edit(key,e.target.value.toUpperCase())}/>
              <input aria-label={pick(fa+" HEX",en+" HEX")} dir="ltr" maxLength={7}
                value={draft[key]} onChange={e=>edit(key,e.target.value.toUpperCase())}/>
            </div>
          </label>)}
        </div>
        <div className={styles.sectionTitle}>{pick("نوع و حالت نمایش","Background and display")}</div>
        <div className={styles.colors}>
          <label className={styles.field}><span>{pick("حالت پس‌زمینه","Background type")}</span>
            <select value={draft.background_style} onChange={e=>edit("background_style",e.target.value as AppAppearance["background_style"])}>
              <option value="solid">{pick("رنگ ساده","Solid color")}</option>
              <option value="gradient">{pick("گرادیان","Gradient")}</option>
              <option value="image">{pick("تصویر","Image")}</option>
            </select>
          </label>
          <label className={styles.field}><span>{pick("تم اپ","App theme")}</span>
            <select value={draft.theme_mode} onChange={e=>edit("theme_mode",e.target.value as AppAppearance["theme_mode"])}>
              <option value="dark">{pick("تیره","Dark")}</option>
              <option value="light">{pick("روشن","Light")}</option>
              <option value="system">{pick("مطابق دستگاه","System default")}</option>
            </select>
          </label>
        </div>
        {draft.background_style==="image"&&<label className={styles.field}>
          <span>{pick("آدرس تصویر HTTPS","HTTPS image URL")}</span>
          <input dir="ltr" type="url" placeholder="https://cdn.example.com/background.webp"
            value={draft.background_image_url||""}
            onChange={e=>edit("background_image_url",e.target.value||null)}/>
          <small>{pick("تصویر باید روی هاست HTTPS عمومی باشد. آپلود مستقیم در این نسخه فعال نیست.","Use an externally hosted public HTTPS image. Direct image upload is not yet available.")}</small>
        </label>}
        <div className={styles.actions}>
          <button className="primary" type="button" onClick={()=>void save()} disabled={busy}>{busy?pick("در حال ذخیره...","Saving..."):pick("ذخیره ظاهر اپ","Save app appearance")}</button>
          <button className="ghost" type="button" onClick={()=>void reset()} disabled={busy}>{pick("بازنشانی","Reset")}</button>
        </div>
      </div>
      <div className={styles.preview}>
        <div className={styles.sectionTitle}>{pick("پیش‌نمایش زنده اپ","Live app preview")}</div>
        <div className={styles.phone} style={previewStyle}>
          <div className={styles.previewTop}><span className={styles.logo} style={{background:primary}}>✦</span><b>TwinConnect</b><small>•••</small></div>
          <div className={styles.previewBody}>
            <div className={styles.previewStatus} style={{background:surface,color:text,borderColor:primary+"55"}}>
              <span style={{color:primary}}>●</span> {pick("آماده اتصال","Ready to connect")}
            </div>
            <div className={styles.previewRing} style={{borderColor:primary,boxShadow:`0 0 48px ${primary}55`}}>
              <span style={{color:primary}}>⏻</span>
            </div>
            <button className={styles.previewButton} type="button" style={{background:button,color:brightness(button)>165?"#101018":"#FFFFFF"}}>
              {pick("اتصال","Connect")}
            </button>
            <div className={styles.previewTile} style={{background:surface,color:text}}>
              <b>{pick("سرور انتخابی","Selected server")}</b><small style={{color:muted}}>Germany · WireGuard</small>
            </div>
            <div className={styles.previewTile} style={{background:surface,color:text}}>
              <b>{pick("اشتراک","Subscription")}</b><small style={{color:muted}}>25 GB / 100 GB</small>
            </div>
          </div>
        </div>
        <small className={styles.previewNote}>{pick("این پیش‌نمایش طراحی است، نه اتصال فعال VPN.","Design preview only, not an active VPN connection.")}</small>
      </div>
    </div>}
  </section>;
}
