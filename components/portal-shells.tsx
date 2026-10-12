"use client";

import Link from "next/link";
import {useEffect,useState} from "react";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";
import {BrandMark} from "../lib/branding";
import {CustomerSessionProvider,useCustomerSession} from "../lib/customer-session";
import {clearCustomerToken,customerApi,getCustomerToken} from "../lib/customer-api";
import {getResellerProfile} from "../lib/role-router";
import {CustomerNotificationCenter} from "./customer-notification-center";

type MenuItem=readonly [string,string,string,string];
type PortalShellProps={children:React.ReactNode;active?:string;type:"customer"|"reseller"};

const customerMenu:MenuItem[]=[
  ["داشبورد","Dashboard","/panel","⌂"],
  ["خرید اشتراک","Buy Subscription","/panel/buy","◇"],
  ["اشتراک من","My Subscription","/panel/subscription","▱"],
  ["اتصال و کانفیگ","Connection","/panel/connection","⌁"],
  ["مصرف","Usage","/panel/usage","◔"],
  ["سفارش‌ها","Orders","/panel/orders","▤"],
  ["کیف پول","Wallet","/panel/wallet","◉"],
  ["پرداخت‌ها","Payments","/panel/payments","◫"],
  ["پشتیبانی","Support","/panel/support","◌"],
  ["اعلان‌ها","Notifications","/panel/notifications","◎"],
  ["پروفایل و امنیت","Profile & Security","/panel/profile","♙"]
];

const resellerMenu:MenuItem[]=[
  ["داشبورد","Dashboard","/reseller","⌂"],["مشتریان","Customers","/reseller/customers","♙"],["اشتراک‌ها","Subscriptions","/reseller/subscriptions","▱"],["فروش","Sales","/reseller/sales","◫"],["کیف پول","Wallet","/reseller/wallet","◉"],["سفارش‌ها","Orders","/reseller/orders","▤"],["بسته‌های ترافیک","Traffic Packages","/reseller/traffic","◇"],["ربات نمایندگی","Reseller Bot","/reseller/bot","✈"],["اعلان‌ها","Notifications","/reseller/notifications","◎"],["تنظیمات","Settings","/reseller/settings","⚙"]
];

function CustomerIdentity(){
  const {pick}=useI18n();
  const {user,logout}=useCustomerSession();
  const initial=(user?.full_name||user?.email||"U").trim().charAt(0).toUpperCase();
  return <div className="portal-identity">
    <div className="profile"><span className="avatar">{initial}</span><div className="profile-copy"><b>{user?.full_name||pick("کاربر","Customer")}</b><small>{user?.email||"Customer"}</small></div></div>
    <button type="button" className="portal-logout" onClick={logout}>{pick("خروج","Sign out")}</button>
  </div>;
}

function ResellerAccessGuard({children}:{children:React.ReactNode}){
  const {pick}=useI18n();
  const [ready,setReady]=useState(false);
  const [error,setError]=useState("");
  useEffect(()=>{
    let alive=true;
    const run=async()=>{
      const token=getCustomerToken();
      if(!token){window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);return;}
      let account;
      try{account=await customerApi.me(token);}catch{clearCustomerToken();window.location.replace("/login");return;}
      if(!alive)return;
      if(!account.is_active){clearCustomerToken();window.location.replace("/login");return;}
      if(account.role==="admin"){window.location.replace("/admin");return;}
      try{
        const reseller=await getResellerProfile(token);
        if(!alive)return;
        if(!reseller){window.location.replace("/panel");return;}
        setReady(true);
      }catch(reason){if(alive)setError(reason instanceof Error?reason.message:String(reason));}
    };
    void run();
    return()=>{alive=false};
  },[]);
  if(error)return <div className="auth-gate"><div className="auth-gate-card"><b>{pick("بررسی دسترسی نمایندگی ناموفق بود","Could not verify reseller access")}</b><small>{error}</small><button className="ghost" onClick={()=>window.location.reload()}>{pick("تلاش دوباره","Retry")}</button></div></div>;
  if(!ready)return <div className="auth-gate"><div className="auth-gate-card"><span className="spinner"/><b>{pick("در حال بررسی دسترسی نمایندگی...","Checking reseller access...")}</b></div></div>;
  return <>{children}</>;
}

function PortalFrame({children,active="",type}:PortalShellProps){
  const {pick}=useI18n();
  const [collapsed,setCollapsed]=useState(false);
  const [mobileOpen,setMobileOpen]=useState(false);
  const menu=type==="customer"?customerMenu:resellerMenu;
  const storageKey=`twinpanel.${type}.sidebar.collapsed`;

  const toggle=()=>setCollapsed(v=>{
    const n=!v;
    try{localStorage.setItem(storageKey,n?"1":"0");}catch{}
    return n;
  });

  return <div className={`shell portal-shell ${collapsed?"sidebar-collapsed":""} ${mobileOpen?"mobile-menu-open":""}`}>
    <aside className="sidebar">
      <div className="sidebar-head"><BrandMark/><button className="sidebar-collapse" type="button" onClick={toggle}>↔</button><button className="mobile-menu-close" type="button" onClick={()=>setMobileOpen(false)}>×</button></div>
      <nav className="sidebar-nav"><div className="nav-group"><div className="nav-group-title">{type==="customer"?pick("حساب کاربری","Customer Account"):pick("مرکز نمایندگی","Reseller Center")}</div>{menu.map(([fa,en,href,icon])=><Link key={href} href={href} className={active===href?"active":""} title={collapsed?pick(fa,en):undefined} onClick={()=>setMobileOpen(false)}><i>{icon}</i><span className="nav-label">{pick(fa,en)}</span></Link>)}</div></nav>
      {type==="customer"?<CustomerIdentity/>:<div className="profile"><span className="avatar">R</span><div className="profile-copy"><b>{pick("نماینده فروش","Reseller")}</b><small>Partner</small></div></div>}
    </aside>
    <main><header><button className="mobile-menu-toggle" type="button" onClick={()=>setMobileOpen(v=>!v)} aria-expanded={mobileOpen}>☰</button><div className="search">⌕ <input placeholder={pick("جستجو...","Search...")}/></div><div className="head-actions">{type==="customer"&&<CustomerNotificationCenter/>}<LanguageSwitch compact/><ThemeSwitch compact/></div></header>{children}</main>
  </div>;
}

export function PortalShell(props:PortalShellProps){
  if(props.type==="customer")return <CustomerSessionProvider><PortalFrame {...props}/></CustomerSessionProvider>;
  return <ResellerAccessGuard><PortalFrame {...props}/></ResellerAccessGuard>;
}
