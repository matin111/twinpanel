"use client";

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
const emptyMother:MotherAccessSettings={admin_enabled:true,reseller_enabled:false,reseller_overrides:{},mother_node_id:0,mother_name:"",mother_public_domain:"",mother_public_ip:""};

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
  const [activeTab,setActiveTab]=useState<"account"|"network"|"subscriptions">("account");
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
      generalSettingsApi.me(),generalSettingsApi.subscriptionUsername(),generalSettingsApi.twoFactorStatus(),
      generalSettingsApi.l2tp(),generalSettingsApi.motherAccess(),generalSettingsApi.resellers(),
    ]);
    const failures:string[]=[];
    if(results[0].status==="fulfilled"){const value=results[0].value as SettingsUser;setProfile(value);setEmailDraft(value.email||"");}else failures.push(String(results[0].reason));
    if(results[1].status==="fulfilled")setUsername(results[1].value as SubscriptionUsernameSettings);else failures.push(String(results[1].reason));
    if(results[2].status==="fulfilled")setTwoFactorEnabled(Boolean(results[2].value.enabled));else failures.push(String(results[2].reason));
    if(results[3].status==="fulfilled"){const value=results[3].value as L2tpSettings;setL2tp(value);setL2tpDraft(value.psk||"");}else failures.push(String(results[3].reason));
    if(results[4].status==="fulfilled")setMother(results[4].value as MotherAccessSettings);else failures.push(String(results[4].reason));
    if(results[5].status==="fulfilled")setResellers(results[5].value as SettingsReseller[]);else failures.push(String(results[5].reason));
    if(failures.length)setError(failures[0]);
    setLoading(false);
  };
  useEffect(()=>{void load();},[]);

  const saveEmail=async(event:FormEvent)=>{event.preventDefault();if(!begin("email"))return;try{const value=await generalSettingsApi.updateEmail({email:emailDraft.trim(),current_password:emailPassword});setProfile(value);setEmailDraft(value.email||"");setEmailPassword("");setOk(pick("ایمیل مدیر ذخیره شد","Admin email saved"));}catch(e){setFailure(e);}finally{finish();}};
  const savePassword=async(event:FormEvent)=>{event.preventDefault();if(!begin("password"))return;if(newPassword!==confirmPassword){setError(pick("تکرار رمز جدید یکسان نیست.","Password confirmation does not match."));finish();return;}try{await generalSettingsApi.changePassword({current_password:currentPassword,new_password:newPassword});setCurrentPassword("");setNewPassword("");setConfirmPassword("");setOk(pick("رمز عبور تغییر کرد","Password changed"));}catch(e){setFailure(e);}finally{finish();}};
  const setup2fa=async()=>{if(!begin("2fa-setup"))return;try{setTwoFactorSetup(await generalSettingsApi.twoFactorSetup());setTwoFactorCode("");}catch(e){setFailure(e);}finally{finish();}};
  const enable2fa=async()=>{if(!begin("2fa-enable"))return;try{await generalSettingsApi.twoFactorEnable(twoFactorCode.trim());setTwoFactorEnabled(true);setTwoFactorSetup(null);setTwoFactorCode("");setOk(pick("ورود دومرحله‌ای فعال شد","Two-factor authentication enabled"));}catch(e){setFailure(e);}finally{finish();}};
  const disable2fa=async()=>{if(!begin("2fa-disable"))return;try{await generalSettingsApi.twoFactorDisable({current_password:twoFactorDisablePassword,code:twoFactorDisableCode.trim()});setTwoFactorEnabled(false);setTwoFactorDisablePassword("");setTwoFactorDisableCode("");setOk(pick("ورود دومرحله‌ای غیرفعال شد","Two-factor authentication disabled"));}catch(e){setFailure(e);}finally{finish();}};
  const generatePsk=async()=>{if(!begin("l2tp-generate"))return;try{const value=await generalSettingsApi.generateL2tpPsk();setL2tpDraft(value.psk);setShowPsk(true);}catch(e){setFailure(e);}finally{finish();}};
  const savePsk=async()=>{if(!l2tpDraft.trim()){setError(pick("Secret نمی‌تواند خالی باشد.","Secret cannot be empty."));return;}if(!window.confirm(pick("Secret جدید روی تمام سرورهای خروجی فعال L2TP اعمال شود؟","Apply this secret to all active L2TP exit servers?")))return;if(!begin("l2tp-save"))return;try{const result=await generalSettingsApi.saveL2tpPsk(l2tpDraft.trim());const current=await generalSettingsApi.l2tp();setL2tp(current);setL2tpDraft(current.psk||"");const count=result.synced_nodes?.length??0;setOk(result.changed?pick(`Secret ذخیره شد؛ ${count} سرور بروزرسانی شد.`,`Secret saved; ${count} servers updated.`):pick("Secret تغییری نکرد.","Secret was unchanged."));}catch(e){setFailure(e);}finally{finish();}};
  const saveMother=async()=>{if(!begin("mother-global"))return;try{const result=await generalSettingsApi.saveMotherAccess({admin_enabled:mother.admin_enabled,reseller_enabled:mother.reseller_enabled,mother_name:mother.mother_name.trim(),public_domain:mother.mother_public_domain.trim()});setMother(v=>({...v,...result}));setOk(pick("تنظیمات سرور مادر ذخیره شد","Mother-server settings saved"));}catch(e){setFailure(e);}finally{finish();}};
  const toggleResellerMother=async(resellerId:number,enabled:boolean)=>{const key=`mother-reseller:${resellerId}`;if(!begin(key))return;try{await generalSettingsApi.setResellerMotherAccess(resellerId,enabled);setMother(v=>({...v,reseller_overrides:{...v.reseller_overrides,[String(resellerId)]:enabled}}));setOk(pick("دسترسی نماینده ذخیره شد","Reseller access saved"));}catch(e){setFailure(e);}finally{finish();}};
  const saveUsername=async(event:FormEvent)=>{event.preventDefault();if(!begin("username"))return;try{const result=await generalSettingsApi.saveSubscriptionUsername({prefix:username.prefix,template:username.template});setUsername(result);setOk(pick("قالب نام کاربری ذخیره شد","Username format saved"));}catch(e){setFailure(e);}finally{finish();}};
  const copyText=async(value:string)=>{try{await navigator.clipboard.writeText(value);setOk(pick("کپی شد","Copied"));setError("");}catch{setError(pick("کپی در مرورگر مجاز نیست.","Clipboard access is unavailable."));}};
  const enabledResellerOverrides=useMemo(()=>Object.values(mother.reseller_overrides||{}).filter(Boolean).length,[mother.reseller_overrides]);

  return <Shell active="/admin/settings"><div className="page settings-compact">
    <PageHead title={pick("تنظیمات سیستم","System Settings")}/>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}{loading&&<div className="runtime-loading">{pick("در حال دریافت تنظیمات...","Loading settings...")}</div>}

    <nav className="settings-compact-tabs" aria-label={pick("دسته‌بندی تنظیمات","Settings categories")}>
      {([
        ["account",pick("حساب و امنیت","Account & security"),pick("ایمیل، رمز، 2FA و ظاهر","Email, password, 2FA & appearance")],
        ["network",pick("سرورها و پروتکل‌ها","Servers & protocols"),pick("L2TP و سرور مادر","L2TP & mother server")],
        ["subscriptions",pick("تنظیمات اشتراک","Subscriptions"),pick("قالب نام کاربری","Username format")],
      ] as const).map(([id,label,description])=><button key={id} type="button" className={`settings-compact-tab ${activeTab===id?"is-active":""}`} aria-current={activeTab===id?"page":undefined} onClick={()=>setActiveTab(id)}><strong>{label}</strong><small>{description}</small></button>)}
    </nav>
    {activeTab==="account"&&<section className="settings-compact-section" aria-label={pick("حساب و امنیت","Account & security")}>
    <div className="module-grid two settings2027-live">
      <Card><div className="card-head"><b>{pick("حساب مدیر","Admin account")}</b><Badge tone={profile?.is_active?"ok":"warn"}>{profile?.is_active?pick("فعال","Active"):pick("نامشخص","Unknown")}</Badge></div><div className="runtime-info-list"><div><span>{pick("نام","Name")}</span><b>{profile?.full_name||"—"}</b></div><div><span>{pick("نقش","Role")}</span><b dir="ltr">{profile?.role||"—"}</b></div><div><span>ID</span><b dir="ltr">{profile?.id??"—"}</b></div></div><form onSubmit={saveEmail}><label className="field"><span>{pick("ایمیل","Email")}</span><input type="email" dir="ltr" value={emailDraft} onChange={e=>setEmailDraft(e.target.value)} required/></label><label className="field"><span>{pick("رمز فعلی","Current password")}</span><input type="password" value={emailPassword} onChange={e=>setEmailPassword(e.target.value)} required autoComplete="current-password"/></label><button className="primary" disabled={Boolean(busy)}>{busy==="email"?pick("در حال ذخیره...","Saving..."):pick("ذخیره ایمیل","Save email")}</button></form></Card>
      <Card><div className="card-head"><b>{pick("نمایش پنل","Panel appearance")}</b><Badge tone="violet">{mode.toUpperCase()} · {resolved}</Badge></div><div className="theme-setting-panel"><ThemeSwitch/></div></Card>
    </div>

    <div className="module-grid two">
      <Card><div className="card-head"><b>{pick("تغییر رمز عبور","Change password")}</b></div><form onSubmit={savePassword}><label className="field"><span>{pick("رمز فعلی","Current password")}</span><input type="password" value={currentPassword} onChange={e=>setCurrentPassword(e.target.value)} required autoComplete="current-password"/></label><label className="field"><span>{pick("رمز جدید","New password")}</span><input type="password" minLength={8} value={newPassword} onChange={e=>setNewPassword(e.target.value)} required autoComplete="new-password"/></label><label className="field"><span>{pick("تکرار رمز جدید","Confirm new password")}</span><input type="password" minLength={8} value={confirmPassword} onChange={e=>setConfirmPassword(e.target.value)} required autoComplete="new-password"/></label><button className="primary" disabled={Boolean(busy)}>{busy==="password"?pick("در حال تغییر...","Changing..."):pick("تغییر رمز","Change password")}</button></form></Card>
      <Card><div className="card-head"><b>{pick("ورود دومرحله‌ای","Two-factor authentication")}</b><Badge tone={twoFactorEnabled?"ok":"warn"}>{twoFactorEnabled?pick("فعال","Enabled"):pick("غیرفعال","Disabled")}</Badge></div>{!twoFactorEnabled&&<>{!twoFactorSetup?<button className="primary" disabled={Boolean(busy)} onClick={()=>void setup2fa()}>{busy==="2fa-setup"?"…":pick("راه‌اندازی 2FA","Set up 2FA")}</button>:<><label className="field"><span>{pick("کلید Authenticator","Authenticator key")}</span><div className="secret-field"><input dir="ltr" readOnly value={twoFactorSetup.secret}/><button type="button" onClick={()=>void copyText(twoFactorSetup.secret)}>{pick("کپی","Copy")}</button></div></label><label className="field"><span>{pick("کد ۶ رقمی","6-digit code")}</span><input dir="ltr" inputMode="numeric" maxLength={6} value={twoFactorCode} onChange={e=>setTwoFactorCode(e.target.value.replace(/\D/g,""))}/></label><button className="primary" disabled={Boolean(busy)||twoFactorCode.length!==6} onClick={()=>void enable2fa()}>{pick("فعال‌سازی","Enable")}</button></>}</>}{twoFactorEnabled&&<><label className="field"><span>{pick("رمز فعلی","Current password")}</span><input type="password" value={twoFactorDisablePassword} onChange={e=>setTwoFactorDisablePassword(e.target.value)}/></label><label className="field"><span>{pick("کد 2FA","2FA code")}</span><input dir="ltr" inputMode="numeric" maxLength={6} value={twoFactorDisableCode} onChange={e=>setTwoFactorDisableCode(e.target.value.replace(/\D/g,""))}/></label><button className="ghost" disabled={Boolean(busy)||twoFactorDisableCode.length!==6||!twoFactorDisablePassword} onClick={()=>void disable2fa()}>{pick("غیرفعال‌سازی 2FA","Disable 2FA")}</button></>}</Card>
    </div>

    </section>}
    {activeTab==="network"&&<section className="settings-compact-section" aria-label={pick("سرورها و پروتکل‌ها","Servers & protocols")}>
    <Card><div className="card-head"><b>{pick("Secret مرکزی L2TP / IPsec","Central L2TP / IPsec secret")}</b><Badge tone="violet">{l2tp.exit_count} {pick("سرور خروجی","exit servers")}</Badge></div><label className="field"><span>IPsec Secret</span><div className="secret-field"><input dir="ltr" type={showPsk?"text":"password"} value={l2tpDraft} onChange={e=>setL2tpDraft(e.target.value)} maxLength={64}/><button type="button" onClick={()=>setShowPsk(v=>!v)}>{showPsk?pick("پنهان","Hide"):pick("نمایش","Show")}</button></div></label><div className="action-row"><button className="ghost" disabled={Boolean(busy)} onClick={()=>void generatePsk()}>{busy==="l2tp-generate"?"…":pick("ساخت Secret","Generate secret")}</button><button className="primary" disabled={Boolean(busy)||!l2tpDraft.trim()} onClick={()=>void savePsk()}>{busy==="l2tp-save"?"…":pick("ذخیره و همگام‌سازی","Save & sync")}</button></div></Card>

    <Card>
      <div className="card-head"><div><b>{pick("سرور مادر","Mother server")}</b><small>{pick("نام و دامنه سرور مادر + دسترسی در سرورهای تکی اشتراک. سرور مادر هیچ‌وقت وارد Multi-Link نمی‌شود.","Mother identity/domain plus visibility in individual subscription servers. Mother never participates in Multi-Link.")}</small></div><Badge tone="violet">{enabledResellerOverrides}/{resellers.length}</Badge></div>
      <div className="setting-grid"><label className="field"><span>{pick("نام سرور مادر","Mother server name")}</span><input maxLength={120} value={mother.mother_name} onChange={e=>setMother(v=>({...v,mother_name:e.target.value}))} placeholder={pick("سرور مرکزی","Central server")}/></label><label className="field"><span>{pick("دامنه عمومی سرور مادر","Mother public domain")}</span><input dir="ltr" value={mother.mother_public_domain} onChange={e=>setMother(v=>({...v,mother_public_domain:e.target.value}))} placeholder="vpn.example.com"/></label></div>
      <div className="runtime-info-list"><div><span>Node ID</span><b>#{mother.mother_node_id||"—"}</b></div><div><span>{pick("IP فعلی","Current IP")}</span><b dir="ltr">{mother.mother_public_ip||"—"}</b></div></div>
      <label className="toggle module-toggle"><span>{pick("نمایش سرور مادر در اشتراک‌های مدیر","Show Mother in admin subscriptions")}</span><input type="checkbox" checked={mother.admin_enabled} onChange={e=>setMother(v=>({...v,admin_enabled:e.target.checked}))}/><i/></label>
      <label className="toggle module-toggle"><span>{pick("نمایش سرور مادر در اشتراک‌های نمایندگان","Show Mother in reseller subscriptions")}</span><input type="checkbox" checked={mother.reseller_enabled} onChange={e=>setMother(v=>({...v,reseller_enabled:e.target.checked}))}/><i/></label>
      <div className="action-row"><button className="primary" disabled={Boolean(busy)||!mother.mother_name.trim()} onClick={()=>void saveMother()}>{busy==="mother-global"?"…":pick("ذخیره تنظیمات سرور مادر","Save Mother settings")}</button></div>
      {resellers.length>0&&<div className="runtime-info-list">{resellers.map(reseller=>{const enabled=Boolean(mother.reseller_overrides?.[String(reseller.id)]);return <div key={reseller.id}><span><b>{reseller.name}</b>{reseller.code?` · ${reseller.code}`:""}</span><label className="toggle module-toggle"><input type="checkbox" checked={enabled} disabled={!mother.reseller_enabled||Boolean(busy)} onChange={e=>void toggleResellerMother(reseller.id,e.target.checked)}/><i/></label></div>;})}</div>}
    </Card>

    </section>}
    {activeTab==="subscriptions"&&<section className="settings-compact-section" aria-label={pick("تنظیمات اشتراک","Subscriptions")}>
    <Card className="runtime-editor"><div className="card-head"><b>{pick("نام کاربری اشتراک","Subscription username")}</b><button className="ghost" disabled={loading||Boolean(busy)} onClick={()=>void load()}>{pick("بروزرسانی","Refresh")}</button></div><form onSubmit={saveUsername}><div className="setting-grid"><label className="field"><span>{pick("پیشوند","Prefix")}</span><input dir="ltr" value={username.prefix} onChange={e=>setUsername(s=>({...s,prefix:e.target.value}))} placeholder="mv"/></label><label className="field"><span>{pick("قالب","Template")}</span><input dir="ltr" value={username.template} onChange={e=>setUsername(s=>({...s,template:e.target.value}))} placeholder="{prefix}{sub_id}_{user_id}"/></label></div><div className="runtime-info-list"><div><span>{pick("پیش‌نمایش","Preview")}</span><b dir="ltr">{username.preview||"—"}</b></div><div><span>{pick("متغیرها","Variables")}</span><b dir="ltr">{username.variables?.join(" · ")||"—"}</b></div></div><button className="primary" disabled={Boolean(busy)}>{busy==="username"?pick("در حال ذخیره...","Saving..."):pick("ذخیره قالب","Save format")}</button></form></Card>
    </section>}
    <style>{`
      .settings-compact {max-width:1440px;margin-inline:auto}
      .settings-compact-tabs {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0 0 18px;direction:rtl}
      .settings-compact-tab {appearance:none;border:1px solid var(--border,#263248);border-radius:13px;background:var(--card,#101827);color:inherit;text-align:start;padding:13px 16px;min-height:67px;cursor:pointer;display:flex;flex-direction:column;gap:4px;transition:border-color .15s,background .15s}
      .settings-compact-tab:hover {border-color:#4f7dca}
      .settings-compact-tab.is-active {border-color:#387ef5;background:color-mix(in srgb,#2563eb 12%,var(--card,#101827))}
      .settings-compact-tab strong {font-size:13px;font-weight:750}
      .settings-compact-tab small {font-size:11px;opacity:.65;font-weight:400}
      .settings-compact-section {display:grid;gap:14px;min-width:0;direction:rtl}
      .settings-compact-section .module-grid.two {align-items:start;gap:14px}
      .settings-compact-section .module-grid.two>* {align-self:start;min-height:0!important;height:auto!important}
      .settings-compact-section .card {min-height:0}
      .settings-compact-section .card-head {margin-bottom:12px}
      .settings-compact-section .field {margin-bottom:9px}
      .settings-compact-section .field input {min-height:40px}
      .settings-compact-section form {display:flex;flex-direction:column;gap:8px}
      .settings-compact-section .runtime-info-list {margin-block:9px}
      .settings-compact-section .runtime-info-list>div {padding-block:7px}
      .settings-compact-section .action-row {display:flex;flex-wrap:wrap;gap:8px}
      .settings-compact-section .theme-setting-panel {padding:8px;min-height:0}
      .settings-compact-section .module-toggle {padding-block:9px}
      .settings-compact-section .setting-grid {gap:12px}
      .settings-compact-section .primary,.settings-compact-section .ghost {max-width:100%}
      @media(max-width:700px) {
        .settings-compact-tabs {gap:6px}
        .settings-compact-tab {padding:10px;min-height:56px}
        .settings-compact-tab strong {font-size:11px}
        .settings-compact-tab small {display:none}
        .settings-compact-section .module-grid.two,.settings-compact-section .setting-grid {grid-template-columns:minmax(0,1fr)}
      }
    `}</style>
  </div></Shell>;
}
