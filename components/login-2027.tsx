"use client";

import Link from "next/link";
import {useSearchParams} from "next/navigation";
import {FormEvent,useState} from "react";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";
import {useBranding} from "../lib/branding";
import {customerApi,saveCustomerToken} from "../lib/customer-api";
import {resolvePortal} from "../lib/role-router";

function AuthArt(){
  const {pick}=useI18n();
  const {brand}=useBranding();
  const initial=(brand.shortName||brand.name||"P").trim().charAt(0).toUpperCase();
  return <section className="login-art">
    <div className="brand big"><img src={brand.logoUrl} alt={brand.name}/><div><b>{brand.name}</b></div></div>
    <div className="planet"><span>{initial}</span></div>
    <h2>{pick("اتصال امن، مدیریت ساده","Secure access, simple management")}</h2>
  </section>;
}

function safeNextForPortal(raw:string|null,portal:"admin"|"reseller"|"customer"){
  if(!raw||!raw.startsWith("/")||raw.startsWith("//"))return null;
  const allowed=portal==="admin"?raw.startsWith("/admin"):portal==="reseller"?raw.startsWith("/reseller"):raw.startsWith("/panel");
  return allowed?raw:null;
}

export function LoginPage2027(){
  const {pick}=useI18n();
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
    const portal=await resolvePortal(token,user.role);
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

  return <div className="login login2027">
    <AuthArt/>
    <section className="login-form">
      <div className="login-tools"><LanguageSwitch/><ThemeSwitch/></div>
      <form onSubmit={submit}>
        <h1>{twoFactorToken?pick("تأیید ورود","Verify sign in"):pick("ورود به حساب","Sign in")}</h1>
        {!twoFactorToken&&<>
          <label>{pick("ایمیل","Email")}<input dir="ltr" type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="user@example.com" required/></label>
          <label>{pick("رمز عبور","Password")}<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="••••••••" required/></label>
          <div className="remember"><span><input type="checkbox" checked={remember} onChange={e=>setRemember(e.target.checked)}/> {pick("مرا به خاطر بسپار","Remember me")}</span></div>
        </>}
        {twoFactorToken&&<label>{pick("کد تأیید دو مرحله‌ای","Two-factor code")}<input dir="ltr" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={e=>setCode(e.target.value.replace(/\D/g,"").slice(0,8))} placeholder="000000" required/></label>}
        {error&&<div className="auth-error">{error}</div>}
        <button className="primary full" disabled={busy}>{busy?pick("در حال بررسی...","Please wait..."):twoFactorToken?pick("تأیید و ورود","Verify and sign in"):pick("ورود","Sign in")}</button>
        {twoFactorToken&&<button type="button" className="auth-link-button" onClick={()=>{setTwoFactorToken("");setCode("");setError("");}}>{pick("بازگشت به ورود","Back to sign in")}</button>}
        {!twoFactorToken&&<small className="signup">{pick("حساب ندارید؟","No account?")} <Link href="/register">{pick("ثبت‌نام کاربر","Create customer account")}</Link></small>}
      </form>
    </section>
  </div>;
}

export function RegisterPage2027(){
  const {pick}=useI18n();
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
      window.location.replace("/panel");
    }catch(reason){setError(reason instanceof Error?reason.message:pick("ثبت‌نام ناموفق بود","Registration failed"));}
    finally{setBusy(false);}
  };

  return <div className="login login2027">
    <AuthArt/>
    <section className="login-form">
      <div className="login-tools"><LanguageSwitch/><ThemeSwitch/></div>
      <form onSubmit={submit}>
        <h1>{pick("ساخت حساب کاربری","Create customer account")}</h1>
        <label>{pick("نام","Name")}<input value={name} onChange={e=>setName(e.target.value)} autoComplete="name"/></label>
        <label>{pick("ایمیل","Email")}<input dir="ltr" type="email" value={email} onChange={e=>setEmail(e.target.value)} autoComplete="email" placeholder="user@example.com" required/></label>
        <label>{pick("رمز عبور","Password")}<input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="new-password" placeholder="••••••••" minLength={8} required/></label>
        <label>{pick("تکرار رمز عبور","Confirm password")}<input type="password" value={confirm} onChange={e=>setConfirm(e.target.value)} autoComplete="new-password" placeholder="••••••••" minLength={8} required/></label>
        <div className="customer-only-note">{pick("این فرم فقط حساب کاربر عادی ایجاد می‌کند.","This form creates customer accounts only.")}</div>
        {error&&<div className="auth-error">{error}</div>}
        <button className="primary full" disabled={busy}>{busy?pick("در حال ساخت حساب...","Creating account..."):pick("ثبت‌نام","Create account")}</button>
        <small className="signup">{pick("حساب دارید؟","Already have an account?")} <Link href="/login">{pick("ورود","Sign in")}</Link></small>
      </form>
    </section>
  </div>;
}
