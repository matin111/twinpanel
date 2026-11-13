"use client";

import {useEffect,useRef,useState,type CSSProperties} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {appearanceApi,type AppAppearance,type AppearanceReseller} from "../lib/central-app-appearance-api";
import {Shell} from "./ui";
import {PortalShell} from "./portal-shells";
import "./central-app-brand-studio.css";

type AppContact={
  logo_url:string|null;primary_color:string|null;secondary_color:string|null;
  telegram_url:string|null;renewal_url:string|null;support_phone:string|null;website_url:string|null;
  brand_name?:string|null;app_username_prefix?:string|null;
};
type ContactKey="telegram_url"|"renewal_url"|"support_phone"|"website_url";
type Tab="identity"|"colors"|"support";
const EMPTY:AppContact={logo_url:null,primary_color:null,secondary_color:null,
  telegram_url:null,renewal_url:null,support_phone:null,website_url:null};
const FIELDS:ReadonlyArray<[ContactKey,string,string,string]>= [
  ["telegram_url","لینک تلگرام پشتیبانی","Support Telegram","https://t.me/yourbrand"],
  ["renewal_url","لینک تمدید اشتراک","Renewal link","https://example.com/renew"],
  ["support_phone","تلفن پشتیبانی","Support phone","+98..."],
  ["website_url","آدرس وب‌سایت","Website","https://example.com"],
];

async function apiRequest<T>(path:string,method="GET",body?:object|FormData):Promise<T>{
  const token=getCustomerToken();
  if(!token)throw new Error("AUTH_REQUIRED");
  const isForm=body instanceof FormData;
  const response=await fetch(`${API_BASE}/v1/central-app/${path}`,{
    method,cache:"no-store",
    headers:{Authorization:`Bearer ${token}`,...(!isForm&&body?{"Content-Type":"application/json"}:{})},
    ...(body?{body:isForm?body:JSON.stringify(body)}:{}),
  });
  if(!response.ok){
    let reason=`HTTP ${response.status}`;
    try{const payload=await response.json();reason=String(payload.detail||reason)}catch{}
    throw new Error(reason);
  }
  return response.json() as Promise<T>;
}

function imageUrl(value:string|null):string{
  if(!value)return "";
  if(value.startsWith("/")&&typeof window!=="undefined")return window.location.origin+value;
  return value;
}

