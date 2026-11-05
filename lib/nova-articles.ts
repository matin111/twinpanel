export type NovaArticle={slug:string;title:string;description:string;updated:string;sections:{title:string;paragraphs:string[]}[]};
export const NOVA_ARTICLES:NovaArticle[]=[
{slug:"vpn-protocol-guide",title:"راهنمای انتخاب پروتکل VPN: از OpenVPN تا WireGuard و V2Ray",description:"چه معیارهایی برای انتخاب پروتکل اتصال مهم است و چرا هیچ پروتکلی برای همه شبکه‌ها بهترین نیست؟",updated:"2026-11-05",sections:[
{title:"چرا انتخاب پروتکل اهمیت دارد؟",paragraphs:["هر پروتکل برای شرایط متفاوتی طراحی شده است. کیفیت اینترنت، محدودیت‌های شبکه، سازگاری برنامه و سرور، نوع دستگاه و نیاز شما می‌تواند نتیجه اتصال را تغییر دهد.","مقایسه را فقط بر اساس ادعای سرعت انجام ندهید. ابتدا بررسی کنید پروتکل واقعاً در پلن شما فعال است و برای سیستم‌عاملتان کلاینت مطمئن وجود دارد."]},
{title:"OpenVPN و Cisco / OpenConnect",paragraphs:["OpenVPN یک گزینه جاافتاده است که با کلاینت‌های متعدد روی دستگاه‌های مختلف کار می‌کند. تنظیمات و مسیر ارتباطی TCP یا UDP روی پایداری آن اثر می‌گذارد.","Cisco / OpenConnect معمولاً با آدرس سرور و مشخصات ورود راه‌اندازی می‌شود. کیفیت آن مانند هر پروتکل دیگر به سرور و مسیر اینترنت وابسته است."]},
{title:"WireGuard و V2Ray / Xray",paragraphs:["WireGuard طراحی ساده و سبکی دارد و معمولاً با فایل تنظیمات یا کد QR استفاده می‌شود؛ بااین‌حال همه شبکه‌ها مسیر UDP یکسانی ندارند.","خانواده V2Ray / Xray روش‌ها و انتقال‌های گوناگونی را پشتیبانی می‌کند. لازم است لینک ارائه‌شده با برنامه مورد استفاده سازگار باشد و تنظیمات از منبع معتبر دریافت شود."]},
{title:"روش‌های مدرن دیگر",paragraphs:["AnyTLS، Hysteria2، Naive، ShadowTLS، Snell، Mieru و سایر گزینه‌های فهرست پنل، نیازمندی‌های فنی و کلاینت‌های خاص خود را دارند. ارائه شدن نام آن‌ها به معنی فعال بودن تمامشان در هر پلن نیست.","برای انتخاب، از صفحه خدمات پروتکل‌های موجود را بخوانید و در حساب کاربری فقط لینک‌ها و فایل‌های مربوط به اشتراک خود را بردارید."]},
{title:"چک‌لیست انتخاب",paragraphs:["سیستم‌عامل و کلاینت را مشخص کنید؛ نوع اینترنت و موقعیت سرور را در نظر بگیرید؛ مشخصات پلن را بررسی کنید؛ در صورت اختلال از سرور یا پروتکل مجاز جایگزین استفاده کنید. هیچ اتصال دائمی و بدون قطعی قابل تضمین نیست."]}
]},
{slug:"static-ip-vs-vpn",title:"تفاوت VPN معمولی و IP ثابت چیست؟",description:"آشنایی با کاربرد IP ثابت، محدودیت‌ها و نکات پیش از خرید سرویس.",updated:"2026-11-05",sections:[
{title:"IP ثابت به چه معناست؟",paragraphs:["وقتی برای یک سرویس آدرس خروجی ثابت تعیین می‌شود، در شرایط تعریف‌شده همان آدرس برای اتصال شما استفاده خواهد شد. این ویژگی ممکن است برای سامانه‌هایی مفید باشد که دسترسی را به فهرستی از آدرس‌های مجاز محدود می‌کنند.","VPN معمولی ممکن است هنگام تغییر سرور یا بازسازی اتصال از آدرس دیگری استفاده کند؛ اما نحوه تخصیص آدرس دقیقاً به قرارداد سرویس وابسته است."]},
{title:"کاربردهای متداول",paragraphs:["برخی محیط‌های دورکاری، داشبوردهای سازمانی، محیط‌های آزمایشی و سرویس‌های دارای allowlist آی‌پی می‌توانند به آدرس خروجی مشخص نیاز داشته باشند.","همه سرویس‌ها با IP ثابت سازگار نیستند و آدرس ثابت، جایگزین تأیید هویت یا مجوز استفاده از سرویس مقصد نمی‌شود."]},
{title:"پیش از خرید چه چیزهایی را بررسی کنیم؟",paragraphs:["کشور و موقعیت سرور، امکان تغییر آدرس، تعداد دستگاه، مدت اعتبار، حجم، شرایط تمدید و نوع پروتکل‌های پلن را بررسی کنید.","ثابت بودن آدرس به معنی تضمین مادام‌العمر همان IP، رفع محدودیت همه سایت‌ها یا تضمین رفتار حساب کاربری نیست."]}
]},
{slug:"how-to-connect-vpn",title:"آموزش دریافت لینک VPN و اتصال روی موبایل و کامپیوتر",description:"راهنمای دریافت اطلاعات اشتراک، نصب کلاینت مناسب و رفع خطاهای رایج.",updated:"2026-11-05",sections:[
{title:"مرحله اول: اطلاعات اشتراک را دریافت کنید",paragraphs:["وارد حساب کاربری شوید. پس از ثبت و تأیید سفارش، جزئیات اشتراک و لینک‌های اتصال مربوط به سرورهای آماده را از بخش دریافت لینک اکانت بردارید.","در بعضی روش‌ها لینک اشتراک، فایل پیکربندی یا QR قابل استفاده است و در روش‌های دیگر آدرس سرور، نام کاربری و رمز لازم خواهد بود.","نکته مهم: داخل ساب‌لینک اشتراک، برای هر پروتکل برنامه مخصوص یا سازگار همان پروتکل معرفی شده است. ساب‌لینک را در مرورگر باز کنید، پروتکل دلخواه را انتخاب کنید و برنامه مناسب سیستم‌عاملتان را از بخش همان پروتکل دریافت کنید."]},
{title:"مرحله دوم: برنامه سازگار را نصب کنید",paragraphs:["برای OpenVPN به کلاینت سازگار با فایل ovpn نیاز دارید؛ برای WireGuard از کلاینت پشتیبانی‌کننده WireGuard استفاده می‌شود؛ OpenConnect و V2Ray / Xray نیز کلاینت‌های اختصاصی دارند.","اول بخش برنامه‌های همان پروتکل را در ساب‌لینک باز کنید؛ برای هر پروتکل، برنامه سازگار به تفکیک دستگاه معرفی شده است. برنامه معرفی‌شده را از لینک معتبر دریافت کنید و از نصب نسخه‌های ناشناس یا وارد کردن لینک حساس در سایت‌های نامعتبر خودداری کنید."]},
{title:"مرحله سوم: تنظیمات را اضافه و اتصال را بررسی کنید",paragraphs:["لینک یا فایل را به کلاینت وارد کنید، سرور مجاز را انتخاب کرده و اتصال را روشن کنید. برخی برنامه‌ها به مجوز ساخت اتصال VPN نیاز دارند.","اگر اتصال برقرار نشد، ابتدا تاریخ انقضا و حجم اشتراک، صحیح بودن اطلاعات و به‌روزبودن برنامه را بررسی کنید. سپس شبکه یا سرور جایگزین مربوط به پلن را آزمایش کنید."]},
{title:"هنگام خطا چه کنیم؟",paragraphs:["خطاهای احراز هویت معمولاً به اشتباه بودن مشخصات، محدودیت حساب یا وضعیت سرور مربوط می‌شوند. در خطاهای شبکه ممکن است تغییر سرور یا پروتکل کمک کند.","برای راهنمایی دقیق‌تر، تصویر خطا را بدون نمایش رمز یا لینک خصوصی برای پشتیبانی ارسال کنید."]}
]}
];
export function novaArticle(slug:string){return NOVA_ARTICLES.find(article=>article.slug===slug)||null;}

