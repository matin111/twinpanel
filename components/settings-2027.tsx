"use client";

import Link from "next/link";
import {FormEvent,useEffect,useState} from "react";
import {Badge,Card,PageHead,Shell} from "./ui";
import {useI18n} from "../lib/i18n";
import {ThemeSwitch,useTheme} from "../lib/theme";
import {generalSettingsApi,SubscriptionUsernameSettings} from "../lib/general-settings-api";

const empty:SubscriptionUsernameSettings={prefix:"",template:"",preview:"",variables:[]};

export function SettingsPage2027(){
  const {pick}=useI18n();
  const {mode,resolved}=useTheme();
  const [username,setUsername]=useState<SubscriptionUsernameSettings>(empty);
  const [loading,setLoading]=useState(true);
  const [saving,setSaving]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const load=async()=>{
    setLoading(true);setError("");
    try{setUsername(await generalSettingsApi.subscriptionUsername());}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setLoading(false);}
  };
  useEffect(()=>{void load();},[]);

  const save=async(event:FormEvent)=>{
    event.preventDefault();if(saving)return;
    setSaving(true);setError("");setOk("");
    try{
      const result=await generalSettingsApi.saveSubscriptionUsername({prefix:username.prefix,template:username.template});
      setUsername(result);
      setOk(pick("تنظیمات نام کاربری ذخیره شد","Username settings saved"));
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setSaving(false);}
  };

  return <Shell active="/admin/settings"><div className="page">
    <PageHead title={pick("تنظیمات سیستم","System Settings")} sub={pick("تنظیمات واقعی Backend و ترجیحات رابط","Live backend settings and interface preferences")}/>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}

    <div className="module-grid two settings2027-live">
      <Card>
        <div className="card-head"><div><b>{pick("حالت نمایش","Appearance mode")}</b><small>{pick("در مرورگر ذخیره می‌شود و روی تمام صفحات اعمال می‌شود","Saved in the browser and applied across all pages")}</small></div><Badge tone="violet">{mode.toUpperCase()} · {resolved}</Badge></div>
        <div className="theme-setting-panel"><ThemeSwitch/><div><b>{pick("دارک، لایت یا هماهنگ با سیستم","Dark, light or follow system")}</b><p className="muted">{pick("این تنظیم واقعی است و نیاز به ذخیره جداگانه ندارد.","This is a real preference and saves automatically.")}</p></div></div>
      </Card>

      <Card>
        <div className="card-head"><div><b>{pick("بخش‌های تنظیمات","Settings modules")}</b><small>{pick("هر مورد به صفحه عملیاتی خودش می‌رود","Each item opens its live operational page")}</small></div></div>
        <div className="settings-link-grid">
          <Link href="/admin/branding"><b>{pick("برندینگ","Branding")}</b><small>{pick("نام، لوگو و هویت عمومی","Name, logo and public identity")}</small></Link>
          <Link href="/admin/notifications"><b>{pick("اعلان‌ها","Notifications")}</b><small>{pick("Telegram، پرداخت، شبکه و امنیت","Telegram, payment, network and security")}</small></Link>
          <Link href="/admin/sms-reader"><b>{pick("پرداخت و SMS Reader","Payments & SMS Reader")}</b><small>{pick("تطبیق پیامک و تأیید پرداخت","SMS matching and payment verification")}</small></Link>
          <Link href="/admin/vpn-settings"><b>{pick("تنظیمات VPN","VPN Settings")}</b><small>{pick("تنظیمات سرویس‌های VPN","VPN service settings")}</small></Link>
          <Link href="/admin/l2tp"><b>L2TP / IPsec</b><small>{pick("PSK و تنظیمات پروتکل","PSK and protocol settings")}</small></Link>
          <Link href="/admin/system-health"><b>{pick("سلامت و امنیت","Health & Security")}</b><small>{pick("System Health و Core Protocols","System health and core protocols")}</small></Link>
        </div>
      </Card>
    </div>

    <Card className="runtime-editor">
      <div className="card-head"><div><b>{pick("قالب نام کاربری اشتراک","Subscription username format")}</b><small>{pick("مستقیم از تنظیمات عمومی Backend خوانده و ذخیره می‌شود","Read and saved directly through the backend general settings API")}</small></div><button className="ghost" disabled={loading||saving} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
      {loading?<div className="runtime-loading">{pick("در حال دریافت تنظیمات...","Loading settings...")}</div>:<form onSubmit={save}>
        <div className="setting-grid">
          <label className="field"><span>{pick("پیشوند","Prefix")}</span><input dir="ltr" value={username.prefix} onChange={e=>setUsername(s=>({...s,prefix:e.target.value}))} placeholder="tp"/></label>
          <label className="field"><span>{pick("قالب","Template")}</span><input dir="ltr" value={username.template} onChange={e=>setUsername(s=>({...s,template:e.target.value}))} placeholder="{prefix}{user_id}-{subscription_id}"/></label>
        </div>
        <div className="runtime-info-list"><div><span>{pick("پیش‌نمایش Backend","Backend preview")}</span><b dir="ltr">{username.preview||"—"}</b></div><div><span>{pick("متغیرهای مجاز","Available variables")}</span><b dir="ltr">{username.variables?.join(" · ")||"—"}</b></div></div>
        <div className="action-row"><button className="primary" disabled={saving}>{saving?pick("در حال ذخیره...","Saving..."):pick("ذخیره تنظیمات","Save settings")}</button></div>
      </form>}
    </Card>

    <Card><div className="card-head"><div><b>{pick("اصل طراحی تنظیمات","Settings policy")}</b></div></div><p className="muted">{pick("در این صفحه گزینه نمایشی یا بدون Backend نگه نمی‌داریم. تنظیماتی مثل Accent یا تراکم رابط فقط زمانی اضافه می‌شوند که واقعاً در محصول ذخیره و اعمال شوند.","This page intentionally avoids decorative controls without a backend or persistent implementation. Accent and density options will only appear when they are truly stored and applied product-wide.")}</p></Card>
  </div></Shell>;
}
