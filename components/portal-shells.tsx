"use client";

import Link from "next/link";
import {useEffect,useState} from "react";
import {LanguageSwitch,useI18n} from "../lib/i18n";
import {ThemeSwitch} from "../lib/theme";
import {BrandMark} from "../lib/branding";

type MenuItem=readonly [string,string,string,string];

type PortalShellProps={children:React.ReactNode;active?:string;type:"customer"|"reseller"};

const customerMenu:MenuItem[]=[
  ["داشبورد","Dashboard","/panel","⌂"],["اشتراک من","My Subscription","/panel/subscription","▱"],["اتصال","Connection","/panel/connection","⌁"],["مصرف","Usage","/panel/usage","◔"],["کیف پول","Wallet","/panel/wallet","◉"],["پرداخت‌ها","Payments","/panel/payments","◫"],["پشتیبانی","Support","/panel/support","◌"],["اعلان‌ها","Notifications","/panel/notifications","◎"],["پروفایل","Profile","/panel/profile","♙"]
];

const resellerMenu:MenuItem[]=[
  ["داشبورد","Dashboard","/reseller","⌂"],["مشتریان","Customers","/reseller/customers","♙"],["اشتراک‌ها","Subscriptions","/reseller/subscriptions","▱"],["فروش","Sales","/reseller/sales","◫"],["کیف پول","Wallet","/reseller/wallet","◉"],["سفارش‌ها","Orders","/reseller/orders","▤"],["بسته‌های ترافیک","Traffic Packages","/reseller/traffic","◇"],["ربات نمایندگی","Reseller Bot","/reseller/bot","✈"],["اعلان‌ها","Notifications","/reseller/notifications","◎"],["تنظیمات","Settings","/reseller/settings","⚙"]
];

export function PortalShell({children,active="",type}:PortalShellProps){
  const {pick}=useI18n();
  const [collapsed,setCollapsed]=useState(false);
  const [mobileOpen,setMobileOpen]=useState(false);
  const menu=type==="customer"?customerMenu:resellerMenu;
  const storageKey=`twinpanel.${type}.sidebar.collapsed`;

  useEffect(()=>{try{setCollapsed(localStorage.getItem(storageKey)==="1");}catch{}},[storageKey]);
  const toggle=()=>setCollapsed(v=>{const n=!v;try{localStorage.setItem(storageKey,n?"1":"0");}catch{}return n});

  return <div className={`shell portal-shell ${collapsed?"sidebar-collapsed":""} ${mobileOpen?"mobile-menu-open":""}`}>
    <aside className="sidebar">
      <div className="sidebar-head"><BrandMark/><button className="sidebar-collapse" type="button" onClick={toggle}>↔</button><button className="mobile-menu-close" type="button" onClick={()=>setMobileOpen(false)}>×</button></div>
      <nav className="sidebar-nav"><div className="nav-group"><div className="nav-group-title">{type==="customer"?pick("حساب کاربری","Customer Account"):pick("مرکز نمایندگی","Reseller Center")}</div>{menu.map(([fa,en,href,icon])=><Link key={href} href={href} className={active===href?"active":""} title={collapsed?pick(fa,en):undefined} onClick={()=>setMobileOpen(false)}><i>{icon}</i><span className="nav-label">{pick(fa,en)}</span></Link>)}</div></nav>
      <div className="profile"><span className="avatar">M</span><div className="profile-copy"><b>{type==="customer"?pick("کاربر","User"):pick("نماینده فروش","Reseller")}</b><small>{type==="customer"?"Customer":"Partner"}</small></div></div>
    </aside>
    <main><header><button className="mobile-menu-toggle" type="button" onClick={()=>setMobileOpen(v=>!v)}>☰</button><div className="search">⌕ <input placeholder={pick("جستجو...","Search...")}/></div><div className="head-actions"><LanguageSwitch compact/><ThemeSwitch compact/><span className="avatar">M</span></div></header>{children}</main>
  </div>;
}
