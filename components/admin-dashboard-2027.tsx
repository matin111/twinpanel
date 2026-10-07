"use client";

import {Badge,Card,PageHead,Shell,Stat} from "./ui";
import {useI18n} from "../lib/i18n";

const cityPairs=[["فرانکفورت","Frankfurt"],["آمستردام","Amsterdam"],["استانبول","Istanbul"],["دبی","Dubai"]] as const;
const flags=["🇩🇪","🇳🇱","🇹🇷","🇦🇪"];

export function AdminDashboard2027(){
  const {pick}=useI18n();
  const activityPairs=[
    ["پرداخت موفق ثبت شد","Successful payment recorded"],
    ["اشتراک جدید ساخته شد","New subscription created"],
    ["نود فرانکفورت آنلاین شد","Frankfurt node came online"],
    ["کاربر جدید ثبت‌نام کرد","New user registered"]
  ] as const;

  return <Shell active="/admin"><div className="page">
    <PageHead
      title={pick("داشبورد مدیریت","Admin Dashboard")}
      sub={pick("نمای کلی زنده از کاربران، اشتراک‌ها، درآمد و زیرساخت","Live overview of users, subscriptions, revenue and infrastructure")}
    />

    <div className="stats dashboard-stats">
      <Stat label={pick("کاربران فعال","Active users")} value={pick("۲,۸۴۳","2,843")} delta={pick("+۱۲٪ این ماه","+12% this month")} icon="♙"/>
      <Stat label={pick("اشتراک فعال","Active subscriptions")} value={pick("۱,۹۲۴","1,924")} delta="+9%" icon="▱"/>
      <Stat label={pick("اشتراک آنلاین","Online subscriptions")} value={pick("۳۸۷","387")} delta={pick("● زنده · ۲۰٪ اشتراک‌های فعال","● LIVE · 20% of active subs")} icon="◉"/>
      <Stat label={pick("درآمد این ماه","Revenue this month")} value="128.6M" delta="+23%" icon="◫"/>
      <Stat label={pick("نود آنلاین","Online nodes")} value="28 / 32" delta={pick("۸۸٪ سلامت","88% healthy")} icon="▦"/>
    </div>

    <div className="dash-grid">
      <Card>
        <div className="card-head"><div><b>{pick("روند درآمد","Revenue trend")}</b><small>{pick("۳۰ روز گذشته","Last 30 days")}</small></div><Badge tone="violet">{pick("۳۰ روز","30 days")}</Badge></div>
        <div className="chart"><svg viewBox="0 0 600 200"><defs><linearGradient id="g2027" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#8b5cf6" stopOpacity=".38"/><stop offset="1" stopColor="#8b5cf6" stopOpacity="0"/></linearGradient></defs><path d="M0 180 C70 150 90 165 135 128 S220 105 260 120 S340 62 390 80 S460 42 510 58 S565 20 600 28 L600 200 L0 200Z" fill="url(#g2027)"/><path d="M0 180 C70 150 90 165 135 128 S220 105 260 120 S340 62 390 80 S460 42 510 58 S565 20 600 28" fill="none" stroke="#9b7cff" strokeWidth="4"/></svg></div>
      </Card>

      <Card>
        <div className="card-head"><div><b>{pick("وضعیت اشتراک‌ها","Subscription status")}</b><small>{pick("فعال، آنلاین و منقضی","Active, online and expired")}</small></div></div>
        <div className="donut"><div><b>{pick("۱,۹۲۴","1,924")}</b><small>{pick("فعال","Active")}</small></div></div>
        <div className="legend"><span><i className="c1"/>{pick("فعال ۷۲٪","Active 72%")}</span><span><i className="c2"/>{pick("منقضی ۱۸٪","Expired 18%")}</span></div>
        <div className="online-summary"><span className="dot"/><b>{pick("۳۸۷ اشتراک اکنون آنلاین هستند","387 subscriptions are online now")}</b><small>{pick("این عدد در نسخه متصل از Sessionهای واقعی خوانده می‌شود","This will be sourced from live sessions after backend wiring")}</small></div>
      </Card>
    </div>

    <div className="triple">
      <Card><div className="card-head"><b>{pick("نودها","Nodes")}</b><a>{pick("مشاهده همه","View all")}</a></div>{cityPairs.map((x,i)=><div className="row" key={x[1]}><span className="flag">{flags[i]}</span><div className="grow"><b>{pick(x[0],x[1])}</b><small>{pick("پایدار و آماده سرویس","Stable and ready")}</small></div><span>{[85,92,96,89][i]}ms</span><Badge>{pick("آنلاین","Online")}</Badge></div>)}</Card>
      <Card><div className="card-head"><b>{pick("تانل‌ها","Tunnels")}</b><a>{pick("مدیریت","Manage")}</a></div>{["Backhaul","MTunnel","SSH Tunnel","SSH Relay"].map((x,i)=><div className="row" key={x}><span className="dot"/><div className="grow"><b>{x}</b><small>Transport #{i+1}</small></div><Badge tone={i===2?"warn":"ok"}>{i===2?"Standby":"Online"}</Badge></div>)}</Card>
      <Card><div className="card-head"><b>{pick("فعالیت اخیر","Recent activity")}</b><a>{pick("همه","All")}</a></div>{activityPairs.map((x,i)=><div className="activity" key={x[1]}><span>{i+1}</span><div><b>{pick(x[0],x[1])}</b><small>{pick(`${i*12+2} دقیقه پیش`,`${i*12+2} min ago`)}</small></div></div>)}</Card>
    </div>
  </div></Shell>;
}
