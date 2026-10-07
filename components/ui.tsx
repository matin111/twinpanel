"use client";

import Link from "next/link";
import {LanguageSwitch,useI18n} from "../lib/i18n";

const menu=[
  ["داشبورد","Dashboard","/admin","⌂"],
  ["کاربران","Users","/admin/users","♙"],
  ["اشتراک‌ها","Subscriptions","/admin/subscriptions","▱"],
  ["پلن‌ها","Plans","/admin/plans","◈"],
  ["نودها","Nodes","/admin/nodes","▦"],
  ["تانل‌ها","Tunnels","/admin/tunnels","⤨"],
  ["پرداخت‌ها","Payments","/admin/payments","◫"],
  ["پشتیبانی","Support","/admin/support","◌"],
  ["اعلان‌ها","Notifications","/admin/notifications","◉"],
  ["تنظیمات","Settings","/admin/settings","⚙"]
] as const;

export function Shell({children,active="/admin"}:{children:React.ReactNode;active?:string}){
  const {pick}=useI18n();
  return <div className="shell">
    <aside>
      <div className="brand"><img src="/logo.svg" alt="TwinPanel"/><div><b>TwinPanel</b><small>CONTROL 2027</small></div></div>
      <nav>{menu.map(([fa,en,h,i])=><Link key={h} href={h} className={active===h?"active":""}><i>{i}</i>{pick(fa,en)}</Link>)}</nav>
      <div className="profile"><span className="avatar">M</span><div><b>{pick("مدیر سیستم","System Admin")}</b><small>Administrator</small></div></div>
    </aside>
    <main>
      <header>
        <div className="search">⌕ <input placeholder={pick("جستجو در پنل...","Search panel...")}/></div>
        <div className="head-actions"><LanguageSwitch compact/><button type="button">◐</button><button className="notify" type="button">◉</button><span className="avatar">M</span></div>
      </header>
      {children}
    </main>
  </div>;
}

export function PageHead({title,sub,action}:{title:string;sub:string;action?:string}){
  return <div className="page-head"><div><small>TWINPANEL 2027</small><h1>{title}</h1><p>{sub}</p></div>{action&&<button className="primary">＋ {action}</button>}</div>;
}

export function Card({children,className=""}:{children:React.ReactNode;className?:string}){
  return <section className={`card ${className}`}>{children}</section>;
}

export function Stat({label,value,delta,icon="◈"}:{label:string;value:string;delta?:string;icon?:string}){
  return <Card className="stat"><span className="stat-icon">{icon}</span><div><small>{label}</small><b>{value}</b>{delta&&<em>{delta}</em>}</div></Card>;
}

export function Badge({children,tone="ok"}:{children:React.ReactNode;tone?:"ok"|"warn"|"bad"|"violet"}){
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function Toolbar(){
  const {pick}=useI18n();
  return <div className="toolbar"><label>⌕ <input placeholder={pick("جستجو...","Search...")}/></label><button>{pick("همه وضعیت‌ها","All statuses")}⌄</button><button>{pick("فیلترها","Filters")}⌄</button></div>;
}

export const names=[
  ["علی رضایی","Ali Rezaei"],
  ["سارا محمدی","Sara Mohammadi"],
  ["محمد کریمی","Mohammad Karimi"],
  ["نگار حسینی","Negar Hosseini"],
  ["رضا احمدی","Reza Ahmadi"]
] as const;
