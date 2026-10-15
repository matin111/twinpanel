"use client";

import {FormEvent,useEffect,useMemo,useRef,useState} from "react";
import {API_BASE} from "../lib/api";
import {opsApi} from "../lib/admin-ops-api";
import {useI18n} from "../lib/i18n";
import {Badge,Shell,Stat} from "./ui";

type TicketUser={email?:string|null;phone?:string|null;full_name?:string|null};
type TicketGuest={name?:string|null;contact?:string|null};
type Message={id:number;ticket_id:number;sender_role:string;source?:string|null;message?:string|null;attachment_ref?:string|null;attachment_type?:string|null;created_at:string;_pending?:boolean};
type Ticket={id:number;user_id?:number|null;user?:TicketUser|null;guest?:TicketGuest|null;category?:string|null;category_title?:string|null;subject?:string|null;status:string;source?:string|null;created_at?:string|null;updated_at?:string|null;last_message_at?:string|null;messages?:Message[]};
type Source="all"|"telegram"|"live"|"panel";
type Status="all"|"open"|"answered"|"closed";
type Pulse={latest_support_message_id?:number};

type UploadResult={attachment_type:string;attachment_ref:string};

const ADMIN_PULSE_EVENT="twinpanel:admin-pulse";
const LIST_CACHE_KEY="twinpanel.admin.support.list.v4";
const DETAIL_CACHE_PREFIX="twinpanel.admin.support.detail.v4.";
const STICKERS=["👍","❤️","🙏","😊","😂","🎉","✅","🔥","💜","👋","⭐","🤝","😍","👏","💯","🚀"];
const ALLOWED_IMAGES=new Set(["image/jpeg","image/png","image/webp","image/gif"]);
const MAX_IMAGE_BYTES=5*1024*1024;

