"use client";

import {useI18n} from "../lib/i18n";
import {Badge,Card,PageHead,Shell,Stat,Toolbar} from "./ui";

function SwitchRow({fa,en,checked=true}:{fa:string;en:string;checked?:boolean}){
  const {pick}=useI18n();
  return <label className="toggle module-toggle"><span>{pick(fa,en)}</span><input type="checkbox" defaultChecked={checked}/><i/></label>;
}

export function TelegramPage(){
  const {pick}=useI18n();
  const bots=[
    [pick("ربات اصلی","Main bot"),"@TwinPanelBot",pick("فعال","Active"),"ok"],
    [pick("ربات فروش","Sales bot"),"@TwinPanelShopBot",pick("فعال","Active"),"ok"],
    [pick("ربات پشتیبانی","Support bot"),"@TwinPanelSupportBot",pick("فعال","Active"),"ok"],
    [pick("ربات کیف پول","Wallet bot"),"@TwinPanelWalletBot",pick("متوقف","Stopped"),"warn"],
    [pick("ربات نمایندگی","Reseller bot"),"@TwinPanelResellerBot",pick("فعال","Active"),"ok"]
  ] as const;
  return <Shell active="/admin/telegram"><div className="page">
    <PageHead title={pick("مدیریت ربات تلگرام","Telegram Bot Manager")} sub={pick("مدیریت ربات‌های فروش، پشتیبانی، کیف پول و نمایندگی","Manage sales, support, wallet and reseller bots")}/>
    <div className="stats"><Stat label={pick("ربات فعال","Active bots")} value="۴ / ۵" icon="✈"/><Stat label={pick("کاربران متصل","Linked users")} value="۱,۸۴۲" icon="♙"/><Stat label={pick("پیام امروز","Messages today")} value="۶,۳۲۰" icon="◎"/><Stat label={pick("خطاهای امروز","Errors today")} value="۳" icon="!"/></div>
    <div className="module-grid two">
      <Card><div className="card-head"><div><b>{pick("وضعیت ربات‌ها","Bot status")}</b><small>{pick("کنترل سرویس و اتصال API","Service and API connectivity")}</small></div><Badge>{pick("سرویس سالم","Healthy")}</Badge></div>
        {bots.map(([name,user,status,tone])=><div className="row" key={user}><span className="module-icon">✈</span><div className="grow"><b>{name}</b><small>{user}</small></div><Badge tone={tone as "ok"|"warn"}>{status}</Badge><button className="mini-btn">{pick("مدیریت","Manage")}</button></div>)}
      </Card>
      <Card><div className="card-head"><div><b>{pick("تنظیمات ربات اصلی","Main bot settings")}</b><small>{pick("توکن، Webhook و رفتار ربات","Token, webhook and runtime behavior")}</small></div></div>
        <label className="field"><span>{pick("توکن ربات","Bot token")}</span><div className="secret-field"><input value="••••••••••:••••••••••••••••••" readOnly/><button>{pick("تغییر","Change")}</button></div></label>
        <label className="field"><span>Webhook URL</span><input value="https://api.example.com/telegram/webhook" readOnly/></label>
        <SwitchRow fa="خرید از داخل ربات" en="Purchases inside bot"/>
        <SwitchRow fa="اعلان تمدید اشتراک" en="Subscription renewal alerts"/>
        <SwitchRow fa="ارسال خودکار اطلاعات اتصال" en="Automatic connection delivery"/>
        <div className="action-row"><button className="primary">{pick("تست اتصال","Test connection")}</button><button className="ghost">{pick("راه‌اندازی مجدد","Restart")}</button><button className="ghost">{pick("مشاهده لاگ","View logs")}</button></div>
      </Card>
    </div>
  </div></Shell>;
}

