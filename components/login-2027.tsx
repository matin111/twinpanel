"use client";

import Link from "next/link";
import {useSearchParams} from "next/navigation";
import {FormEvent,useState} from "react";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";
import {useBranding} from "../lib/branding";
import {customerApi,saveCustomerToken} from "../lib/customer-api";
import {resolvePortal} from "../lib/role-router";
import {writePortalAccess} from "../lib/access-cache";

function AuthArt(){
  const {pick}=useI18n();
  const {brand}=useBranding();
  return <section className="login-art auth-showcase" aria-label={pick("معرفی برند","Brand showcase")}>
    <div className="auth-brand">
      <img src={brand.logoUrl} alt={brand.name}/>
      <div><b>{brand.name}</b><small>{brand.tagline}</small></div>
    </div>
    <div className="auth-visual" aria-hidden="true">
      <span className="auth-float auth-float-wifi">⌁</span>
      <span className="auth-float auth-float-server">▤</span>
      <span className="auth-float auth-float-bolt">ϟ</span>
      <span className="auth-float auth-float-shield">✓</span>
      <div className="auth-globe"><i/><i/><i/></div>
      <div className="auth-orbit"/>
      <div className="auth-shield"><span>⌾</span></div>
      <div className="auth-pedestal"><i/><i/></div>
    </div>
    <div className="auth-showcase-copy">
      <h2>{pick("اتصال امن، مدیریت ساده","Secure access, simple management")}</h2>
      <p>{pick(`با ${brand.name} سرویس‌ها و اشتراک‌های خود را سریع، امن و یکپارچه مدیریت کنید.`,`Manage your services and subscriptions quickly, securely and seamlessly with ${brand.name}.`)}</p>
      <div className="auth-slider-dots" aria-hidden="true"><i/><i className="active"/><i/></div>
    </div>
  </section>;
}

function safeNextForPortal(raw:string|null,portal:"admin"|"reseller"|"customer"){
  if(!raw||!raw.startsWith("/")||raw.startsWith("//"))return null;
  const allowed=portal==="admin"?raw.startsWith("/admin"):portal==="reseller"?raw.startsWith("/reseller"):raw.startsWith("/panel")||raw.startsWith("/store");
  return allowed?raw:null;
}

export function LoginPage2027(){
  const {pick}=useI18n();
  const {brand}=useBranding();
  const searchParams=useSearchParams();
  const [email,setEmail]=useState("");
  const [password,setPassword]=useState("");
  const [remember,setRemember]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [twoFactorToken,setTwoFactorToken]=useState("");
  const [code,setCode]=useState("");

  const finish=async(token:string)=>{
    saveCustomerToken(token,remember);
    const user=await customerApi.me(token);
    if(!user.is_active)throw new Error(pick("حساب غیرفعال است","Account is inactive"));

    let portal:"admin"|"reseller"|"customer"=String(user.role||"").toLowerCase()==="admin"?"admin":"customer";
    if(portal!=="admin"){
      try{
        portal=await resolvePortal(token,user.role);
      }catch{
        portal="customer";
      }
    }

    writePortalAccess(token,portal,user);
    const fallback=portal==="admin"?"/admin":portal==="reseller"?"/reseller":"/panel";
    const requested=safeNextForPortal(searchParams.get("next"),portal);
    window.location.replace(requested||fallback);
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(busy)return;
    setBusy(true);setError("");
    try{
      if(twoFactorToken){
        const result=await customerApi.verifyTwoFactor(twoFactorToken,code.trim());
        await finish(result.access_token);return;
      }
      const result=await customerApi.login(email.trim().toLowerCase(),password);
      if(result.requires_2fa&&result.two_factor_token){setTwoFactorToken(result.two_factor_token);return;}
      if(!result.access_token)throw new Error(pick("توکن ورود دریافت نشد","Login token was not returned"));
      await finish(result.access_token);
    }catch(reason){setError(reason instanceof Error?reason.message:pick("ورود ناموفق بود","Sign in failed"));}
    finally{setBusy(false);}
  };

  const next=searchParams.get("next");
  const registerHref=next?`/register?next=${encodeURIComponent(next)}`:"/register";

  return <div className="login login2027 auth-page">
    <AuthArt/>
    <section className="login-form auth-form-side">
      <div className="login-tools auth-tools"><LanguageSwitch/><ThemeSwitch/></div>
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-card-icon" aria-hidden="true">◇</div>
        <h1>{twoFactorToken?pick("تأیید ورود","Verify sign in"):pick("ورود به حساب","Sign in")}</h1>
        <p className="auth-card-subtitle">{twoFactorToken?pick("کد تأیید حساب خود را وارد کنید.","Enter your account verification code."):pick(`دسترسی امن و سریع به پنل مدیریت ${brand.name}`,`Secure, fast access to the ${brand.name} management panel`)}</p>
        {!twoFactorToken&&<>
          <label className="auth-field"><span>{pick("ایمیل","Email")}</span><div><input dir="ltr" type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="user@example.com" required/><i aria-hidden="true">✉</i></div></label>
          <label className="auth-field"><span>{pick("رمز عبور","Password")}</span><div><input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="••••••••" required/><i aria-hidden="true">♙</i></div></label>
          <div className="remember auth-remember"><span><input type="checkbox" checked={remember} onChange={e=>setRemember(e.target.checked)}/> {pick("مرا به خاطر بسپار","Remember me")}</span></div>
        </>}
        {twoFactorToken&&<label className="auth-field"><span>{pick("کد تأیید دو مرحله‌ای","Two-factor code")}</span><div><input dir="ltr" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,"").slice(0,8))} placeholder="000000" required/><i aria-hidden="true">#</i></div></label>}
        {error&&<div className="auth-error">{error}</div>}
        <button className="primary full auth-submit" disabled={busy}>{busy?pick("در حال بررسی...","Please wait..."):twoFactorToken?pick("تأیید و ورود","Verify and sign in"):pick("ورود","Sign in")}<span aria-hidden="true">↵</span></button>
        {twoFactorToken&&<button type="button" className="auth-link-button" onClick={()=>{setTwoFactorToken("");setCode("");setError("");}}>{pick("بازگشت به ورود","Back to sign in")}</button>}
        {!twoFactorToken&&<small className="signup auth-signup">{pick("حساب ندارید؟","No account?")} <Link href={registerHref}>{pick("ثبت‌نام کاربر","Create customer account")}</Link></small>}
      </form>
    </section>
  </div>;
}