export function CentralAppBrandManager({role}:{role:"admin"|"reseller"}){
  const {pick}=useI18n();
  const [resellers,setResellers]=useState<AppearanceReseller[]>([]);
  const [resellerId,setResellerId]=useState(0);
  const [appearance,setAppearance]=useState<AppAppearance|null>(null);
  const [contact,setContact]=useState<AppContact>(EMPTY);
  const [tab,setTab]=useState<Tab>("identity");
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [dirty,setDirty]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const fileRef=useRef<HTMLInputElement>(null);
  const target=role==="reseller"?"reseller/profile":resellerId>0?`admin/resellers/${resellerId}/profile`:"admin/profile";
  const uploadTarget=role==="reseller"?"reseller/assets/logo":resellerId>0?`admin/resellers/${resellerId}/assets/logo`:"admin/assets/logo";
  useEffect(()=>{
    if(role!=="admin")return;
    let live=true;
    appearanceApi.listResellers().then(rows=>{if(live)setResellers(rows)})
      .catch(e=>{if(live)setError(String(e))});
    return()=>{live=false};
  },[role]);
  useEffect(()=>{
    let live=true;
    setLoading(true);setError("");setNotice("");setAppearance(null);setDirty(false);
    Promise.all([appearanceApi.load(role,resellerId),apiRequest<AppContact>(target)])
      .then(([a,c])=>{if(live){setAppearance(a);setContact({...EMPTY,...c})}})
      .catch(e=>{if(live)setError(e instanceof Error?e.message:String(e))})
      .finally(()=>{if(live)setLoading(false)});
    return()=>{live=false};
  },[role,resellerId,target]);
  const changeColor=(key:"primary_color"|"secondary_color"|"button_color"|"background_color"|"surface_color",value:string)=>{
    if(!/^#[0-9a-fA-F]{6}$/.test(value))return;
    setAppearance(current=>current?{...current,[key]:value}:current);setDirty(true);
  };
  const changeAppearance=<K extends keyof AppAppearance>(key:K,value:AppAppearance[K])=>{
    setAppearance(current=>current?{...current,[key]:value}:current);setDirty(true);
  };
  const changeContact=(key:ContactKey,value:string)=>{
    setContact(current=>({...current,[key]:value||null}));setDirty(true);
  };
  const upload=async(file:File|undefined)=>{
    if(!file||busy)return;
    if(file.size>2*1024*1024){setError(pick("حجم لوگو باید کمتر از ۲ مگابایت باشد.","Logo must be under 2 MB."));return}
    if(!["image/png","image/jpeg","image/webp"].includes(file.type)){
      setError(pick("فقط PNG، JPG و WebP پشتیبانی می‌شود.","Use PNG, JPG or WebP."));return;
    }
    setBusy(true);setError("");setNotice("");
    try{
      const body=new FormData();body.append("file",file);
      const data=await apiRequest<{logo_url:string}>(uploadTarget,"POST",body);
      setContact(current=>({...current,logo_url:data.logo_url}));
      setNotice(pick("لوگو آپلود شد و از طریق API برند در دسترس اپ قرار گرفت.","Logo uploaded and available to the app brand API."));
      // Other unsaved appearance fields remain untouched.
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false);if(fileRef.current)fileRef.current.value=""}
  };
  const save=async()=>{
    if(!appearance||busy)return;
    setBusy(true);setError("");setNotice("");
    try{
      const a=await appearanceApi.save(role,appearance,resellerId);
      const c=await apiRequest<AppContact>(target,"PUT",{
        logo_url:contact.logo_url,primary_color:a.primary_color,secondary_color:a.secondary_color,
        telegram_url:contact.telegram_url,renewal_url:contact.renewal_url,
        support_phone:contact.support_phone,website_url:contact.website_url,
      });
      setAppearance(a);setContact(current=>({...current,...c}));
      setDirty(false);setNotice(pick("تنظیمات ذخیره شد؛ اپ با ورود یا بروزرسانی برند آن را دریافت می‌کند.","Saved; the app receives updates on login or brand refresh."));
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  };
  const reset=async()=>{
    if(busy||!window.confirm(pick("تنظیمات رنگ و ظاهر به حالت پیش‌فرض برگردد؟","Reset app appearance to defaults?")))return;
    setBusy(true);setError("");setNotice("");
    try{
      setAppearance(await appearanceApi.reset(role,resellerId));
      setDirty(false);setNotice(pick("ظاهر بازنشانی شد؛ لوگو و راه‌های تماس تغییری نکردند.","Appearance reset; logo and contacts were preserved."));
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  };
  const brand=role==="reseller"
    ?contact.brand_name||pick("برند نمایندگی شما","Your reseller brand")
    :resellerId>0?resellers.find(r=>r.id===resellerId)?.name||""
    :contact.brand_name||pick("پنل اصلی","Main panel");
  const previewLogo=imageUrl(contact.logo_url);
  const previewPalette={
    "--tc-primary":appearance?.primary_color||"#9F43FF",
    "--tc-secondary":appearance?.secondary_color||"#00DFF2",
    "--tc-button":appearance?.button_color||"#9053FF",
    "--tc-card":appearance?.surface_color||"#22234D",
  } as CSSProperties;
  const preview=<div className={`tbs-device tbs-device-modern ${appearance?.theme_mode==="light"?"tbs-device-light":""}`}
    style={{
      ...previewPalette,
      background:appearance?.background_style==="solid"
        ?appearance?.background_color
        :`linear-gradient(145deg,${appearance?.background_color} 12%,${appearance?.secondary_color}36 58%,${appearance?.background_color} 100%)`,
      color:appearance?.theme_mode==="light"?"#172033":"#f3f6ff",
    }}>
    <div className="tbs-device-top"><span>WIN · TWINCONNECT</span><span>✦</span></div>
    <div className="tbs-device-brand">
      <span className="tbs-device-logo">{previewLogo?<img alt="" src={previewLogo}/>:<span>✦</span>}</span>
      <div><strong>{brand}</strong><small>{pick("پیش‌نمایش تم اختصاصی","Custom theme preview")}</small></div>
    </div>
    <div className="tbs-device-glow" style={{background:appearance?.primary_color}}/>
    <div className="tbs-modern-status"><span className="tbs-status-dot"/> {pick("آماده اتصال","Ready to connect")}</div>
    <div className="tbs-modern-connect" style={{
      background:`linear-gradient(125deg,${appearance?.primary_color},${appearance?.button_color} 52%,${appearance?.secondary_color})`,
    }}><span className="tbs-modern-power">⏻</span><span><strong>{pick("اتصال سریع","Quick connect")}</strong><small>{pick("انتخاب سرور","Selected server")}</small></span><span>›</span></div>
    <div className="tbs-modern-details">
      <span>{pick("سرور","Server")}<strong>—</strong></span>
      <span>{pick("پینگ","Ping")}<strong>—</strong></span>
    </div>
    <div className="tbs-modern-speeds">
      <div className="tbs-modern-traffic"><span>↓ {pick("دانلود","Download")}</span><strong>— MB/s</strong><div className="tbs-modern-graph"/></div>
      <div className="tbs-modern-traffic"><span>↑ {pick("آپلود","Upload")}</span><strong>— MB/s</strong><div className="tbs-modern-graph"/></div>
    </div>
    <div className="tbs-modern-subscription"><b>{pick("اطلاعات اشتراک","Subscription")}</b>
      <div><span>{pick("حجم مصرفی","Usage")}<strong>— / —</strong></span>
      <span>{pick("انقضا","Expiry")}<strong>—</strong></span></div>
    </div>
    <div className="tbs-modern-menu"><span>⌁ {pick("اتصال","Connect")}</span><span>◈ {pick("سرورها","Locations")}</span><span>⚙ {pick("تنظیمات","Settings")}</span></div>
  </div>;
  const page=<div className="tbs-page" dir="rtl">
    <div className="tbs-hero">
      <div className="tbs-hero-icon">✦</div>
      <div className="tbs-hero-copy"><div className="tbs-kicker">TWINCONNECT / BRAND STUDIO</div>
        <h1>{pick("استودیوی برند اپ","App Brand Studio")}</h1>
        <p>{pick("ظاهر اختصاصی برنامه را تنظیم کنید؛ تغییرات از طریق سرویس مرکزی برند به اپ منتقل می‌شوند.","Personalize your app. Brand changes are delivered through the central brand service.")}</p>
      </div>
      <span className="tbs-active"><span/> {pick("برند مستقل","Independent brand")}</span>
    </div>
    {role==="admin"&&<div className="tbs-tenant">
      <div><b>{pick("برند موردنظر","Selected brand")}</b><small>{pick("برای هر پنل تنظیمات مستقل ذخیره می‌شود","Each panel has independent settings")}</small></div>
      <select aria-label={pick("انتخاب پنل","Choose panel")} value={resellerId}
        onChange={e=>{if(dirty&&!window.confirm(pick("تغییرات ذخیره‌نشده از بین می‌روند. ادامه می‌دهید؟","Discard unsaved changes?")))return;setResellerId(Number(e.target.value))}}>
        <option value={0}>{pick("پنل اصلی","Main panel")}</option>
        {resellers.map(r=><option key={r.id} value={r.id}>{r.name} · #{r.id}</option>)}
      </select>
    </div>}
    {error&&<div className="tbs-alert tbs-error" role="alert">{error}</div>}
    {notice&&<div className="tbs-alert tbs-success" role="status">{notice}</div>}
    {loading?<div className="tbs-loading">{pick("در حال دریافت اطلاعات برند…","Loading brand…")}</div>:appearance&&
      <div className="tbs-layout">
        <section className="tbs-editor">
          <div className="tbs-tabs" role="tablist">
            {([
              ["identity","◈","هویت برند","Identity"],
              ["colors","◉","رنگ و ظاهر","Appearance"],
              ["support","☏","پشتیبانی","Support"],
            ] as const).map(([id,icon,fa,en])=><button role="tab" aria-selected={tab===id} type="button"
              className={tab===id?"selected":""} key={id} onClick={()=>setTab(id)}><span>{icon}</span>{pick(fa,en)}</button>)}
          </div>
          {tab==="identity"&&<div className="tbs-panel">
            <div className="tbs-section-head"><div><h2>{pick("هویت برند","Brand identity")}</h2><p>{pick("مشتری پس از ورود، لوگو و نام برند مالک اشتراک خود را می‌بیند.","Customers see their subscription owner's logo and name after login.")}</p></div></div>
            <div className="tbs-field"><label>{pick("نام نمایشی برند","Brand display name")}</label>
              <div className="tbs-readonly">{brand}</div>
              <small>{pick("نام برند از تنظیمات اصلی پنل یا پروفایل نماینده دریافت می‌شود.","Brand name is inherited from the panel or reseller profile.")}</small>
            </div>
            <div className="tbs-upload" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();void upload(e.dataTransfer.files[0])}}>
              <div className="tbs-upload-preview">{previewLogo?<img alt={pick("لوگوی فعلی","Current logo")} src={previewLogo}/>:<span>✦</span>}</div>
              <div className="tbs-upload-copy"><strong>{pick("لوگوی اختصاصی اپ","App brand logo")}</strong>
                <p>{pick("تصویر را اینجا رها کنید یا از دستگاه انتخاب کنید","Drop an image or choose from your device")}</p>
                <small>PNG · JPG · WebP — MAX 2 MB</small>
                <button type="button" disabled={busy} onClick={()=>fileRef.current?.click()}>{busy?"…":pick("انتخاب و آپلود لوگو","Upload logo")}</button>
                <input aria-label={pick("آپلود لوگو","Upload logo")} ref={fileRef} type="file" accept=".png,.jpg,.jpeg,.webp" hidden onChange={e=>void upload(e.target.files?.[0])}/>
              </div>
            </div>
            {contact.logo_url&&<button className="tbs-text-action" type="button"
              onClick={()=>{setContact(current=>({...current,logo_url:null}));setDirty(true)}}>{pick("حذف لوگو از برند","Remove logo from brand")}</button>}
          </div>}
          {tab==="colors"&&<div className="tbs-panel">
            <div className="tbs-section-head"><div><h2>{pick("رنگ‌ها و ظاهر","Colors & appearance")}</h2><p>{pick("رنگ‌ها را تنظیم کنید و نتیجه را در پیش‌نمایش ببینید.","Customize colors and preview changes instantly.")}</p></div></div>
            <div className="tbs-presets">
              {([
                ["#9F43FF","#00DFF2","#9053FF","#0A1028","#252350"],
                ["#7C3AED","#4F46E5","#7C3AED","#101018","#20202A"],
                ["#0087DB","#00C2BB","#0087DB","#071B30","#15304A"],
                ["#F97316","#DB2777","#F97316","#231320","#39203B"],
                ["#15A66A","#0E7490","#15A66A","#081B1B","#173336"],
              ] as const).map(([a,b,button,background,surface],i)=>
                <button key={a} type="button"
                  aria-label={i===0?pick("تم شیشه‌ای نئونی TwinConnect","TwinConnect neon glass theme"):pick("اعمال پالت","Apply preset")}
                  title={i===0?pick("تم شیشه‌ای نئونی TwinConnect","TwinConnect neon glass theme"):pick("اعمال پالت","Apply preset")}
                  style={{background:`linear-gradient(125deg,${a} 45%,${b} 55%)`}}
                  onClick={()=>{setAppearance(current=>current?{
                    ...current,primary_color:a,secondary_color:b,
                    button_color:button,background_color:background,
                    surface_color:surface,background_style:"gradient",
                  }:current);setDirty(true)}}/>)}
            </div>
            <div className="tbs-colors">
              {([
                ["primary_color","رنگ اصلی","Primary"],
                ["secondary_color","رنگ مکمل","Secondary"],
                ["button_color","دکمه اتصال","Connect button"],
                ["background_color","پس‌زمینه اپ","Background"],
                ["surface_color","کارت‌ها","Cards"],
              ] as const).map(([key,fa,en])=><div className="tbs-color-field" key={key}>
                <label htmlFor={key}>{pick(fa,en)}</label>
                <div className="tbs-color-input"><input type="color" id={key} value={appearance[key]} onChange={e=>changeColor(key,e.target.value)}/>
                  <input dir="ltr" maxLength={7} value={appearance[key]} onChange={e=>changeColor(key,e.target.value)} aria-label={pick(fa,en)}/></div>
              </div>)}
            </div>
            <div className="tbs-selects">
              <label>{pick("حالت نمایش","Theme")}
                <select value={appearance.theme_mode} onChange={e=>changeAppearance("theme_mode",e.target.value as AppAppearance["theme_mode"])}>
                  <option value="dark">{pick("تیره","Dark")}</option><option value="light">{pick("روشن","Light")}</option><option value="system">{pick("سیستم","System")}</option>
                </select></label>
              <label>{pick("استایل پس‌زمینه","Background style")}
                <select value={appearance.background_style} onChange={e=>changeAppearance("background_style",e.target.value as AppAppearance["background_style"])}>
                  <option value="gradient">{pick("گرادیان","Gradient")}</option><option value="solid">{pick("ساده","Solid")}</option><option value="image">{pick("تصویر","Image")}</option>
                </select></label>
            </div>
            {appearance.background_style==="image"&&<label className="tbs-field">{pick("لینک HTTPS تصویر پس‌زمینه","Background image HTTPS URL")}
              <input dir="ltr" value={appearance.background_image_url||""} placeholder="https://..."
                onChange={e=>changeAppearance("background_image_url",e.target.value||null)}/></label>}
          </div>}
          {tab==="support"&&<div className="tbs-panel">
            <div className="tbs-section-head"><div><h2>{pick("ارتباط و پشتیبانی","Support & contact")}</h2><p>{pick("این اطلاعات در اپ با برند خودتان نمایش داده می‌شوند.","These details appear in your branded app.")}</p></div></div>
            {FIELDS.map(([key,fa,en,placeholder])=><label className="tbs-field" key={key}>
              <span>{pick(fa,en)}</span><input dir="ltr" placeholder={placeholder} value={contact[key]||""}
                onChange={e=>changeContact(key,e.target.value)}/></label>)}
          </div>}
          <div className="tbs-actions">
            <span>{dirty?pick("تغییرات ذخیره‌نشده","Unsaved changes"):pick("همگام با پنل","Synced with panel")}</span>
            <div><button type="button" className="tbs-reset" disabled={busy} onClick={()=>void reset()}>{pick("بازنشانی ظاهر","Reset")}</button>
              <button type="button" className="tbs-save" disabled={busy||!dirty} onClick={()=>void save()}>{busy?"…":pick("ذخیره تغییرات","Save changes")}</button></div>
          </div>
        </section>
        <aside className="tbs-preview">
          <div className="tbs-preview-head"><div><strong>{pick("پیش‌نمایش زنده","Live preview")}</strong>
            <small>{pick("نمای تقریبی اپ پس از دریافت برند","Approximate app appearance")}</small></div>
            <span>{pick("پیش‌نمایش طراحی","DESIGN PREVIEW")}</span></div>
          {preview}
          <div className="tbs-preview-note">{pick("این بخش فقط پیش‌نمایش ظاهر است؛ سرورها و اتصال واقعی را داخل نسخه ویندوز پس از ورود بررسی کنید.","This is an appearance preview; check actual servers and connections in the signed-in Windows app.")}</div>
        </aside>
      </div>}
  </div>;
  return role==="admin"?<Shell active="/admin/smart-app">{page}</Shell>:<PortalShell type="reseller" active="/reseller/smart-app">{page}</PortalShell>;
}
