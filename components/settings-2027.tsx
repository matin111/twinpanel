"use client";

import Link from "next/link";
import {FormEvent,useEffect,useMemo,useState} from "react";
import {Badge,Card,PageHead,Shell} from "./ui";
import {useI18n} from "../lib/i18n";
import {ThemeSwitch,useTheme} from "../lib/theme";
import {
  generalSettingsApi,
  L2tpSettings,
  MotherAccessSettings,
  SettingsReseller,
  SettingsUser,
  SubscriptionUsernameSettings,
  TwoFactorSetup,
} from "../lib/general-settings-api";

const emptyUsername:SubscriptionUsernameSettings={prefix:"",template:"",preview:"",variables:[]};
const emptyL2tp:L2tpSettings={psk:"",length:0,exit_count:0,exit_nodes:[]};
const emptyMother:MotherAccessSettings={admin_enabled:true,reseller_enabled:false,reseller_overrides:{}};

export function SettingsPage2027(){
  const {pick}=useI18n();
  const {mode,resolved}=useTheme();

  const [profile,setProfile]=useState<SettingsUser|null>(null);
  const [emailDraft,setEmailDraft]=useState("");
  const [emailPassword,setEmailPassword]=useState("");

  const [currentPassword,setCurrentPassword]=useState("");
  const [newPassword,setNewPassword]=useState("");
  const [confirmPassword,setConfirmPassword]=useState("");

  const [twoFactorEnabled,setTwoFactorEnabled]=useState(false);
  const [twoFactorSetup,setTwoFactorSetup]=useState<TwoFactorSetup|null>(null);
  const [twoFactorCode,setTwoFactorCode]=useState("");
  const [twoFactorDisablePassword,setTwoFactorDisablePassword]=useState("");
  const [twoFactorDisableCode,setTwoFactorDisableCode]=useState("");

  const [l2tp,setL2tp]=useState<L2tpSettings>(emptyL2tp);
  const [l2tpDraft,setL2tpDraft]=useState("");
  const [showPsk,setShowPsk]=useState(false);

  const [mother,setMother]=useState<MotherAccessSettings>(emptyMother);
  const [resellers,setResellers]=useState<SettingsReseller[]>([]);

  const [username,setUsername]=useState<SubscriptionUsernameSettings>(emptyUsername);

  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");

  const setFailure=(e:unknown)=>setError(e instanceof Error?e.message:String(e));
  const begin=(key:string)=>{if(busy)return false;setBusy(key);setError("");setOk("");return true;};
  const finish=()=>setBusy("");

  const load=async()=>{
    setLoading(true);setError("");setOk("");
    const results=await Promise.allSettled([
      generalSettingsApi.me(),
      generalSettingsApi.subscriptionUsername(),
      generalSettingsApi.twoFactorStatus(),
      generalSettingsApi.l2tp(),
      generalSettingsApi.motherAccess(),
      generalSettingsApi.resellers(),
    ]);

    const failures:string[]=[];

    if(results[0].status==="fulfilled"){
      const value=results[0].value as SettingsUser;
      setProfile(value);setEmailDraft(value.email||"");
    }else failures.push(String(results[0].reason));

    if(results[1].status==="fulfilled")setUsername(results[1].value as SubscriptionUsernameSettings);
    else failures.push(String(results[1].reason));

    if(results[2].status==="fulfilled")setTwoFactorEnabled(Boolean(results[2].value.enabled));
    else failures.push(String(results[2].reason));

    if(results[3].status==="fulfilled"){
      const value=results[3].value as L2tpSettings;
      setL2tp(value);setL2tpDraft(value.psk||"");
    }else failures.push(String(results[3].reason));

    if(results[4].status==="fulfilled")setMother(results[4].value as MotherAccessSettings);
    else failures.push(String(results[4].reason));

    if(results[5].status==="fulfilled")setResellers(results[5].value as SettingsReseller[]);
    else failures.push(String(results[5].reason));

    if(failures.length)setError(failures[0]);
    setLoading(false);
  };

  useEffect(()=>{void load();},[]);

  const saveEmail=async(event:FormEvent)=>{
    event.preventDefault();if(!begin("email"))return;
    try{
      const value=await generalSettingsApi.updateEmail({email:emailDraft.trim(),current_password:emailPassword});
      setProfile(value);setEmailDraft(value.email||"");setEmailPassword("");
      setOk(pick("ایمیل مدیر بروزرسانی شد","Admin email updated"));
    }catch(e){setFailure(e);}finally{finish();}
  };

  const savePassword=async(event:FormEvent)=>{
    event.preventDefault();if(!begin("password"))return;
    if(newPassword!==confirmPassword){setError(pick("تکرار رمز عبور با رمز جدید یکسان نیست.","Password confirmation does not match."));finish();return;}
    try{
      await generalSettingsApi.changePassword({current_password:currentPassword,new_password:newPassword});
      setCurrentPassword("");setNewPassword("");setConfirmPassword("");
      setOk(pick("رمز عبور مدیر تغییر کرد","Admin password changed"));
    }catch(e){setFailure(e);}finally{finish();}
  };

  const setup2fa=async()=>{
    if(!begin("2fa-setup"))return;
    try{setTwoFactorSetup(await generalSettingsApi.twoFactorSetup());setTwoFactorCode("");setOk(pick("کلید 2FA ساخته شد؛ پس از ثبت در Authenticator کد ۶ رقمی را تأیید کنید.","2FA secret created. Add it to your authenticator, then verify the 6-digit code."));}
    catch(e){setFailure(e);}finally{finish();}
  };

  const enable2fa=async()=>{
    if(!begin("2fa-enable"))return;
    try{await generalSettingsApi.twoFactorEnable(twoFactorCode.trim());setTwoFactorEnabled(true);setTwoFactorSetup(null);setTwoFactorCode("");setOk(pick("احراز هویت دومرحله‌ای فعال شد","Two-factor authentication enabled"));}
    catch(e){setFailure(e);}finally{finish();}
  };

  const disable2fa=async()=>{
    if(!begin("2fa-disable"))return;
    try{await generalSettingsApi.twoFactorDisable({current_password:twoFactorDisablePassword,code:twoFactorDisableCode.trim()});setTwoFactorEnabled(false);setTwoFactorDisablePassword("");setTwoFactorDisableCode("");setOk(pick("احراز هویت دومرحله‌ای غیرفعال شد","Two-factor authentication disabled"));}
    catch(e){setFailure(e);}finally{finish();}
  };

  const generatePsk=async()=>{
    if(!begin("l2tp-generate"))return;
    try{const value=await generalSettingsApi.generateL2tpPsk();setL2tpDraft(value.psk);setShowPsk(true);setOk(pick("Secret جدید ساخته شد؛ برای اعمال روی سرورها ذخیره را بزنید.","A new secret was generated. Save it to apply it to servers."));}
    catch(e){setFailure(e);}finally{finish();}
  };

  const savePsk=async()=>{
    if(!l2tpDraft.trim()){setError(pick("Secret نمی‌تواند خالی باشد.","Secret cannot be empty."));return;}
    if(!window.confirm(pick("Secret روی همه Exit Nodeهای فعال L2TP همگام‌سازی شود؟","Sync this secret to all active L2TP exit nodes?")))return;
    if(!begin("l2tp-save"))return;
    try{
      const result=await generalSettingsApi.saveL2tpPsk(l2tpDraft.trim());
      const current=await generalSettingsApi.l2tp();setL2tp(current);setL2tpDraft(current.psk||"");
      const count=result.synced_nodes?.length??0;
      setOk(result.changed?pick(`Secret ذخیره و روی ${count} نود همگام شد.`,`Secret saved and synced to ${count} nodes.`):pick("Secret بدون تغییر بود.","Secret was unchanged."));
    }catch(e){setFailure(e);}finally{finish();}
  };

  const saveMother=async()=>{
    if(!begin("mother-global"))return;
    try{
      const result=await generalSettingsApi.saveMotherAccess({admin_enabled:mother.admin_enabled,reseller_enabled:mother.reseller_enabled});
      setMother(v=>({...v,admin_enabled:result.admin_enabled,reseller_enabled:result.reseller_enabled}));
      setOk(pick("تنظیمات دسترسی سرور مادر ذخیره شد","Mother-server access settings saved"));
    }catch(e){setFailure(e);}finally{finish();}
  };

  const toggleResellerMother=async(resellerId:number,enabled:boolean)=>{
    const key=`mother-reseller:${resellerId}`;if(!begin(key))return;
    try{
      await generalSettingsApi.setResellerMotherAccess(resellerId,enabled);
      setMother(v=>({...v,reseller_overrides:{...v.reseller_overrides,[String(resellerId)]:enabled}}));
      setOk(pick("دسترسی نماینده بروزرسانی شد","Reseller access updated"));
    }catch(e){setFailure(e);}finally{finish();}
  };

  const saveUsername=async(event:FormEvent)=>{
    event.preventDefault();if(!begin("username"))return;
    try{const result=await generalSettingsApi.saveSubscriptionUsername({prefix:username.prefix,template:username.template});setUsername(result);setOk(pick("تنظیمات نام کاربری ذخیره شد","Username settings saved"));}
    catch(e){setFailure(e);}finally{finish();}
  };

  const copyText=async(value:string,label:string)=>{
    try{await navigator.clipboard.writeText(value);setOk(label);setError("");}
    catch{setError(pick("کپی در مرورگر مجاز نیست.","Clipboard access is not available."));}
  };

  const enabledResellerOverrides=useMemo(()=>Object.values(mother.reseller_overrides||{}).filter(Boolean).length,[mother.reseller_overrides]);

  return <Shell active="/admin/settings"><div className="page">
    <PageHead title={pick("تنظیمات سیستم","System Settings")} sub={pick("حساب مدیر، امنیت، L2TP، دسترسی سرور مادر و تنظیمات عملیاتی","Admin account, security, L2TP, mother-server access and operational settings")}/>

    {error&&<div className="runtime-error">{error}</div>}
    {ok&&<div className="runtime-success">{ok}</div>}
    {loading&&<div className="runtime-loading">{pick("در حال دریافت تنظیمات واقعی سیستم...","Loading live system settings...")}</div>}

    <div className="module-grid two settings2027-live">
      <Card>
        <div className="card-head"><div><b>{pick("حساب مدیر","Admin account")}</b><small>{pick("پروفایل و ایمیل حسابی که اکنون وارد شده است","Profile and email for the currently signed-in account")}</small></div><Badge tone={profile?.is_active?"ok":"warn"}>{profile?.is_active?pick("فعال","Active"):pick("نامشخص","Unknown")}</Badge></div>
        <div className="runtime-info-list">
          <div><span>{pick("نام","Name")}</span><b>{profile?.full_name||"—"}</b></div>
          <div><span>{pick("نقش","Role")}</span><b dir="ltr">{profile?.role||"—"}</b></div>
          <div><span>ID</span><b dir="ltr">{profile?.id??"—"}</b></div>
        </div>
        <form onSubmit={saveEmail}>
          <label className="field"><span>{pick("ایمیل مدیر","Admin email")}</span><input type="email" dir="ltr" value={emailDraft} onChange={e=>setEmailDraft(e.target.value)} required/></label>
          <label className="field"><span>{pick("رمز فعلی برای تأیید","Current password for confirmation")}</span><input type="password" value={emailPassword} onChange={e=>setEmailPassword(e.target.value)} required autoComplete="current-password"/></label>
          <div className="action-row"><button className="primary" disabled={Boolean(busy)}>{busy==="email"?pick("در حال ذخیره...","Saving..."):pick("ذخیره ایمیل","Save email")}</button></div>
        </form>
      </Card>

      <Card>
        <div className="card-head"><div><b>{pick("حالت نمایش","Appearance mode")}</b><small>{pick("در مرورگر ذخیره می‌شود و روی تمام صفحات اعمال می‌شود","Saved in the browser and applied across all pages")}</small></div><Badge tone="violet">{mode.toUpperCase()} · {resolved}</Badge></div>
        <div className="theme-setting-panel"><ThemeSwitch/><div><b>{pick("دارک، لایت یا هماهنگ با سیستم","Dark, light or follow system")}</b><p className="muted">{pick("این تنظیم واقعی است و نیاز به ذخیره جداگانه ندارد.","This preference is applied immediately and needs no separate save.")}</p></div></div>
      </Card>
    </div>

    <div className="module-grid two">
      <Card>
        <div className="card-head"><div><b>{pick("تغییر رمز عبور","Change password")}</b><small>{pick("رمز فعلی و رمز جدید را وارد کنید","Enter the current and new password")}</small></div></div>
        <form onSubmit={savePassword}>
          <label className="field"><span>{pick("رمز فعلی","Current password")}</span><input type="password" value={currentPassword} onChange={e=>setCurrentPassword(e.target.value)} required autoComplete="current-password"/></label>
          <label className="field"><span>{pick("رمز جدید","New password")}</span><input type="password" minLength={8} value={newPassword} onChange={e=>setNewPassword(e.target.value)} required autoComplete="new-password"/></label>
          <label className="field"><span>{pick("تکرار رمز جدید","Confirm new password")}</span><input type="password" minLength={8} value={confirmPassword} onChange={e=>setConfirmPassword(e.target.value)} required autoComplete="new-password"/></label>
          <button className="primary" disabled={Boolean(busy)}>{busy==="password"?pick("در حال تغییر...","Changing..."):pick("تغییر رمز","Change password")}</button>
        </form>
      </Card>

      <Card>
        <div className="card-head"><div><b>{pick("احراز هویت دومرحله‌ای","Two-factor authentication")}</b><small>{pick("TOTP برای ورود مدیر","TOTP protection for admin login")}</small></div><Badge tone={twoFactorEnabled?"ok":"warn"}>{twoFactorEnabled?pick("فعال","Enabled"):pick("غیرفعال","Disabled")}</Badge></div>
        {!twoFactorEnabled&&<>
          {!twoFactorSetup&&<button className="primary" disabled={Boolean(busy)} onClick={()=>void setup2fa()}>{busy==="2fa-setup"?"…":pick("راه‌اندازی 2FA","Set up 2FA")}</button>}
          {twoFactorSetup&&<>
            <label className="field"><span>{pick("Secret","Secret")}</span><div className="secret-field"><input dir="ltr" readOnly value={twoFactorSetup.secret}/><button type="button" className="mini-btn" onClick={()=>void copyText(twoFactorSetup.secret,pick("Secret کپی شد","Secret copied"))}>{pick("کپی","Copy")}</button></div></label>
            <label className="field"><span>Authenticator URI</span><div className="secret-field"><input dir="ltr" readOnly value={twoFactorSetup.otpauth_uri}/><button type="button" className="mini-btn" onClick={()=>void copyText(twoFactorSetup.otpauth_uri,pick("URI کپی شد","URI copied"))}>{pick("کپی","Copy")}</button></div></label>
            <label className="field"><span>{pick("کد ۶ رقمی","6-digit code")}</span><input dir="ltr" inputMode="numeric" maxLength={6} value={twoFactorCode} onChange={e=>setTwoFactorCode(e.target.value.replace(/\D/g,"").slice(0,6))}/></label>
            <button type="button" className="primary" disabled={Boolean(busy)||twoFactorCode.length!==6} onClick={()=>void enable2fa()}>{busy==="2fa-enable"?"…":pick("تأیید و فعال‌سازی","Verify and enable")}</button>
          </>}
        </>}
        {twoFactorEnabled&&<>
          <label className="field"><span>{pick("رمز فعلی","Current password")}</span><input type="password" value={twoFactorDisablePassword} onChange={e=>setTwoFactorDisablePassword(e.target.value)} autoComplete="current-password"/></label>
          <label className="field"><span>{pick("کد ۶ رقمی","6-digit code")}</span><input dir="ltr" inputMode="numeric" maxLength={6} value={twoFactorDisableCode} onChange={e=>setTwoFactorDisableCode(e.target.value.replace(/\D/g,"").slice(0,6))}/></label>
          <button type="button" className="ghost" disabled={Boolean(busy)||!twoFactorDisablePassword||twoFactorDisableCode.length!==6} onClick={()=>void disable2fa()}>{busy==="2fa-disable"?"…":pick("غیرفعال‌سازی 2FA","Disable 2FA")}</button>
        </>}
      </Card>
    </div>

    <Card className="runtime-editor">
      <div className="card-head"><div><b>L2TP / IPsec Secret</b><small>{pick("Secret مرکزی؛ هنگام ذخیره روی Exit Nodeهای فعال L2TP همگام می‌شود و در خطا rollback دارد.","Central secret; saving syncs active L2TP exit nodes and rolls back on failure.")}</small></div><Badge tone="violet">{l2tp.exit_count} {pick("نود","nodes")}</Badge></div>
      <div className="setting-grid">
        <label className="field"><span>{pick("IPsec Secret مرکزی","Central IPsec secret")}</span><div className="secret-field"><input dir="ltr" type={showPsk?"text":"password"} value={l2tpDraft} maxLength={64} onChange={e=>setL2tpDraft(e.target.value)}/><button type="button" className="mini-btn" onClick={()=>setShowPsk(v=>!v)}>{showPsk?pick("مخفی","Hide"):pick("نمایش","Show")}</button></div></label>
        <div className="runtime-info-list">
          <div><span>{pick("طول Secret","Secret length")}</span><b>{l2tpDraft.length}</b></div>
          <div><span>{pick("Exit Nodeهای L2TP","L2TP exit nodes")}</span><b>{l2tp.exit_nodes.map(x=>x.name).join(" · ")||"—"}</b></div>
        </div>
      </div>
      <div className="action-row">
        <button type="button" className="ghost" disabled={Boolean(busy)} onClick={()=>void generatePsk()}>{busy==="l2tp-generate"?"…":pick("ساخت Secret","Generate secret")}</button>
        <button type="button" className="primary" disabled={Boolean(busy)||!l2tpDraft.trim()} onClick={()=>void savePsk()}>{busy==="l2tp-save"?pick("در حال همگام‌سازی...","Syncing..."):pick("ذخیره و همگام‌سازی","Save & sync")}</button>
      </div>
    </Card>

    <Card className="runtime-editor">
      <div className="card-head"><div><b>{pick("دسترسی سرور مادر","Mother-server access")}</b><small>{pick("دسترسی مدیر و نماینده‌ها را مستقل کنترل کنید","Control admin and reseller access independently")}</small></div><Badge tone="violet">{enabledResellerOverrides} / {resellers.length}</Badge></div>
      <div className="module-grid two">
        <label className="toggle module-toggle"><span>{pick("دسترسی مدیر به سرور مادر","Admin mother access")}</span><input type="checkbox" checked={mother.admin_enabled} onChange={e=>setMother(v=>({...v,admin_enabled:e.target.checked}))}/><i/></label>
        <label className="toggle module-toggle"><span>{pick("فعال‌سازی دسترسی نماینده‌ها","Enable reseller mother access")}</span><input type="checkbox" checked={mother.reseller_enabled} onChange={e=>setMother(v=>({...v,reseller_enabled:e.target.checked}))}/><i/></label>
      </div>
      <div className="action-row"><button type="button" className="primary" disabled={Boolean(busy)} onClick={()=>void saveMother()}>{busy==="mother-global"?"…":pick("ذخیره دسترسی سراسری","Save global access")}</button></div>

      <div className="card-head"><div><b>{pick("دسترسی هر نماینده","Per-reseller access")}</b><small>{mother.reseller_enabled?pick("روشن بودن هر نماینده در کنار دسترسی سراسری لازم است.","Each reseller also needs its own switch enabled."):pick("دسترسی سراسری نماینده‌ها خاموش است؛ overrideها فعلاً مؤثر نیستند.","Global reseller access is off, so overrides are not currently effective.")}</small></div></div>
      {resellers.length?<div>{resellers.map(reseller=>{const enabled=Boolean(mother.reseller_overrides[String(reseller.id)]);const key=`mother-reseller:${reseller.id}`;return <div className="module-row" key={reseller.id}><span className="module-icon">◎</span><div className="grow"><b>{reseller.name}</b><small dir="ltr">{reseller.code||`#${reseller.id}`} · {reseller.email||"—"}</small></div><Badge tone={reseller.is_active===false?"warn":enabled&&mother.reseller_enabled?"ok":"violet"}>{reseller.is_active===false?pick("تعلیق","Suspended"):enabled&&mother.reseller_enabled?pick("مجاز","Allowed"):pick("بسته","Blocked")}</Badge><label className="toggle module-toggle"><input type="checkbox" checked={enabled} disabled={Boolean(busy)} onChange={e=>void toggleResellerMother(reseller.id,e.target.checked)}/><i/></label>{busy===key&&<small>…</small>}</div>})}</div>:<div className="runtime-empty">{pick("نماینده‌ای وجود ندارد.","No resellers found.")}</div>}
    </Card>

    <Card className="runtime-editor">
      <div className="card-head"><div><b>{pick("قالب نام کاربری اشتراک","Subscription username format")}</b><small>{pick("مستقیم از تنظیمات عمومی Backend خوانده و ذخیره می‌شود","Read and saved directly through the backend general settings API")}</small></div><button className="ghost" disabled={loading||Boolean(busy)} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div>
      <form onSubmit={saveUsername}>
        <div className="setting-grid">
          <label className="field"><span>{pick("پیشوند","Prefix")}</span><input dir="ltr" value={username.prefix} onChange={e=>setUsername(s=>({...s,prefix:e.target.value}))} placeholder="tp"/></label>
          <label className="field"><span>{pick("قالب","Template")}</span><input dir="ltr" value={username.template} onChange={e=>setUsername(s=>({...s,template:e.target.value}))} placeholder="{prefix}{user_id}-{subscription_id}"/></label>
        </div>
        <div className="runtime-info-list"><div><span>{pick("پیش‌نمایش Backend","Backend preview")}</span><b dir="ltr">{username.preview||"—"}</b></div><div><span>{pick("متغیرهای مجاز","Available variables")}</span><b dir="ltr">{username.variables?.join(" · ")||"—"}</b></div></div>
        <div className="action-row"><button className="primary" disabled={Boolean(busy)}>{busy==="username"?pick("در حال ذخیره...","Saving..."):pick("ذخیره تنظیمات","Save settings")}</button></div>
      </form>
    </Card>

    <Card>
      <div className="card-head"><div><b>{pick("ماژول‌های عملیاتی تنظیمات","Operational settings modules")}</b><small>{pick("فقط بخش‌هایی که صفحه عملیاتی مستقل دارند","Only modules with their own operational pages")}</small></div></div>
      <div className="settings-link-grid">
        <Link href="/admin/branding"><b>{pick("برندینگ","Branding")}</b><small>{pick("نام، لوگو و هویت عمومی","Name, logo and public identity")}</small></Link>
        <Link href="/admin/notifications"><b>{pick("اعلان‌ها","Notifications")}</b><small>{pick("کانال‌ها، ارسال و تاریخچه اعلان","Channels, delivery and notification history")}</small></Link>
        <Link href="/admin/sms-reader"><b>SMS Reader</b><small>{pick("دستگاه، Pair و تطبیق پرداخت","Device pairing and payment matching")}</small></Link>
        <Link href="/admin/payments"><b>{pick("پرداخت‌ها","Payments")}</b><small>{pick("تنظیمات و عملیات پرداخت","Payment settings and operations")}</small></Link>
      </div>
    </Card>

    <Card><div className="card-head"><div><b>{pick("اصل طراحی تنظیمات","Settings policy")}</b></div></div><p className="muted">{pick("در این صفحه فقط تنظیمات واقعی و متصل به Backend نگه داشته می‌شوند. تنظیمات VPN/Xray و سلامت پروتکل‌ها در بخش سرورها و امنیت مدیریت می‌شوند؛ L2TP فقط Secret مرکزی را اینجا نگه می‌دارد.","This page only keeps real backend-connected settings. VPN/Xray and protocol health belong to Servers and Security; only the central L2TP secret is kept here.")}</p></Card>
  </div></Shell>;
}
