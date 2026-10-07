"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";
import {useEffect,useState} from "react";
import {useI18n} from "../lib/i18n";

const items=[
  ["plans","پلن‌ها","Plans"],
  ["protocols","پروتکل‌ها","Protocols"],
  ["guides","آموزش اتصال","Setup guides"],
  ["faq","سوالات متداول","FAQ"]
] as const;

export function StoreMobileAccess(){
  const pathname=usePathname();
  const {pick}=useI18n();
  const [open,setOpen]=useState(false);
  const isStore=pathname==="/"||pathname==="/store";

  useEffect(()=>{setOpen(false)},[pathname]);
  useEffect(()=>{
    if(!open)return;
    const onKey=(event:KeyboardEvent)=>{if(event.key==="Escape")setOpen(false)};
    window.addEventListener("keydown",onKey);
    return ()=>window.removeEventListener("keydown",onKey);
  },[open]);

  if(!isStore)return null;

  const jump=(id:string)=>{
    setOpen(false);
    window.setTimeout(()=>document.getElementById(id)?.scrollIntoView({behavior:"smooth",block:"start"}),30);
  };

  return <>
    <button className="store-mobile-open" type="button" onClick={()=>setOpen(true)} aria-label={pick("باز کردن منوی فروشگاه","Open store menu")} aria-expanded={open}>☰</button>
    <Link className="store-register-quick" href="/register">{pick("ثبت‌نام","Register")}</Link>
    <div className={`store-mobile-drawer ${open?"open":""}`} aria-hidden={!open}>
      <button className="store-mobile-overlay" type="button" onClick={()=>setOpen(false)} aria-label={pick("بستن منو","Close menu")}/>
      <aside>
        <div className="store-mobile-head"><b>{pick("منوی فروشگاه","Store menu")}</b><button type="button" onClick={()=>setOpen(false)}>×</button></div>
        <nav>
          {items.map(([id,fa,en])=><button type="button" key={id} onClick={()=>jump(id)}>{pick(fa,en)}</button>)}
        </nav>
        <div className="store-mobile-account">
          <Link className="primary" href="/register" onClick={()=>setOpen(false)}>{pick("ساخت حساب کاربری","Create customer account")}</Link>
          <Link className="ghost" href="/login" onClick={()=>setOpen(false)}>{pick("ورود به حساب","Sign in")}</Link>
          <Link className="ghost" href="/panel" onClick={()=>setOpen(false)}>{pick("پنل کاربری","Customer panel")}</Link>
        </div>
      </aside>
    </div>
  </>;
}