export function BackupsPage(){
  const {pick}=useI18n();
  const rows=[
    ["backup-2026-10-07-0900.tar.gz","2.4 GB","07 Oct 09:00",pick("سالم","Valid")],
    ["backup-2026-10-06-0900.tar.gz","2.3 GB","06 Oct 09:00",pick("سالم","Valid")],
    ["backup-2026-10-05-0900.tar.gz","2.3 GB","05 Oct 09:00",pick("سالم","Valid")]
  ];
  return <Shell active="/admin/backups"><div className="page">
    <PageHead title={pick("بکاپ و بازیابی","Backup & Restore")} sub={pick("پشتیبان‌گیری امن از دیتابیس و تنظیمات و بازیابی کنترل‌شده","Secure database/config backups and controlled restore")} action={pick("ایجاد بکاپ","Create backup")}/>
    <div className="stats"><Stat label={pick("آخرین بکاپ","Last backup")} value="09:00" icon="⟲"/><Stat label={pick("حجم آخرین بکاپ","Latest size")} value="2.4 GB"/><Stat label={pick("بکاپ نگهداری‌شده","Retained backups")} value="۱۴"/><Stat label={pick("وضعیت زمان‌بندی","Schedule")} value={pick("روزانه","Daily")}/></div>
    <div className="module-grid two">
      <Card><div className="card-head"><div><b>{pick("بکاپ‌های اخیر","Recent backups")}</b><small>{pick("نسخه‌های قابل بازیابی","Restorable snapshots")}</small></div><Badge>{pick("رمزگذاری فعال","Encrypted")}</Badge></div>
        <div className="table"><table><thead><tr><th>{pick("فایل","File")}</th><th>{pick("حجم","Size")}</th><th>{pick("تاریخ","Date")}</th><th>{pick("وضعیت","Status")}</th><th></th></tr></thead><tbody>{rows.map(r=><tr key={r[0]}><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td><Badge>{r[3]}</Badge></td><td><button className="mini-btn">{pick("دانلود","Download")}</button></td></tr>)}</tbody></table></div>
      </Card>
      <Card><div className="card-head"><div><b>{pick("بازیابی سیستم","Restore system")}</b><small>{pick("بازیابی فقط پس از بررسی سلامت فایل انجام می‌شود","Restore runs only after archive validation")}</small></div><Badge tone="warn">{pick("عملیات حساس","Sensitive")}</Badge></div>
        <div className="upload-zone"><b>{pick("فایل بکاپ را انتخاب کنید","Choose backup archive")}</b><small>.tar.gz / .sql</small><button className="ghost">{pick("انتخاب فایل","Select file")}</button></div>
        <SwitchRow fa="ارسال بکاپ به تلگرام" en="Send backups to Telegram"/>
        <SwitchRow fa="بکاپ خودکار روزانه" en="Automatic daily backup"/>
        <label className="field"><span>{pick("کلید بازیابی","Recovery key")}</span><input value="TP-RCV-••••-••••-••••" readOnly/></label>
        <button className="primary">{pick("بررسی فایل و آماده‌سازی بازیابی","Validate and prepare restore")}</button>
      </Card>
    </div>
  </div></Shell>;
}

export function StoreSettingsPage(){
  const {pick}=useI18n();
  return <Shell active="/admin/store-settings"><div className="page">
    <PageHead title={pick("تنظیمات فروشگاه","Store Settings")} sub={pick("کنترل محتوای فروشگاه، پلن‌های قابل فروش، پرداخت و پشتیبانی","Control storefront content, sellable plans, payments and support")}/>
    <div className="module-grid two">
      <Card><h3>{pick("تنظیمات عمومی فروشگاه","General storefront settings")}</h3><p className="muted">{pick("اطلاعات اصلی صفحه عمومی فروش","Core public storefront information")}</p>
        <label className="field"><span>{pick("عنوان اصلی","Hero title")}</span><input defaultValue={pick("اینترنت آزاد، بدون محدودیت","Fast, secure internet without limits")}/></label>
        <label className="field"><span>{pick("متن معرفی","Hero description")}</span><textarea defaultValue={pick("سرورهای پایدار، پروتکل‌های مدرن و پشتیبانی سریع","Reliable servers, modern protocols and fast support")}/></label>
        <label className="field"><span>{pick("آیدی پشتیبانی تلگرام","Telegram support")}</span><input defaultValue="@matinvpn" dir="ltr"/></label>
        <SwitchRow fa="فروشگاه فعال باشد" en="Enable storefront"/>
        <SwitchRow fa="نمایش قیمت در صفحه اصلی" en="Show prices on homepage"/>
      </Card>
      <Card><h3>{pick("فروش و پرداخت","Sales & payments")}</h3><p className="muted">{pick("روش‌های خرید و نمایش پلن‌ها","Checkout methods and plan visibility")}</p>
        <SwitchRow fa="پرداخت کارت بانکی" en="Card payments"/>
        <SwitchRow fa="پرداخت USDT" en="USDT payments"/>
        <SwitchRow fa="پرداخت با کیف پول" en="Wallet payments"/>
        <SwitchRow fa="کد تخفیف در Checkout" en="Discount codes at checkout"/>
        <label className="field"><span>{pick("پلن برجسته","Featured plan")}</span><select defaultValue="pro"><option value="eco">{pick("اقتصادی","Economy")}</option><option value="pro">{pick("حرفه‌ای","Professional")}</option><option value="vip">VIP</option></select></label>
        <button className="primary">{pick("ذخیره تنظیمات فروشگاه","Save store settings")}</button>
      </Card>
    </div>
  </div></Shell>;
}