export function RegisterPage2027(){
  const {pick}=useI18n();
  const {brand}=useBranding();
  const searchParams=useSearchParams();
  const [name,setName]=useState("");
  const [email,setEmail]=useState("");
  const [password,setPassword]=useState("");
  const [confirm,setConfirm]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");

  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(busy)return;
    if(password.length<8){setError(pick("رمز عبور حداقل ۸ کاراکتر باشد","Password must be at least 8 characters"));return;}
    if(password!==confirm){setError(pick("تکرار رمز عبور یکسان نیست","Passwords do not match"));return;}
    setBusy(true);setError("");
    try{
      const result=await customerApi.register(email.trim().toLowerCase(),password,name.trim());
      saveCustomerToken(result.access_token,true);
      const user=await customerApi.me(result.access_token);
      writePortalAccess(result.access_token,"customer",user);
      const requested=safeNextForPortal(searchParams.get("next"),"customer");
      window.location.replace(requested||"/panel");
    }catch(reason){setError(reason instanceof Error?reason.message:pick("ثبت‌نام ناموفق بود","Registration failed"));}
    finally{setBusy(false);}
  };

  const next=searchParams.get("next");
  const loginHref=next?`/login?next=${encodeURIComponent(next)}`:"/login";

  return <div className="login login2027 auth-page">
    <AuthArt/>
    <section className="login-form auth-form-side">
      <div className="login-tools auth-tools"><LanguageSwitch/><ThemeSwitch/></div>
      <form className="auth-card auth-card-register" onSubmit={submit}>
        <div className="auth-card-icon" aria-hidden="true">◇</div>
        <h1>{pick("ساخت حساب کاربری","Create customer account")}</h1>
        <p className="auth-card-subtitle">{pick(`حساب خود را برای استفاده از خدمات ${brand.name} ایجاد کنید.`,`Create your account to use ${brand.name} services.`)}</p>
        <label className="auth-field"><span>{pick("نام","Name")}</span><div><input value={name} onChange={e=>setName(e.target.value)} autoComplete="name"/><i aria-hidden="true">◌</i></div></label>
        <label className="auth-field"><span>{pick("ایمیل","Email")}</span><div><input dir="ltr" type="email" value={email} onChange={e=>setEmail(e.target.value)} autoComplete="email" placeholder="user@example.com" required/><i aria-hidden="true">✉</i></div></label>
        <label className="auth-field"><span>{pick("رمز عبور","Password")}</span><div><input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="new-password" placeholder="••••••••" minLength={8} required/><i aria-hidden="true">♙</i></div></label>
        <label className="auth-field"><span>{pick("تکرار رمز عبور","Confirm password")}</span><div><input type="password" value={confirm} onChange={e=>setConfirm(e.target.value)} autoComplete="new-password" placeholder="••••••••" minLength={8} required/><i aria-hidden="true">♙</i></div></label>
        <div className="customer-only-note">{pick("این فرم فقط حساب کاربر عادی ایجاد می‌کند.","This form creates customer accounts only.")}</div>
        {error&&<div className="auth-error">{error}</div>}
        <button className="primary full auth-submit" disabled={busy}>{busy?pick("در حال ساخت حساب...","Creating account..."):pick("ثبت‌نام","Create account")}<span aria-hidden="true">↵</span></button>
        <small className="signup auth-signup">{pick("حساب دارید؟","Already have an account?")} <Link href={loginHref}>{pick("ورود","Sign in")}</Link></small>
      </form>
    </section>
  </div>;
}
