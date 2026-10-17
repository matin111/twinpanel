"use client";

import {FormEvent,useEffect,useMemo,useRef,useState} from "react";
import {API_BASE} from "../lib/api";
import {opsApi} from "../lib/admin-ops-api";
import {useI18n} from "../lib/i18n";
import {Badge,Card,Shell,Stat} from "./ui";

type TicketUser={
  email?:string|null;
  phone?:string|null;
  full_name?:string|null;
};

type TicketGuest={
  name?:string|null;
  contact?:string|null;
};

type SupportMessage={
  id:number;
  ticket_id:number;
  sender_user_id?:number|null;
  sender_role:string;
  source?:string|null;
  message?:string|null;
  attachment_type?:string|null;
  attachment_ref?:string|null;
  created_at:string;
};

type SupportTicket={
  id:number;
  user_id?:number|null;
  user?:TicketUser|null;
  guest?:TicketGuest|null;
  category?:string|null;
  category_title?:string|null;
  subject?:string|null;
  status:string;
  source?:string|null;
  created_at?:string|null;
  updated_at?:string|null;
  last_message_at?:string|null;
  closed_at?:string|null;
  messages?:SupportMessage[];
};

type SourceFilter="all"|"telegram"|"live"|"panel";
type StatusFilter="all"|"open"|"answered"|"closed";
type UploadResult={attachment_type:string;attachment_ref:string};

const ALLOWED_IMAGES=new Set(["image/jpeg","image/png","image/webp","image/gif"]);
const MAX_IMAGE_BYTES=5*1024*1024;

function rowsFrom(value:unknown):SupportTicket[]{
  if(Array.isArray(value))return value.filter(Boolean) as SupportTicket[];
  if(value&&typeof value==="object"){
    const root=value as Record<string,unknown>;
    for(const key of ["tickets","items","results"]){
      const rows=root[key];
      if(Array.isArray(rows))return rows.filter(Boolean) as SupportTicket[];
    }
  }
  return [];
}

function normalizeDetail(value:unknown):SupportTicket{
  if(!value||typeof value!=="object")return {id:0,status:"open",messages:[]};
  const root=value as Record<string,unknown>;
  const ticket=(root.ticket&&typeof root.ticket==="object"?root.ticket:root) as SupportTicket;
  const messages=Array.isArray(root.messages)?root.messages as SupportMessage[]:Array.isArray(ticket.messages)?ticket.messages:[];
  return {...ticket,messages};
}

function ticketSource(ticket:SupportTicket):Exclude<SourceFilter,"all">{
  const source=String(ticket.source||"").trim().toLowerCase();
  const subject=String(ticket.subject||"").toLowerCase();
  if(source==="telegram"||subject.includes("تلگرام")||subject.includes("telegram"))return "telegram";
  if(source==="store_guest"||source==="live_chat"||ticket.user_id==null||subject.includes("گفتگوی آنلاین")||subject.includes("live chat"))return "live";
  return "panel";
}

function attachmentUrl(value?:string|null){
  const ref=String(value||"").trim();
  if(!ref)return "";
  if(ref.startsWith("http://")||ref.startsWith("https://"))return ref;
  return `${API_BASE}${ref.startsWith("/")?ref:`/v1/support/files/${encodeURIComponent(ref)}`}`;
}

