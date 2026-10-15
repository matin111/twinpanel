import type {Lang} from "./i18n";

export type NotificationLike=Record<string,unknown>;

const value=(row:NotificationLike,...keys:string[])=>{
  for(const key of keys){
    const current=row[key];
    if(current!==undefined&&current!==null)return String(current);
  }
  return "";
};

const englishTitleMap:Record<string,string>={
  "تغییر وضعیت نود":"Node status changed",
  "تغییر وضعیت تونل":"Tunnel status changed",
  "پرداخت تأیید شد":"Payment approved",
  "پرداخت تایید شد":"Payment approved",
  "پرداخت رد شد":"Payment rejected",
  "افزایش موجودی کیف پول":"Wallet balance increased",
  "اصلاح موجودی کیف پول":"Wallet balance adjusted",
  "درخواست شارژ رد شد":"Wallet top-up rejected",
};

function englishDigits(input:string){
  return String(input||"")
    .replace(/[۰-۹]/g,d=>String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)))
    .replace(/[٠-٩]/g,d=>String("٠١٢٣٤٥٦٧٨٩".indexOf(d)))
    .replace(/٬/g,",")
    .replace(/٫/g,".");
}

function translateMessageToEnglish(input:string){
  const translated=String(input||"")
    .replace(/^🌐 تغییر وضعیت شبکه/gm,"🌐 Network status changed")
    .replace(/^🔀 تغییر وضعیت تونل/gm,"🔀 Tunnel status changed")
    .replace(/پرداخت سفارش (#?\d+) تأیید شد و اشتراک شما آماده استفاده است\.?/g,"Payment for order $1 was approved and your subscription is ready to use.")
    .replace(/پرداخت سفارش (#?\d+) تایید شد و اشتراک شما آماده استفاده است\.?/g,"Payment for order $1 was approved and your subscription is ready to use.")
    .replace(/پرداخت سفارش (#?\d+) تأیید شد و سرویس شما در حال آماده‌سازی است\.?/g,"Payment for order $1 was approved and your service is being prepared.")
    .replace(/پرداخت سفارش (#?\d+) تایید شد و سرویس شما در حال آماده‌سازی است\.?/g,"Payment for order $1 was approved and your service is being prepared.")
    .replace(/درخواست شارژ کیف پول #(\d+) رد شد\.?/g,"Wallet top-up #$1 was rejected.")
    .replace(/موجودی کیف پول شما توسط مدیر (.+?) افزایش یافت\./g,"Your wallet balance was increased by $1 by an administrator.")
    .replace(/موجودی کیف پول شما توسط مدیر (.+?) کاهش یافت\./g,"Your wallet balance was decreased by $1 by an administrator.")
    .replace(/توضیح:/g,"Note:")
    .replace(/دلیل:/g,"Reason:")
    .replace(/تومان/g,"Toman");

  return englishDigits(translated);
}

export function localizeAdminPanelNotification(row:NotificationLike,lang:Lang){
  const rawTitle=value(row,"title","event_key");
  const rawMessage=value(row,"message","body");
  if(lang==="fa")return {title:rawTitle,message:rawMessage};

  const source=value(row,"source").toLowerCase();
  const title=source==="node"
    ?"Node status changed"
    :source==="tunnel"
      ?"Tunnel status changed"
      :(englishTitleMap[rawTitle]||rawTitle);

  return {title,message:translateMessageToEnglish(rawMessage)};
}

export function localizeUserNotification(row:NotificationLike,lang:Lang){
  const rawTitle=value(row,"title");
  const rawMessage=value(row,"message","body");
  if(lang==="fa")return {title:rawTitle,message:rawMessage};

  const batch=value(row,"batch_id").toLowerCase();
  let title=englishTitleMap[rawTitle]||rawTitle;

  if(batch.startsWith("payment-approved-"))title="Payment approved";
  else if(batch.startsWith("wallet-admin-adjust-"))title=rawTitle==="افزایش موجودی کیف پول"?"Wallet balance increased":"Wallet balance adjusted";
  else if(batch.startsWith("wallet-topup-rejected-"))title="Wallet top-up rejected";

  return {title,message:translateMessageToEnglish(rawMessage)};
}

export function notificationDate(valueInput:unknown,lang:Lang){
  if(!valueInput)return "—";
  const date=new Date(String(valueInput));
  if(Number.isNaN(date.getTime()))return String(valueInput);
  return date.toLocaleString(lang==="fa"?"fa-IR":"en-GB");
}
