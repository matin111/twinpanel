import type {Lang} from "./i18n";

export const resellerLocale=(lang:Lang)=>lang==="fa"?"fa-IR":"en-US";

export function resellerNumber(lang:Lang,value:unknown,options:Intl.NumberFormatOptions={}):string{
  const number=Number(value||0);
  return (Number.isFinite(number)?number:0).toLocaleString(resellerLocale(lang),options);
}

export function resellerMoney(lang:Lang,value:unknown):string{
  return `${resellerNumber(lang,value)} ${lang==="fa"?"تومان":"Toman"}`;
}

export function resellerDate(lang:Lang,value:unknown):string{
  if(!value)return "—";
  const date=new Date(String(value));
  if(Number.isNaN(date.getTime()))return String(value);
  return date.toLocaleString(resellerLocale(lang));
}

export function resellerTime(lang:Lang,value:Date):string{
  return value.toLocaleTimeString(resellerLocale(lang));
}

export function resellerGb(lang:Lang,value:unknown):string{
  return `${resellerNumber(lang,value,{maximumFractionDigits:2})} GB`;
}

export function resellerBytes(lang:Lang,value:unknown):string{
  return resellerGb(lang,Number(value||0)/(1024**3));
}

const STATUS_FA:Record<string,string>={
  active:"فعال",
  inactive:"غیرفعال",
  enabled:"فعال",
  disabled:"غیرفعال",
  online:"آنلاین",
  offline:"آفلاین",
  degraded:"ناپایدار",
  pending:"در انتظار",
  pending_payment:"در انتظار پرداخت",
  awaiting_review:"در انتظار بررسی",
  review:"در انتظار بررسی",
  submitted:"ثبت‌شده",
  approved:"تأییدشده",
  auto_verified:"تأیید خودکار",
  paid:"پرداخت‌شده",
  completed:"تکمیل‌شده",
  success:"موفق",
  rejected:"ردشده",
  failed:"ناموفق",
  canceled:"لغوشده",
  suspended:"معلق",
  expired:"منقضی",
  read:"خوانده‌شده",
  unread:"خوانده‌نشده",
};

const STATUS_EN:Record<string,string>={
  active:"Active",
  inactive:"Inactive",
  enabled:"Enabled",
  disabled:"Disabled",
  online:"Online",
  offline:"Offline",
  degraded:"Degraded",
  pending:"Pending",
  pending_payment:"Pending payment",
  awaiting_review:"Awaiting review",
  review:"Awaiting review",
  submitted:"Submitted",
  approved:"Approved",
  auto_verified:"Auto verified",
  paid:"Paid",
  completed:"Completed",
  success:"Success",
  rejected:"Rejected",
  failed:"Failed",
  canceled:"Canceled",
  suspended:"Suspended",
  expired:"Expired",
  read:"Read",
  unread:"Unread",
};

export function resellerStatus(lang:Lang,value:unknown):string{
  const raw=String(value??"").trim();
  if(!raw)return "—";
  const key=raw.toLowerCase();
  return (lang==="fa"?STATUS_FA:STATUS_EN)[key]||raw;
}

const TYPE_FA:Record<string,string>={
  credit:"افزایش موجودی",
  debit:"کاهش موجودی",
  purchase:"خرید",
  renewal:"تمدید",
  topup:"شارژ",
  top_up:"شارژ",
  traffic_purchase:"خرید حجم",
  traffic_recharge:"شارژ حجم",
  manual_adjustment:"اصلاح دستی",
};

const TYPE_EN:Record<string,string>={
  credit:"Credit",
  debit:"Debit",
  purchase:"Purchase",
  renewal:"Renewal",
  topup:"Top-up",
  top_up:"Top-up",
  traffic_purchase:"Traffic purchase",
  traffic_recharge:"Traffic recharge",
  manual_adjustment:"Manual adjustment",
};

export function resellerType(lang:Lang,value:unknown):string{
  const raw=String(value??"").trim();
  if(!raw)return "—";
  const key=raw.toLowerCase();
  return (lang==="fa"?TYPE_FA:TYPE_EN)[key]||raw;
}

export type ResellerNotificationLike={
  title?:string|null;
  message?:string|null;
  source?:string|null;
};

export function resellerNotificationDisplay(lang:Lang,row:ResellerNotificationLike):{title:string;message:string}{
  const rawTitle=String(row.title||"").trim();
  const rawMessage=String(row.message||"").trim();
  if(lang==="fa")return {title:rawTitle||"اعلان",message:rawMessage||"—"};

  const source=String(row.source||"").toLowerCase();
  if(source==="bot_wallet"){
    const match=rawMessage.match(/#(\d+)\s+از\s+(.+?)\s+به مبلغ\s+([\d,٬]+)\s+تومان/);
    return {
      title:"New bot wallet top-up receipt",
      message:match
        ?`Wallet top-up request #${match[1]} from ${match[2]} for ${match[3].replace(/٬/g,",")} Toman is ready for review.`
        :(rawMessage||"A new bot wallet top-up receipt is ready for review."),
    };
  }

  if(source==="bot_order"){
    const renewal=rawTitle.includes("تمدید")||rawMessage.includes("تمدید");
    const match=rawMessage.match(/سفارش\s+#(\d+)\s+از\s+(.+?)\s+به مبلغ\s+([\d,٬]+)\s+تومان/);
    return {
      title:renewal?"New bot renewal receipt":"New bot purchase receipt",
      message:match
        ?`${renewal?"Renewal":"Purchase"} order #${match[1]} from ${match[2]} for ${match[3].replace(/٬/g,",")} Toman is ready for review.`
        :(rawMessage||"A new bot order receipt is ready for review."),
    };
  }

  const titleMap:Record<string,string>={
    "رسید شارژ کیف پول جدید":"New bot wallet top-up receipt",
    "رسید تمدید ربات جدید":"New bot renewal receipt",
    "رسید خرید ربات جدید":"New bot purchase receipt",
    "هشدار انقضای اشتراک":"Subscription expiry warning",
  };
  return {title:titleMap[rawTitle]||rawTitle||"Notification",message:rawMessage||"—"};
}