export function SupportCenterRuntime(){
  const {pick,lang}=useI18n();
  const [tickets,setTickets]=useState<SupportTicket[]>([]);
  const [selected,setSelected]=useState<number|null>(null);
  const [detail,setDetail]=useState<SupportTicket|null>(null);
  const [query,setQuery]=useState("");
  const [sourceFilter,setSourceFilter]=useState<SourceFilter>("all");
  const [statusFilter,setStatusFilter]=useState<StatusFilter>("all");
  const [reply,setReply]=useState("");
  const [image,setImage]=useState<File|null>(null);
  const [preview,setPreview]=useState("");
  const [loading,setLoading]=useState(true);
  const [detailLoading,setDetailLoading]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [ok,setOk]=useState("");
  const fileRef=useRef<HTMLInputElement|null>(null);
  const endRef=useRef<HTMLDivElement|null>(null);

  const locale=lang==="fa"?"fa-IR":"en-GB";
  const dateText=(value?:string|null)=>{
    if(!value)return "—";
    const date=new Date(value);
    return Number.isNaN(date.getTime())?String(value):date.toLocaleString(locale,{dateStyle:"medium",timeStyle:"short"});
  };

  const sourceLabel=(ticket:SupportTicket)=>{
    const source=ticketSource(ticket);
    if(source==="telegram")return pick("ربات تلگرام","Telegram bot");
    if(source==="live")return pick("چت آنلاین","Live chat");
    return pick("پنل کاربری","Customer panel");
  };

  const sourceIcon=(ticket:SupportTicket)=>{
    const source=ticketSource(ticket);
    if(source==="telegram")return "✈";
    if(source==="live")return "●";
    return "◫";
  };

  const statusLabel=(status:string)=>{
    const value=String(status||"").toLowerCase();
    if(value==="open")return pick("نیاز به پاسخ","Needs reply");
    if(value==="answered")return pick("پاسخ داده شده","Answered");
    if(value==="closed")return pick("بسته شده","Closed");
    return value||"—";
  };

  const statusTone=(status:string):"ok"|"warn"|"bad"|"violet"=>{
    const value=String(status||"").toLowerCase();
    if(value==="open")return "warn";
    if(value==="answered")return "ok";
    if(value==="closed")return "bad";
    return "violet";
  };

  const categoryLabel=(ticket:SupportTicket)=>{
    const category=String(ticket.category||"").toLowerCase();
    const map:Record<string,[string,string]>={
      connection:["مشکل اتصال","Connection"],
      payment:["خرید و پرداخت","Payment"],
      subscription:["اشتراک","Subscription"],
      sublink:["لینک اشتراک","Subscription link"],
      other:["سایر موارد","Other"],
    };
    const pair=map[category];
    return pair?pick(pair[0],pair[1]):String(ticket.category_title||ticket.category||"—");
  };

  const identity=(ticket:SupportTicket)=>{
    const user=ticket.user||{};
    const guest=ticket.guest||{};
    return String(user.full_name||guest.name||user.email||user.phone||guest.contact||`#${ticket.id}`);
  };

  const contact=(ticket:SupportTicket)=>{
    const user=ticket.user||{};
    const guest=ticket.guest||{};
    const raw=String(user.email||user.phone||guest.contact||"").trim();
    if(ticketSource(ticket)==="telegram"&&/^\d+$/.test(raw))return `Telegram ID: ${raw}`;
    return raw||pick("بدون اطلاعات تماس","No contact information");
  };

  const loadTickets=async(silent=false)=>{
    if(!silent)setLoading(true);
    try{
      const rows=rowsFrom(await opsApi.supportTickets());
      setTickets(rows);
      setSelected(current=>{
        if(current&&rows.some(row=>row.id===current))return current;
        return rows.find(row=>row.status==="open")?.id??rows[0]?.id??null;
      });
      if(!silent)setError("");
    }catch(reason){if(!silent)setError(reason instanceof Error?reason.message:String(reason));}
    finally{if(!silent)setLoading(false);}
  };

  const loadDetail=async(ticketId:number,silent=false)=>{
    if(!silent)setDetailLoading(true);
    try{
      setDetail(normalizeDetail(await opsApi.supportTicket(ticketId)));
      if(!silent)setError("");
    }catch(reason){if(!silent)setError(reason instanceof Error?reason.message:String(reason));}
    finally{if(!silent)setDetailLoading(false);}
  };

  useEffect(()=>{
    void loadTickets();
    const timer=window.setInterval(()=>{if(document.visibilityState==="visible")void loadTickets(true);},5000);
    return()=>window.clearInterval(timer);
  },[]);

  useEffect(()=>{
    if(!selected){setDetail(null);return;}
    void loadDetail(selected);
    const timer=window.setInterval(()=>{if(document.visibilityState==="visible")void loadDetail(selected,true);},3000);
    return()=>window.clearInterval(timer);
  },[selected]);

  useEffect(()=>{if(detail?.messages?.length)window.setTimeout(()=>endRef.current?.scrollIntoView({block:"end"}),40);},[selected,detail?.messages?.length]);
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview);},[preview]);

  const resetImage=()=>{
    if(preview)URL.revokeObjectURL(preview);
    setImage(null);setPreview("");if(fileRef.current)fileRef.current.value="";
  };

  const chooseImage=(file?:File|null)=>{
    if(!file)return;
    if(!ALLOWED_IMAGES.has(file.type)){setError(pick("فرمت تصویر باید JPG، PNG، WebP یا GIF باشد.","Image must be JPG, PNG, WebP or GIF."));return;}
    if(file.size>MAX_IMAGE_BYTES){setError(pick("حداکثر حجم تصویر ۵ مگابایت است.","Maximum image size is 5 MB."));return;}
    if(preview)URL.revokeObjectURL(preview);
    setImage(file);setPreview(URL.createObjectURL(file));setError("");
  };

  const refreshAfterAction=async(ticketId:number)=>{await Promise.all([loadTickets(true),loadDetail(ticketId,true)]);};

  const sendReply=async(event:FormEvent)=>{
    event.preventDefault();if(!selected||busy)return;
    const text=reply.trim();if(!text&&!image)return;
    setBusy(true);setError("");setOk("");
    try{
      let attachment:UploadResult|null=null;
      if(image)attachment=await opsApi.supportUploadImage(selected,image) as UploadResult;
      const updated=normalizeDetail(await opsApi.supportReplyFull(selected,{message:text||null,attachment_type:attachment?.attachment_type||null,attachment_ref:attachment?.attachment_ref||null}));
      setDetail(updated);setReply("");resetImage();
      setOk(ticketSource(updated)==="telegram"?pick("پاسخ ثبت شد و برای کاربر تلگرام هم ارسال می‌شود.","Reply saved and queued for the Telegram user."):pick("پاسخ ارسال شد.","Reply sent."));
      await loadTickets(true);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const closeOrReopen=async()=>{
    if(!selected||!detail||busy)return;
    setBusy(true);setError("");setOk("");
    try{
      if(detail.status==="closed")await opsApi.supportReopen(selected);else await opsApi.supportClose(selected);
      setOk(detail.status==="closed"?pick("گفتگو دوباره باز شد.","Conversation reopened."):pick("گفتگو بسته شد.","Conversation closed."));
      await refreshAfterAction(selected);
    }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const deleteTicket=async()=>{
    if(!selected||busy)return;
    if(!window.confirm(pick("این گفتگو و تمام پیام‌های آن حذف شود؟","Delete this conversation and all of its messages?")))return;
    setBusy(true);setError("");setOk("");
    try{await opsApi.supportDelete(selected);setDetail(null);setSelected(null);await loadTickets(true);setOk(pick("گفتگو حذف شد.","Conversation deleted."));}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}
    finally{setBusy(false);}
  };

  const filtered=useMemo(()=>{
    const needle=query.trim().toLowerCase();
    return tickets.filter(ticket=>{
      if(sourceFilter!=="all"&&ticketSource(ticket)!==sourceFilter)return false;
      if(statusFilter!=="all"&&ticket.status!==statusFilter)return false;
      if(!needle)return true;
      return [ticket.id,ticket.subject,ticket.category,ticket.category_title,identity(ticket),contact(ticket),ticket.source].map(value=>String(value??"").toLowerCase()).join(" ").includes(needle);
    });
  },[tickets,query,sourceFilter,statusFilter,lang]);

  const needsReply=tickets.filter(ticket=>ticket.status==="open").length;
  const telegram=tickets.filter(ticket=>ticketSource(ticket)==="telegram").length;
  const live=tickets.filter(ticket=>ticketSource(ticket)==="live").length;
  const panel=tickets.filter(ticket=>ticketSource(ticket)==="panel").length;

  return <Shell active="/admin/support"><div className="page supportCenterV1">
    <input ref={fileRef} type="file" hidden accept="image/jpeg,image/png,image/webp,image/gif" onChange={event=>chooseImage(event.target.files?.[0])}/>
    <div className="page-head supportCenterHeadV1"><div><h1>{pick("مرکز پشتیبانی","Support Center")}</h1><p>{pick("یک صندوق ورودی برای ربات تلگرام، چت آنلاین و پنل کاربری","One inbox for Telegram bot, live chat and customer panel")}</p></div><button className="ghost" disabled={loading} onClick={()=>void loadTickets()}>{pick("بروزرسانی","Refresh")}</button></div>
    {error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}
    <div className="stats dashboard-stats supportCenterStatsV1"><Stat label={pick("نیاز به پاسخ","Needs reply")} value={String(needsReply)} icon="●"/><Stat label={pick("ربات تلگرام","Telegram bot")} value={String(telegram)} icon="✈"/><Stat label={pick("چت آنلاین","Live chat")} value={String(live)} icon="◉"/><Stat label={pick("پنل کاربری","Customer panel")} value={String(panel)} icon="◫"/></div>
    <div className="supportCenterToolbarV1">
      <label className="supportSearchV1">⌕<input value={query} onChange={event=>setQuery(event.target.value)} placeholder={pick("جستجو در نام، شناسه، موضوع یا تماس...","Search name, ID, subject or contact...")}/></label>
      <div className="supportFilterGroupV1">{(["all","telegram","live","panel"] as SourceFilter[]).map(value=><button type="button" key={value} className={sourceFilter===value?"active":""} onClick={()=>setSourceFilter(value)}>{value==="all"?pick("همه کانال‌ها","All channels"):value==="telegram"?pick("تلگرام","Telegram"):value==="live"?pick("چت آنلاین","Live chat"):pick("پنل","Panel")}</button>)}</div>
      <div className="supportFilterGroupV1">{(["all","open","answered","closed"] as StatusFilter[]).map(value=><button type="button" key={value} className={statusFilter===value?"active":""} onClick={()=>setStatusFilter(value)}>{value==="all"?pick("همه وضعیت‌ها","All statuses"):statusLabel(value)}</button>)}</div>
    </div>
    <div className="supportCenterGridV1">
      <Card className="supportInboxV1"><div className="supportPaneTitleV1"><b>{pick("گفتگوها","Conversations")}</b><span>{filtered.length.toLocaleString(locale)}</span></div><div className="supportTicketListV1">
        {loading&&tickets.length===0?<div className="runtime-loading">{pick("در حال دریافت گفتگوها...","Loading conversations...")}</div>:filtered.length===0?<div className="runtime-empty">{pick("گفتگویی با این فیلتر پیدا نشد.","No conversations match these filters.")}</div>:filtered.map(ticket=>{
          const active=selected===ticket.id;
          return <button type="button" key={ticket.id} className={`supportTicketV1 ${active?"active":""} ${ticket.status==="open"?"needsReply":""}`} onClick={()=>setSelected(ticket.id)}>
            <div className="supportTicketTopV1"><span className={`supportSourceDotV1 ${ticketSource(ticket)}`}>{sourceIcon(ticket)}</span><div className="grow"><b>{identity(ticket)}</b><small>{contact(ticket)}</small></div><time>{dateText(ticket.last_message_at||ticket.updated_at||ticket.created_at)}</time></div>
            <div className="supportTicketSubjectV1"><span>#{ticket.id}</span><strong>{ticket.subject||categoryLabel(ticket)}</strong></div>
            <div className="supportTicketMetaV1"><Badge tone={statusTone(ticket.status)}>{statusLabel(ticket.status)}</Badge><span>{sourceLabel(ticket)}</span><span>{categoryLabel(ticket)}</span></div>
          </button>;
        })}
      </div></Card>
      <Card className="supportConversationV1">
        {!selected?<div className="supportBlankV1"><span>💬</span><b>{pick("یک گفتگو را انتخاب کنید","Select a conversation")}</b><p>{pick("پیام‌های تلگرام، چت آنلاین و پنل کاربری اینجا یکجا نمایش داده می‌شوند.","Telegram, live-chat and customer-panel messages appear together here.")}</p></div>:detailLoading&&!detail?<div className="runtime-loading">{pick("در حال دریافت پیام‌ها...","Loading messages...")}</div>:detail?<>
          <div className="supportConversationHeadV1"><div className="supportConversationIdentityV1"><span className={`supportSourceAvatarV1 ${ticketSource(detail)}`}>{sourceIcon(detail)}</span><div><h2>{identity(detail)}</h2><p>{contact(detail)}</p><div><span>#{detail.id}</span><span>{sourceLabel(detail)}</span><span>{categoryLabel(detail)}</span></div></div></div><div className="supportConversationActionsV1"><Badge tone={statusTone(detail.status)}>{statusLabel(detail.status)}</Badge><button type="button" className="ghost" disabled={busy} onClick={()=>void closeOrReopen()}>{detail.status==="closed"?pick("باز کردن دوباره","Reopen"):pick("بستن گفتگو","Close")}</button><button type="button" className="mini-btn danger" disabled={busy} onClick={()=>void deleteTicket()}>{pick("حذف","Delete")}</button></div></div>
          <div className="supportChannelNoteV1">{ticketSource(detail)==="telegram"?pick("این گفتگو از ربات تلگرام آمده است؛ پاسخ مدیر به‌صورت خودکار برای کاربر در تلگرام صف می‌شود.","This conversation came from the Telegram bot; admin replies are automatically queued back to the user on Telegram."):ticketSource(detail)==="live"?pick("این گفتگو از چت آنلاین سایت آمده و کاربر پاسخ را همان‌جا به‌صورت زنده می‌بیند.","This conversation came from live chat; the user sees replies there in near real time."):pick("این گفتگو متعلق به کاربر واردشده در پنل است.","This conversation belongs to a signed-in customer in the panel.")}</div>
          <div className="supportMessagesV1">{(detail.messages||[]).length===0?<div className="runtime-empty">{pick("هنوز پیامی ثبت نشده است.","No messages yet.")}</div>:(detail.messages||[]).map(message=>{
            const admin=String(message.sender_role||"").toLowerCase()==="admin";
            const messageSource=String(message.source||"").toLowerCase();
            const channel=messageSource==="telegram"?pick("تلگرام","Telegram"):messageSource==="store_guest"||messageSource==="live_chat"?pick("چت آنلاین","Live chat"):admin?pick("مدیر","Admin"):pick("پنل","Panel");
            const url=attachmentUrl(message.attachment_ref);
            return <article key={message.id} className={`supportBubbleV1 ${admin?"admin":"customer"}`}><div className="supportBubbleMetaV1"><b>{admin?pick("پشتیبانی","Support"):identity(detail)}</b><span>{channel}</span><time>{dateText(message.created_at)}</time></div>{message.message&&<p>{message.message}</p>}{url&&<a className="supportAttachmentV1" href={url} target="_blank" rel="noreferrer"><img src={url} alt={pick("تصویر پیوست","Attachment")}/><span>{pick("باز کردن تصویر","Open image")}</span></a>}</article>;
          })}<div ref={endRef}/></div>
          <form className="supportComposerV1" onSubmit={sendReply}>{detail.status==="closed"?<div className="supportClosedV1">{pick("این گفتگو بسته شده است. برای پاسخ ابتدا آن را دوباره باز کنید.","This conversation is closed. Reopen it before replying.")}</div>:<>{preview&&<div className="supportAdminPreviewV1"><img src={preview} alt=""/><button type="button" onClick={resetImage}>×</button></div>}<textarea value={reply} onChange={event=>setReply(event.target.value)} placeholder={pick("پاسخ پشتیبانی را بنویسید...","Write a support reply...")} rows={3} maxLength={10000}/><div className="supportComposerActionsV1"><div><button type="button" className="ghost" onClick={()=>fileRef.current?.click()} disabled={busy}>📎 {pick("تصویر","Image")}</button><small>{pick("JPG / PNG / WebP / GIF تا ۵MB","JPG / PNG / WebP / GIF up to 5 MB")}</small></div><button className="primary" disabled={busy||(!reply.trim()&&!image)}>{busy?pick("در حال ارسال...","Sending..."):pick("ارسال پاسخ","Send reply")}</button></div></>}</form>
        </>:null}
      </Card>
    </div>
  </div></Shell>;
}