function rowsFrom(value:unknown):Ticket[]{
  if(Array.isArray(value))return value as Ticket[];
  if(value&&typeof value==="object"){
    const root=value as Record<string,unknown>;
    for(const key of ["tickets","items","results"])if(Array.isArray(root[key]))return root[key] as Ticket[];
  }
  return [];
}
function detailFrom(value:unknown):Ticket{
  if(!value||typeof value!=="object")return {id:0,status:"open",messages:[]};
  const root=value as Record<string,unknown>;
  const ticket=(root.ticket&&typeof root.ticket==="object"?root.ticket:root) as Ticket;
  return {...ticket,messages:Array.isArray(root.messages)?root.messages as Message[]:ticket.messages||[]};
}
function sourceOf(ticket:Ticket):Exclude<Source,"all">{
  const source=String(ticket.source||"").toLowerCase();
  const subject=String(ticket.subject||"").toLowerCase();
  const email=String(ticket.user?.email||"").trim();
  if(source==="telegram"||subject.includes("telegram")||subject.includes("تلگرام")||/^\d{6,16}$/.test(email))return "telegram";
  if(source==="store_guest"||source==="live_chat"||ticket.user_id==null||subject.includes("live chat")||subject.includes("گفتگوی آنلاین")||subject.includes("گفتگوی فروشگاه"))return "live";
  return "panel";
}
function sortRows(rows:Ticket[]){return [...rows].sort((a,b)=>new Date(b.last_message_at||b.updated_at||b.created_at||0).getTime()-new Date(a.last_message_at||a.updated_at||a.created_at||0).getTime());}
function attachmentUrl(value?:string|null){const ref=String(value||"").trim();if(!ref)return "";if(/^https?:\/\//.test(ref))return ref;return `${API_BASE}${ref.startsWith("/")?ref:`/v1/support/files/${encodeURIComponent(ref)}`}`;}
function readListCache():Ticket[]{try{return rowsFrom(JSON.parse(sessionStorage.getItem(LIST_CACHE_KEY)||"[]"));}catch{return [];}}
function saveListCache(rows:Ticket[]){try{sessionStorage.setItem(LIST_CACHE_KEY,JSON.stringify(rows));}catch{}}
function readDetailCache(id:number):Ticket|null{try{const value=JSON.parse(sessionStorage.getItem(`${DETAIL_CACHE_PREFIX}${id}`)||"null");return value&&typeof value==="object"?detailFrom(value):null;}catch{return null;}}
function saveDetailCache(ticket:Ticket){if(!ticket.id)return;try{sessionStorage.setItem(`${DETAIL_CACHE_PREFIX}${ticket.id}`,JSON.stringify(ticket));}catch{}}
function friendlyError(reason:unknown,fa:string,en:string,lang:"fa"|"en"){
  const error=reason instanceof Error?reason:null;
  const raw=String(error?.message||reason||"");
  if(error?.name==="TimeoutError"||error?.name==="AbortError"||/signal timed out|timeout|aborted/i.test(raw))return lang==="fa"?fa:en;
  return raw||(lang==="fa"?fa:en);
}

export function SupportCenterRuntimeV4(){
  const {pick,lang}=useI18n();
  const locale=lang==="fa"?"fa-IR":"en-GB";
  const [tickets,setTickets]=useState<Ticket[]>([]);
  const ticketsRef=useRef<Ticket[]>([]);
  const [selected,setSelected]=useState<number|null>(null);
  const selectedRef=useRef<number|null>(null);
  const [detail,setDetail]=useState<Ticket|null>(null);
  const [query,setQuery]=useState("");
  const [sourceFilter,setSourceFilter]=useState<Source>("all");
  const [statusFilter,setStatusFilter]=useState<Status>("all");
  const [reply,setReply]=useState("");
  const [loading,setLoading]=useState(true);
  const [detailLoading,setDetailLoading]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const [stickerOpen,setStickerOpen]=useState(false);
  const [image,setImage]=useState<File|null>(null);
  const [preview,setPreview]=useState("");
  const fileRef=useRef<HTMLInputElement|null>(null);
  const endRef=useRef<HTMLDivElement|null>(null);
  const listBusy=useRef(false);
  const detailBusy=useRef(false);
  const latestInboundId=useRef(0);

  useEffect(()=>{selectedRef.current=selected;},[selected]);
  useEffect(()=>{ticketsRef.current=tickets;},[tickets]);

  const dateText=(value?:string|null)=>{if(!value)return "—";const date=new Date(value);return Number.isNaN(date.getTime())?String(value):date.toLocaleString(locale,{dateStyle:"short",timeStyle:"short"});};
  const identity=(t:Ticket)=>String(t.user?.full_name||t.guest?.name||t.user?.email||t.user?.phone||t.guest?.contact||`#${t.id}`);
  const contact=(t:Ticket)=>{const raw=String(t.user?.email||t.user?.phone||t.guest?.contact||"");return sourceOf(t)==="telegram"&&/^\d+$/.test(raw)?`Telegram ID: ${raw}`:raw||"—";};
  const statusText=(s:string)=>s==="open"?pick("نیاز به پاسخ","Needs reply"):s==="answered"?pick("پاسخ داده شده","Answered"):s==="closed"?pick("بسته شده","Closed"):s;
  const statusTone=(s:string):"ok"|"warn"|"bad"|"violet"=>s==="open"?"warn":s==="answered"?"ok":s==="closed"?"bad":"violet";
  const sourceText=(t:Ticket)=>sourceOf(t)==="telegram"?pick("تلگرام","Telegram"):sourceOf(t)==="live"?pick("چت آنلاین","Live chat"):pick("پنل","Panel");
  const sourceIcon=(t:Ticket)=>sourceOf(t)==="telegram"?"✈":sourceOf(t)==="live"?"●":"◫";

  const replaceTickets=(rows:Ticket[])=>{
    const sorted=sortRows(rows);
    ticketsRef.current=sorted;
    setTickets(sorted);
    saveListCache(sorted);
    setSelected(current=>current&&sorted.some(x=>x.id===current)?current:(sorted.find(x=>x.status==="open")?.id??sorted[0]?.id??null));
  };

  const loadList=async(showError=false)=>{
    if(listBusy.current)return;
    listBusy.current=true;
    try{
      const rows=rowsFrom(await opsApi.supportTickets());
      replaceTickets(rows);
      setError("");
    }catch(reason){
      if(showError&&ticketsRef.current.length===0)setError(friendlyError(reason,"پاسخ سرور پشتیبانی دیر رسید؛ دوباره تلاش کنید.","Support server response took too long; please retry.",lang));
    }finally{listBusy.current=false;setLoading(false);}
  };

  const loadDetail=async(id:number,showError=false)=>{
    if(detailBusy.current)return;
    detailBusy.current=true;
    if(showError)setDetailLoading(true);
    try{
      const next=detailFrom(await opsApi.supportTicket(id));
      if(selectedRef.current===id)setDetail(next);
      saveDetailCache(next);
      setTickets(current=>{const nextRows=sortRows(current.map(x=>x.id===id?{...x,...next,messages:undefined}:x));ticketsRef.current=nextRows;saveListCache(nextRows);return nextRows;});
      setError("");
    }catch(reason){
      if(showError&&!detail)setError(friendlyError(reason,"دریافت پیام‌ها دیر پاسخ داد؛ دوباره گفتگو را انتخاب کنید.","Loading messages took too long; select the conversation again.",lang));
    }finally{detailBusy.current=false;if(showError)setDetailLoading(false);}
  };

  useEffect(()=>{
    const cached=readListCache();
    if(cached.length){replaceTickets(cached);setLoading(false);}
    void loadList(cached.length===0);
    const fallback=window.setInterval(()=>{if(document.visibilityState==="visible")void loadList(false);},15000);
    return()=>window.clearInterval(fallback);
  },[]);

  useEffect(()=>{
    if(!selected){setDetail(null);return;}
    const cached=readDetailCache(selected);
    if(cached){setDetail(cached);setDetailLoading(false);}else{setDetail(null);setDetailLoading(true);}
    void loadDetail(selected,!cached);
    const fallback=window.setInterval(()=>{if(document.visibilityState==="visible")void loadDetail(selected,false);},6000);
    return()=>window.clearInterval(fallback);
  },[selected]);

  useEffect(()=>{
    const onPulse=(event:Event)=>{
      const payload=(event as CustomEvent<Pulse>).detail||{};
      const latest=Math.max(0,Number(payload.latest_support_message_id)||0);
      if(latestInboundId.current===0){latestInboundId.current=latest;return;}
      if(latest<=latestInboundId.current)return;
      latestInboundId.current=latest;
      void loadList(false);
      const id=selectedRef.current;if(id)void loadDetail(id,false);
    };
    window.addEventListener(ADMIN_PULSE_EVENT,onPulse as EventListener);
    return()=>window.removeEventListener(ADMIN_PULSE_EVENT,onPulse as EventListener);
  },[]);

  useEffect(()=>{if(detail?.messages?.length)window.setTimeout(()=>endRef.current?.scrollIntoView({block:"end"}),10);},[selected,detail?.messages?.length]);
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview);},[preview]);

  const filtered=useMemo(()=>{
    const q=query.trim().toLowerCase();
    return tickets.filter(t=>(sourceFilter==="all"||sourceOf(t)===sourceFilter)&&(statusFilter==="all"||t.status===statusFilter)&&(!q||[t.id,t.subject,t.category,identity(t),contact(t)].join(" ").toLowerCase().includes(q)));
  },[tickets,query,sourceFilter,statusFilter]);

  const chooseImage=(file?:File|null)=>{if(!file)return;if(!ALLOWED_IMAGES.has(file.type)){setError(pick("فرمت تصویر پشتیبانی نمی‌شود","Unsupported image format"));return;}if(file.size>MAX_IMAGE_BYTES){setError(pick("حداکثر حجم تصویر ۵ مگابایت است","Maximum image size is 5 MB"));return;}if(preview)URL.revokeObjectURL(preview);setImage(file);setPreview(URL.createObjectURL(file));setError("");};
  const clearImage=()=>{if(preview)URL.revokeObjectURL(preview);setImage(null);setPreview("");if(fileRef.current)fileRef.current.value="";};
  const optimisticReply=(text:string)=>{if(!detail)return 0;const pending:Message={id:-Date.now(),ticket_id:detail.id,sender_role:"admin",source:"admin",message:text,created_at:new Date().toISOString(),_pending:true};setDetail(current=>current?{...current,status:"answered",messages:[...(current.messages||[]),pending]}:current);setReply("");return pending.id;};

  const sendText=async(text:string)=>{
    if(!selected||!text.trim())return;
    const clean=text.trim();const tempId=optimisticReply(clean);setOk("");setError("");
    try{
      const next=detailFrom(await opsApi.supportReplyFull(selected,{message:clean}));
      if(selectedRef.current===selected){setDetail(next);saveDetailCache(next);}
      setOk(sourceOf(next)==="telegram"?pick("پاسخ برای تلگرام ارسال شد.","Reply sent to Telegram."):pick("پیام ارسال شد.","Message sent."));
      void loadList(false);
    }catch(reason){
      if(selectedRef.current===selected)setDetail(current=>current?{...current,messages:(current.messages||[]).filter(x=>x.id!==tempId)}:current);
      setReply(clean);setError(friendlyError(reason,"ارسال پیام دیر پاسخ داد؛ دوباره تلاش کنید.","Message delivery took too long; please retry.",lang));
    }
  };

  const submit=async(event:FormEvent)=>{
    event.preventDefault();if(!selected||(!reply.trim()&&!image))return;
    if(!image){await sendText(reply);return;}
    setError("");setOk("");
    try{
      const upload=await opsApi.supportUploadImage(selected,image) as UploadResult;
      const next=detailFrom(await opsApi.supportReplyFull(selected,{message:reply.trim()||null,attachment_type:upload.attachment_type,attachment_ref:upload.attachment_ref}));
      setDetail(next);saveDetailCache(next);setReply("");clearImage();setOk(pick("تصویر ارسال شد.","Image sent."));void loadList(false);
    }catch(reason){setError(friendlyError(reason,"ارسال تصویر دیر پاسخ داد؛ دوباره تلاش کنید.","Image delivery took too long; please retry.",lang));}
  };

  const toggleClosed=async()=>{
    if(!selected||!detail)return;
    try{
      const next=detailFrom(detail.status==="closed"?await opsApi.supportReopen(selected):await opsApi.supportClose(selected));
      setDetail(current=>current?{...current,...next}:next);saveDetailCache(next);void loadList(false);
    }catch(reason){setError(friendlyError(reason,"تغییر وضعیت گفتگو انجام نشد.","Could not update conversation status.",lang));}
  };

  const deleteTicket=async()=>{
    if(!selected||!window.confirm(pick("این گفتگو حذف شود؟","Delete this conversation?")))return;
    const id=selected;const previous=ticketsRef.current;
    replaceTickets(previous.filter(x=>x.id!==id));setSelected(null);setDetail(null);
    try{await opsApi.supportDelete(id);try{sessionStorage.removeItem(`${DETAIL_CACHE_PREFIX}${id}`);}catch{}setOk(pick("گفتگو حذف شد.","Conversation deleted."));}
    catch(reason){replaceTickets(previous);setError(friendlyError(reason,"حذف گفتگو انجام نشد.","Could not delete conversation.",lang));}
  };

  const deleteMessage=async(id:number)=>{
    if(!selected||id<0||!window.confirm(pick("این پیام حذف شود؟","Delete this message?")))return;
    const previous=detail;
    setDetail(current=>current?{...current,messages:(current.messages||[]).filter(x=>x.id!==id)}:current);
    try{const next=detailFrom(await opsApi.supportDeleteMessage(selected,id));setDetail(next);saveDetailCache(next);}
    catch(reason){setDetail(previous);setError(friendlyError(reason,"حذف پیام انجام نشد.","Could not delete message.",lang));}
  };

  const openCount=tickets.filter(x=>x.status==="open").length;
  const telegram=tickets.filter(x=>sourceOf(x)==="telegram").length;
  const live=tickets.filter(x=>sourceOf(x)==="live").length;
  const panel=tickets.filter(x=>sourceOf(x)==="panel").length;

  return <Shell active="/admin/support"><div className="page supportCenterV1 supportCenterV2"><input ref={fileRef} type="file" hidden accept="image/jpeg,image/png,image/webp,image/gif" onChange={e=>chooseImage(e.target.files?.[0])}/>
    <div className="page-head"><div><h1>{pick("مرکز پشتیبانی","Support Center")}</h1></div><button className="ghost" disabled={loading} onClick={()=>{void loadList(true);const id=selectedRef.current;if(id)void loadDetail(id,true);}}>{pick("بروزرسانی","Refresh")}</button></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}
    <div className="stats dashboard-stats supportCenterStatsV1"><Stat label={pick("نیاز به پاسخ","Needs reply")} value={String(openCount)} icon="●"/><Stat label={pick("ربات تلگرام","Telegram bot")} value={String(telegram)} icon="✈"/><Stat label={pick("چت آنلاین","Live chat")} value={String(live)} icon="◉"/><Stat label={pick("پنل کاربری","Customer panel")} value={String(panel)} icon="◫"/></div>
    <div className="supportCenterToolbarV1"><label className="supportSearchV1">⌕<input value={query} onChange={e=>setQuery(e.target.value)} placeholder={pick("جستجو...","Search...")}/></label><div className="supportFilterGroupV1">{(["all","telegram","live","panel"] as Source[]).map(value=><button type="button" key={value} className={sourceFilter===value?"active":""} onClick={()=>setSourceFilter(value)}>{value==="all"?pick("همه کانال‌ها","All channels"):value==="telegram"?pick("تلگرام","Telegram"):value==="live"?pick("چت آنلاین","Live chat"):pick("پنل","Panel")}</button>)}</div><div className="supportFilterGroupV1">{(["all","open","answered","closed"] as Status[]).map(value=><button type="button" key={value} className={statusFilter===value?"active":""} onClick={()=>setStatusFilter(value)}>{value==="all"?pick("همه","All"):statusText(value)}</button>)}</div></div>
    <div className="supportCenterGridV1">
      <aside className="supportInboxV1"><header><b>{pick("گفتگوها","Conversations")}</b><span>{filtered.length}</span></header><div className="supportTicketListV1">{loading&&tickets.length===0?<div className="supportEmptyV1">{pick("در حال دریافت...","Loading...")}</div>:filtered.length===0?<div className="supportEmptyV1">{pick("گفتگویی پیدا نشد.","No conversations found.")}</div>:filtered.map(item=><button type="button" key={item.id} className={selected===item.id?"active":""} onClick={()=>setSelected(item.id)}><span className={`supportTicketIconV1 ${sourceOf(item)}`}>{sourceIcon(item)}</span><div><b>{identity(item)}</b><small>{contact(item)}</small><strong>#{item.id} {item.subject||item.category_title||pick("پشتیبانی","Support")}</strong><footer><Badge tone={statusTone(item.status)}>{statusText(item.status)}</Badge><span>{sourceText(item)}</span><time>{dateText(item.last_message_at||item.updated_at)}</time></footer></div></button>)}</div></aside>
      <section className="supportConversationV1">{!selected?<div className="supportConversationEmptyV1"><span>💬</span><b>{pick("یک گفتگو را انتخاب کنید","Select a conversation")}</b></div>:detailLoading&&!detail?<div className="supportConversationEmptyV1"><b>{pick("در حال دریافت پیام‌ها...","Loading messages...")}</b></div>:detail?<><header className="supportConversationHeadV1"><div><b>{identity(detail)}</b><small>{contact(detail)}</small><span>{sourceText(detail)} · #{detail.id}</span></div><div><Badge tone={statusTone(detail.status)}>{statusText(detail.status)}</Badge><button className="ghost" onClick={()=>void toggleClosed()}>{detail.status==="closed"?pick("باز کردن","Reopen"):pick("بستن گفتگو","Close")}</button><button className="ghost" onClick={()=>void deleteTicket()}>{pick("حذف گفتگو","Delete")}</button></div></header><div className="supportMessagesV1">{(detail.messages||[]).map(item=>{const admin=item.sender_role==="admin";return <article key={item.id} className={admin?"admin":"customer"}><div><b>{admin?pick("پشتیبانی","Support"):identity(detail)}</b><time>{item._pending?pick("در حال ارسال","Sending"):dateText(item.created_at)}</time>{item.id>0&&<button type="button" className="supportMessageDeleteV2" onClick={()=>void deleteMessage(item.id)}>×</button>}</div>{item.message&&<p>{item.message}</p>}{item.attachment_ref&&<a href={attachmentUrl(item.attachment_ref)} target="_blank" rel="noreferrer"><img src={attachmentUrl(item.attachment_ref)} alt="" className="supportMessageImageV1"/></a>}</article>})}<div ref={endRef}/></div>{detail.status!=="closed"&&<form className="supportComposerV1" onSubmit={submit}>{preview&&<div className="supportChatImagePreview compact"><img src={preview} alt=""/><button type="button" onClick={clearImage}>×</button></div>}<textarea value={reply} onChange={e=>setReply(e.target.value)} placeholder={pick("پیام خود را بنویسید...","Write a reply...")} rows={3}/><div><button type="button" className="ghost" onClick={()=>fileRef.current?.click()}>📎 {pick("تصویر","Image")}</button><div className="supportEmojiRootV3"><button type="button" className="ghost" onClick={()=>setStickerOpen(v=>!v)}>✨ {pick("استیکر","Sticker")}</button>{stickerOpen&&<div className="supportEmojiPickerV3">{STICKERS.map(x=><button type="button" key={x} onClick={()=>{setStickerOpen(false);void sendText(x);}}>{x}</button>)}</div>}</div><button type="submit" className="primary" disabled={!reply.trim()&&!image}>{pick("ارسال","Send")}</button></div></form>}</>:<div className="supportConversationEmptyV1"><b>{pick("گفتگو در دسترس نیست","Conversation unavailable")}</b></div>}</section>
    </div>
  </div></Shell>;
}