export function WalletPage(){
  const {pick}=useI18n();
  const tx=[
    ["#W-8214",pick("شارژ کیف پول","Wallet top-up"),"+240,000",pick("موفق","Success")],
    ["#W-8213",pick("خرید اشتراک","Subscription purchase"),"-90,000",pick("موفق","Success")],
    ["#W-8212",pick("اصلاح دستی مدیر","Admin adjustment"),"+50,000",pick("موفق","Success")]
  ];
  return <Shell active="/admin/wallet"><div className="page">
    <PageHead title={pick("کیف پول","Wallet")} sub={pick("مدیریت موجودی، شارژها و تراکنش‌های کاربران و نمایندگان","Manage balances, top-ups and customer/reseller transactions")} action={pick("اصلاح موجودی","Adjust balance")}/>
    <div className="stats"><Stat label={pick("موجودی کل کاربران","Customer balances")} value="18.4M"/><Stat label={pick("موجودی نمایندگان","Reseller balances")} value="7.2M"/><Stat label={pick("شارژ امروز","Top-ups today")} value="3.8M"/><Stat label={pick("در انتظار تأیید","Pending approval")} value="۳"/></div>
    <Card><Toolbar/><div className="table"><table><thead><tr><th>{pick("شناسه","ID")}</th><th>{pick("نوع","Type")}</th><th>{pick("مبلغ","Amount")}</th><th>{pick("وضعیت","Status")}</th><th>{pick("عملیات","Actions")}</th></tr></thead><tbody>{tx.map(r=><tr key={r[0]}><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td><Badge>{r[3]}</Badge></td><td><button className="mini-btn">{pick("جزئیات","Details")}</button></td></tr>)}</tbody></table></div></Card>
  </div></Shell>;
}

export function DiscountsPage(){
  const {pick}=useI18n();
  const codes=[
    ["WELCOME20","20%","124 / 500","2026-12-31",pick("فعال","Active")],
    ["VIP50","50,000", "41 / 100","2026-11-15",pick("فعال","Active")],
    ["SUMMER","15%","300 / 300","2026-09-30",pick("پایان‌یافته","Expired")]
  ];
  return <Shell active="/admin/discounts"><div className="page">
    <PageHead title={pick("کدهای تخفیف","Discount Codes")} sub={pick("ساخت و مدیریت تخفیف برای فروشگاه و نمایندگان","Create and manage storefront and reseller discounts")} action={pick("کد جدید","New code")}/>
    <div className="stats"><Stat label={pick("کد فعال","Active codes")} value="۱۲"/><Stat label={pick("استفاده این ماه","Uses this month")} value="۴۸۲"/><Stat label={pick("تخفیف اعمال‌شده","Discount granted")} value="6.7M"/><Stat label={pick("نرخ تبدیل","Conversion") } value="18.2%"/></div>
    <Card><div className="table"><table><thead><tr><th>{pick("کد","Code")}</th><th>{pick("تخفیف","Discount")}</th><th>{pick("مصرف","Usage")}</th><th>{pick("انقضا","Expiry")}</th><th>{pick("وضعیت","Status")}</th><th></th></tr></thead><tbody>{codes.map((r,i)=><tr key={r[0]}><td><b>{r[0]}</b></td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td><td><Badge tone={i===2?"warn":"ok"}>{r[4]}</Badge></td><td><button className="mini-btn">{pick("ویرایش","Edit")}</button></td></tr>)}</tbody></table></div></Card>
  </div></Shell>;
}

export function ResellersAdminPage(){
  const {pick}=useI18n();
  const rows=[
    ["Matin Reseller","@matin_reseller","248","12.4M","2.49M",pick("فعال","Active")],
    ["Network Plus","@netplus","91","6.8M","1.12M",pick("فعال","Active")],
    ["Fast VPN","@fastvpn","44","2.1M","480K",pick("تعلیق","Suspended")]
  ];
  return <Shell active="/admin/resellers"><div className="page">
    <PageHead title={pick("نمایندگی‌ها","Resellers")} sub={pick("مدیریت نمایندگان، اعتبار، مشتریان و قیمت اختصاصی","Manage resellers, balances, customers and custom pricing")} action={pick("نماینده جدید","New reseller")}/>
    <div className="stats"><Stat label={pick("نماینده فعال","Active resellers")} value="۲۱"/><Stat label={pick("مشتریان نمایندگان","Reseller customers")} value="۱,۴۸۲"/><Stat label={pick("فروش این ماه","Monthly sales")} value="38.7M"/><Stat label={pick("کمیسیون","Commission") } value="7.4M"/></div>
    <Card><Toolbar/><div className="table"><table><thead><tr><th>{pick("نماینده","Reseller")}</th><th>Telegram</th><th>{pick("مشتری","Customers")}</th><th>{pick("فروش","Sales")}</th><th>{pick("اعتبار","Balance")}</th><th>{pick("وضعیت","Status")}</th><th></th></tr></thead><tbody>{rows.map((r,i)=><tr key={r[0]}><td><b>{r[0]}</b></td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td><td><Badge tone={i===2?"warn":"ok"}>{r[5]}</Badge></td><td><button className="mini-btn">{pick("مدیریت","Manage")}</button></td></tr>)}</tbody></table></div></Card>
  </div></Shell>;
}