/** Articles saved by the Nova blog editor in storefront template settings.
 * The editor stores text, not HTML; everything is rendered as React text. */
export type NovaBlogEntry={
 slug:string;
 title:string;
 description:string;
 body:string;
 updated:string;
 published:boolean;
};
export function cleanNovaBlogEntries(value:unknown):NovaBlogEntry[]{
 if(!Array.isArray(value))return [];
 const seen=new Set<string>();
 const output:NovaBlogEntry[]=[];
 for(const raw of value.slice(0,40)){
  if(!raw||typeof raw!=="object"||Array.isArray(raw))continue;
  const entry=raw as Record<string,unknown>;
  const slug=String(entry.slug||"").trim().toLowerCase();
  const title=String(entry.title||"").trim();
  const description=String(entry.description||"").trim();
  const body=String(entry.body||"").trim();
  if(!/^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$/.test(slug)||seen.has(slug)||!title||!body)continue;
  seen.add(slug);
  output.push({
    slug,title:title.slice(0,180),description:description.slice(0,400),
    body:body.slice(0,5000),
    updated:/^\d{4}-\d{2}-\d{2}$/.test(String(entry.updated||""))?String(entry.updated):"2026-11-05",
    published:entry.published===true,
  });
 }
 return output;
}
export function novaArticlesWithOverrides(value:unknown):NovaArticle[]{
 const overrides=cleanNovaBlogEntries(value);
 const hidden=new Set(overrides.filter(x=>!x.published).map(x=>x.slug));
 const original=NOVA_ARTICLES.filter(x=>!hidden.has(x.slug));
 const merged=new Map<string,NovaArticle>(original.map(x=>[x.slug,x]));
 for(const entry of overrides.filter(x=>x.published)){
  const paragraphs=entry.body.split(/\n\s*\n/).map(x=>x.trim()).filter(Boolean);
  merged.set(entry.slug,{
   slug:entry.slug,title:entry.title,description:entry.description,updated:entry.updated,
   sections:[{title:"متن مقاله",paragraphs:paragraphs.length?paragraphs:[entry.body]}],
  });
 }
 return [...merged.values()];
}
export function novaEditableEntries(value:unknown):NovaBlogEntry[]{
 const overrides=cleanNovaBlogEntries(value);
 const existing=new Set(overrides.map(x=>x.slug));
 const baseline=NOVA_ARTICLES.filter(a=>!existing.has(a.slug)).map(a=>({
  slug:a.slug,title:a.title,description:a.description,
  body:a.sections.map(section=>section.title+"\n"+section.paragraphs.join("\n\n")).join("\n\n"),
  updated:a.updated,published:true,
 }));
 return [...overrides,...baseline];
}
