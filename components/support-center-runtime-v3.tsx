"use client";

import {FormEvent,useEffect,useMemo,useRef,useState} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {
  playNotificationSound,
  primeNotificationSound,
} from "../lib/notification-sound";
import {Badge,Card,Shell,Stat} from "./ui";

type TicketUser={email?:string|null;phone?:string|null;full_name?:string|null};
type TicketGuest={name?:string|null;contact?:string|null};
type Message={id:number;ticket_id:number;sender_role:string;source?:string|null;message?:string|null;attachment_ref?:string|null;attachment_type?:string|null;created_at:string;_pending?:boolean};
type Ticket={id:number;user_id?:number|null;user?:TicketUser|null;guest?:TicketGuest|null;category?:string|null;category_title?:string|null;subject?:string|null;status:string;source?:string|null;created_at?:string|null;updated_at?:string|null;last_message_at?:string|null;messages?:Message[]};
type Source="all"|"telegram"|"live"|"panel";type Status="all"|"open"|"answered"|"closed";

const STICKERS=["👍","❤️","🙏","😊","😂","🎉","✅","🔥","💜","👋","⭐","🤝","😍","👏","💯","🚀"];
const ALLOWED_IMAGES=new Set(["image/jpeg","image/png","image/webp","image/gif"]);const MAX_IMAGE_BYTES=5*1024*1024;

function rowsFrom(value:unknown):Ticket[]{if(Array.isArray(value))return value as Ticket[];if(value&&typeof value==="object"){const root=value as Record<string,unknown>;for(const key of ["tickets","items","results"]){if(Array.isArray(root[key]))return root[key] as Ticket[];}}return [];}
function detailFrom(value:unknown):Ticket{if(!value||typeof value!=="object")return {id:0,status:"open",messages:[]};const root=value as Record<string,unknown>;const ticket=(root.ticket&&typeof root.ticket==="object"?root.ticket:root) as Ticket;return {...ticket,messages:Array.isArray(root.messages)?root.messages as Message[]:ticket.messages||[]};}
function sourceOf(ticket:Ticket):Exclude<Source,"all">{const source=String(ticket.source||"").toLowerCase();const subject=String(ticket.subject||"").toLowerCase();const email=String(ticket.user?.email||"").trim();if(source==="telegram"||subject.includes("telegram")||subject.includes("تلگرام")||/^\d{6,16}$/.test(email))return "telegram";if(source==="store_guest"||source==="live_chat"||ticket.user_id==null||subject.includes("live chat")||subject.includes("گفتگوی آنلاین"))return "live";return "panel";}
function sortRows(rows:Ticket[]){return [...rows].sort((a,b)=>new Date(b.last_message_at||b.updated_at||b.created_at||0).getTime()-new Date(a.last_message_at||a.updated_at||a.created_at||0).getTime());}
function attachmentUrl(value?:string|null){const ref=String(value||"").trim();if(!ref)return "";if(/^https?:\/\//.test(ref))return ref;return `${API_BASE}${ref.startsWith("/")?ref:`/v1/support/files/${encodeURIComponent(ref)}`}`;}

async function req<T>(path:string,init:RequestInit={}):Promise<T>{const token=getCustomerToken();if(!token)throw new Error("AUTH_REQUIRED");const headers=new Headers(init.headers);headers.set("Authorization",`Bearer ${token}`);if(init.body&&!headers.has("Content-Type")&&!(init.body instanceof Blob)&&!(init.body instanceof FormData))headers.set("Content-Type","application/json");const response=await fetch(`${API_BASE}${path}`,{...init,headers,cache:"no-store",signal:init.signal??AbortSignal.timeout(init.method&&init.method!=="GET"?12000:10000)});if(!response.ok){let message=`API ${response.status}`;try{const payload=await response.json() as {detail?:string;message?:string};message=payload.detail??payload.message??message;}catch{}throw new Error(message);}if(response.status===204)return undefined as T;return response.json() as Promise<T>;}

export function SupportCenterRuntimeV3(){
  const {pick,lang}=useI18n();const locale=lang==="fa"?"fa-IR":"en-GB";
  const [tickets,setTickets]=useState<Ticket[]>([]);const [selected,setSelected]=useState<number|null>(null);const selectedRef=useRef<number|null>(null);const [detail,setDetail]=useState<Ticket|null>(null);
  const [query,setQuery]=useState("");const [sourceFilter,setSourceFilter]=useState<Source>("all");const [statusFilter,setStatusFilter]=useState<Status>("all");const [reply,setReply]=useState("");const [loading,setLoading]=useState(true);const [detailLoading,setDetailLoading]=useState(false);const [error,setError]=useState("");const [ok,setOk]=useState("");const [stickerOpen,setStickerOpen]=useState(false);const [image,setImage]=useState<File|null>(null);const [preview,setPreview]=useState("");const fileRef=useRef<HTMLInputElement|null>(null);const endRef=useRef<HTMLDivElement|null>(null);const listBusy=useRef(false);const detailBusy=useRef(false);
  const adminInboundSeenRef=useRef<Map<number,number>>(new Map());
  useEffect(()=>{selectedRef.current=selected;},[selected]);

  // ADMIN_CHAT_SOUND_UNLOCK_V3
  useEffect(()=>{
    const unlock=()=>{
      void primeNotificationSound();
    };

    window.addEventListener(
      "pointerdown",
      unlock,
    );

    window.addEventListener(
      "keydown",
      unlock,
    );

    return()=>{
      window.removeEventListener(
        "pointerdown",
        unlock,
      );

      window.removeEventListener(
        "keydown",
        unlock,
      );
    };
  },[]);
  const dateText=(value?:string|null)=>{if(!value)return "—";const date=new Date(value);return Number.isNaN(date.getTime())?String(value):date.toLocaleString(locale,{dateStyle:"short",timeStyle:"short"});};
  const identity=(t:Ticket)=>String(t.user?.full_name||t.guest?.name||t.user?.email||t.user?.phone||t.guest?.contact||`#${t.id}`);
  const contact=(t:Ticket)=>{const raw=String(t.user?.email||t.user?.phone||t.guest?.contact||"");return sourceOf(t)==="telegram"&&/^\d+$/.test(raw)?`Telegram ID: ${raw}`:raw||"—";};
  const statusText=(s:string)=>s==="open"?pick("نیاز به پاسخ","Needs reply"):s==="answered"?pick("پاسخ داده شده","Answered"):s==="closed"?pick("بسته شده","Closed"):s;
  const statusTone=(s:string):"ok"|"warn"|"bad"|"violet"=>s==="open"?"warn":s==="answered"?"ok":s==="closed"?"bad":"violet";
  const sourceText=(t:Ticket)=>sourceOf(t)==="telegram"?pick("تلگرام","Telegram"):sourceOf(t)==="live"?pick("چت آنلاین","Live chat"):pick("پنل","Panel");
  const sourceIcon=(t:Ticket)=>sourceOf(t)==="telegram"?"✈":sourceOf(t)==="live"?"●":"◫";

  const merge=(rows:Ticket[],replace=false)=>{setTickets(current=>{const map=new Map<number,Ticket>();if(!replace)current.forEach(x=>map.set(x.id,x));rows.forEach(x=>map.set(x.id,x));return sortRows([...map.values()]);});setSelected(current=>current??rows.find(x=>x.status==="open")?.id??rows[0]?.id??null);};
  const loadList=async(mode:"open"|"all",initial=false)=>{if(listBusy.current&&mode==="open")return;if(mode==="open")listBusy.current=true;try{const rows=rowsFrom(await req<unknown>(`/v1/admin/support/tickets${mode==="open"?"?status=open":""}`));merge(rows,mode==="all");setError("");}catch(reason){if(initial){const raw=reason instanceof Error?reason.message:String(reason);if(!/signal timed out|timeout|aborted/i.test(raw))setError(raw);}}finally{if(mode==="open")listBusy.current=false;if(initial)setLoading(false);}};
  const loadDetail=async(id:number,silent=false)=>{
    if(detailBusy.current)return;

    detailBusy.current=true;

    if(!silent){
      setDetailLoading(true);
    }

    try{
      const next=detailFrom(
        await req<unknown>(
          `/v1/admin/support/tickets/${id}`
        )
      );

      // ADMIN_DIRECT_INBOUND_SOUND_V3
      const newestInbound=Math.max(
        0,
        ...(next.messages||[])
          .filter(message=>{
            const role=String(
              message.sender_role||""
            ).toLowerCase();

            return (
              role!=="admin"
              &&Number(message.id)>0
            );
          })
          .map(
            message=>Number(message.id)||0
          )
      );

      const previousInbound=
        adminInboundSeenRef.current.get(id);

      if(previousInbound===undefined){

        // Seed existing conversation silently.
        adminInboundSeenRef.current.set(
          id,
          newestInbound,
        );

      }else{

        if(
          silent
          &&newestInbound>previousInbound
        ){
          void playNotificationSound(
            "message"
          );
        }

        if(newestInbound>previousInbound){
          adminInboundSeenRef.current.set(
            id,
            newestInbound,
          );
        }
      }

      if(selectedRef.current===id){
        setDetail(next);
      }

      setTickets(current=>
        sortRows(
          current.map(x=>
            x.id===id
              ?{
                  ...x,
                  ...next,
                  messages:undefined,
                }
              :x
          )
        )
      );

      setError("");

    }catch(reason){

      if(!silent){
        const raw=
          reason instanceof Error
            ?reason.message
            :String(reason);

        if(
          !/signal timed out|timeout|aborted/i
            .test(raw)
        ){
          setError(raw);
        }
      }

    }finally{

      detailBusy.current=false;

      if(!silent){
        setDetailLoading(false);
      }
    }
  };

  useEffect(()=>{void loadList("all",true);const fast=window.setInterval(()=>{if(document.visibilityState==="visible")void loadList("open",false);},2500);const slow=window.setInterval(()=>{if(document.visibilityState==="visible")void loadList("all",false);},30000);return()=>{clearInterval(fast);clearInterval(slow);};},[]);
  useEffect(()=>{if(!selected){setDetail(null);return;}setDetail(current=>current?.id===selected?current:null);void loadDetail(selected,false);const timer=window.setInterval(()=>{if(document.visibilityState==="visible")void loadDetail(selected,true);},900);return()=>clearInterval(timer);},[selected]);
  useEffect(()=>{if(detail?.messages?.length)window.setTimeout(()=>endRef.current?.scrollIntoView({block:"end"}),10);},[selected,detail?.messages?.length]);
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview);},[preview]);

  const filtered=useMemo(()=>{const q=query.trim().toLowerCase();return tickets.filter(t=>(sourceFilter==="all"||sourceOf(t)===sourceFilter)&&(statusFilter==="all"||t.status===statusFilter)&&(!q||[t.id,t.subject,t.category,identity(t),contact(t)].join(" ").toLowerCase().includes(q)));},[tickets,query,sourceFilter,statusFilter]);
  const chooseImage=(file?:File|null)=>{if(!file)return;if(!ALLOWED_IMAGES.has(file.type)){setError(pick("فرمت تصویر پشتیبانی نمی‌شود","Unsupported image format"));return;}if(file.size>MAX_IMAGE_BYTES){setError(pick("حداکثر حجم تصویر ۵ مگابایت است","Maximum image size is 5 MB"));return;}if(preview)URL.revokeObjectURL(preview);setImage(file);setPreview(URL.createObjectURL(file));};
  const clearImage=()=>{if(preview)URL.revokeObjectURL(preview);setImage(null);setPreview("");if(fileRef.current)fileRef.current.value="";};
  const optimisticReply=(text:string)=>{if(!detail)return;const pending:Message={id:-Date.now(),ticket_id:detail.id,sender_role:"admin",source:"admin",message:text,created_at:new Date().toISOString(),_pending:true};setDetail(current=>current?{...current,status:"answered",messages:[...(current.messages||[]),pending]}:current);setReply("");setOk(pick("پیام ثبت شد؛ در حال تحویل است.","Message queued for delivery."));return pending.id;};
  const sendText=async(text:string)=>{if(!selected||!text.trim())return;const clean=text.trim();const tempId=optimisticReply(clean);try{const next=detailFrom(await req<unknown>(`/v1/admin/support/tickets/${selected}/reply`,{method:"POST",body:JSON.stringify({message:clean})}));if(selectedRef.current===selected)setDetail(next);setOk(sourceOf(next)==="telegram"?pick("پاسخ در صف تلگرام قرار گرفت.","Reply queued for Telegram."):pick("پیام ارسال شد.","Message sent."));}catch(reason){if(selectedRef.current===selected)setDetail(current=>current?{...current,messages:(current.messages||[]).filter(x=>x.id!==tempId)}:current);setReply(clean);setError(reason instanceof Error?reason.message:String(reason));}};
  const submit=async(event:FormEvent)=>{event.preventDefault();if(!selected||(!reply.trim()&&!image))return;if(!image){await sendText(reply);return;}try{const token=getCustomerToken();if(!token)throw new Error("AUTH_REQUIRED");const headers=new Headers({Authorization:`Bearer ${token}`,"Content-Type":image.type||"application/octet-stream"});const upload=await fetch(`${API_BASE}/v1/admin/support/tickets/${selected}/upload-image`,{method:"POST",headers,body:image,cache:"no-store",signal:AbortSignal.timeout(10000)});if(!upload.ok)throw new Error(`UPLOAD ${upload.status}`);const attachment=await upload.json() as {attachment_type:string;attachment_ref:string};const next=detailFrom(await req<unknown>(`/v1/admin/support/tickets/${selected}/reply`,{method:"POST",body:JSON.stringify({message:reply.trim()||null,attachment_type:attachment.attachment_type,attachment_ref:attachment.attachment_ref})}));setDetail(next);setReply("");clearImage();setOk(pick("تصویر ارسال شد.","Image sent."));}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}};
  const toggleClosed=async()=>{if(!selected||!detail)return;const reopen=detail.status==="closed";try{const next=detailFrom(await req<unknown>(`/v1/admin/support/tickets/${selected}/${reopen?"reopen":"close"}`,{method:"POST"}));setDetail(current=>current?{...current,...next}:next);void loadList("all",false);}catch(reason){setError(reason instanceof Error?reason.message:String(reason));}};
  const deleteTicket=async()=>{if(!selected||!window.confirm(pick("این گفتگو حذف شود؟","Delete this conversation?")))return;const id=selected;setTickets(current=>current.filter(x=>x.id!==id));setSelected(null);setDetail(null);try{await req(`/v1/admin/support/tickets/${id}`,{method:"DELETE"});setOk(pick("گفتگو حذف شد.","Conversation deleted."));void loadList("all",false);}catch(reason){setError(reason instanceof Error?reason.message:String(reason));void loadList("all",false);}};
  const deleteMessage=async(id:number)=>{if(!selected||id<0||!window.confirm(pick("این پیام حذف شود؟","Delete this message?")))return;setDetail(current=>current?{...current,messages:(current.messages||[]).filter(x=>x.id!==id)}:current);try{const next=detailFrom(await req<unknown>(`/v1/admin/support/tickets/${selected}/messages/${id}`,{method:"DELETE"}));setDetail(next);}catch(reason){setError(reason instanceof Error?reason.message:String(reason));void loadDetail(selected,true);}};

  const openCount=tickets.filter(x=>x.status==="open").length;const telegram=tickets.filter(x=>sourceOf(x)==="telegram").length;const live=tickets.filter(x=>sourceOf(x)==="live").length;const panel=tickets.filter(x=>sourceOf(x)==="panel").length;
  return <Shell active="/admin/support"><div className="page supportCenterV1 supportCenterV2"><input ref={fileRef} type="file" hidden accept="image/jpeg,image/png,image/webp,image/gif" onChange={e=>chooseImage(e.target.files?.[0])}/><div className="page-head"><div><h1>{pick("مرکز پشتیبانی","Support Center")}</h1><p>{pick("گفتگوی سریع ربات تلگرام، سایت و پنل کاربری","Fast Telegram, website and customer-panel inbox")}</p></div><button className="ghost" onClick={()=>{void loadList("open",false);void loadList("all",false);}}>{pick("بروزرسانی","Refresh")}</button></div>{error&&<div className="runtime-error">{error}</div>}{ok&&<div className="runtime-success">{ok}</div>}<div className="stats dashboard-stats supportCenterStatsV1"><Stat label={pick("نیاز به پاسخ","Needs reply")} value={String(openCount)} icon="●"/><Stat label={pick("ربات تلگرام","Telegram bot")} value={String(telegram)} icon="✈"/><Stat label={pick("چت آنلاین","Live chat")} value={String(live)} icon="◉"/><Stat label={pick("پنل کاربری","Customer panel")} value={String(panel)} icon="◫"/></div>
  <div className="supportCenterToolbarV1"><label className="supportSearchV1">⌕<input value={query} onChange={e=>setQuery(e.target.value)} placeholder={pick("جستجو...","Search...")}/></label><div className="supportFilterGroupV1">{(["all","telegram","live","panel"] as Source[]).map(v=><button type="button" key={v} className={sourceFilter===v?"active":""} onClick={()=>setSourceFilter(v)}>{v==="all"?pick("همه کانال‌ها","All channels"):v==="telegram"?pick("تلگرام","Telegram"):v==="live"?pick("چت آنلاین","Live chat"):pick("پنل","Panel")}</button>)}</div><div className="supportFilterGroupV1">{(["all","open","answered","closed"] as Status[]).map(v=><button type="button" key={v} className={statusFilter===v?"active":""} onClick={()=>setStatusFilter(v)}>{v==="all"?pick("همه وضعیت‌ها","All statuses"):statusText(v)}</button>)}</div></div>
  <div className="supportCenterGridV1"><Card className="supportInboxV1"><div className="supportPaneTitleV1"><b>{pick("گفتگوها","Conversations")}</b><span>{filtered.length}</span></div><div className="supportTicketListV1">{loading&&tickets.length===0?<div className="runtime-loading">{pick("در حال دریافت گفتگوها...","Loading conversations...")}</div>:filtered.length===0?<div className="runtime-empty">{pick("گفتگویی پیدا نشد.","No conversations found.")}</div>:filtered.map(t=><button type="button" key={t.id} className={`supportTicketV1 ${selected===t.id?"active":""} ${t.status==="open"?"needsReply":""}`} onClick={()=>setSelected(t.id)}><div className="supportTicketTopV1"><span className={`supportSourceDotV1 ${sourceOf(t)}`}>{sourceIcon(t)}</span><div className="grow"><b>{identity(t)}</b><small>{contact(t)}</small></div><time>{dateText(t.last_message_at||t.updated_at)}</time></div><div className="supportTicketSubjectV1"><span>#{t.id}</span><strong>{t.subject||sourceText(t)}</strong></div><div className="supportTicketMetaV1"><Badge tone={statusTone(t.status)}>{statusText(t.status)}</Badge><span>{sourceText(t)}</span></div></button>)}</div></Card>
  <Card className="supportConversationV1">{!selected?<div className="supportBlankV1"><span>💬</span><b>{pick("یک گفتگو را انتخاب کنید","Select a conversation")}</b></div>:detailLoading&&!detail?<div className="runtime-loading">{pick("در حال دریافت پیام‌ها...","Loading messages...")}</div>:detail?<><div className="supportConversationHeadV1"><div className="supportConversationIdentityV1"><span className={`supportSourceAvatarV1 ${sourceOf(detail)}`}>{sourceIcon(detail)}</span><div><h2>{identity(detail)}</h2><p>{contact(detail)}</p><div><span>#{detail.id}</span><span>{sourceText(detail)}</span></div></div></div><div className="supportConversationActionsV1"><Badge tone={statusTone(detail.status)}>{statusText(detail.status)}</Badge><button className="ghost" type="button" onClick={()=>void toggleClosed()}>{detail.status==="closed"?pick("باز کردن","Reopen"):pick("بستن گفتگو","Close")}</button><button className="mini-btn danger" type="button" onClick={()=>void deleteTicket()}>{pick("حذف گفتگو","Delete conversation")}</button></div></div><div className="supportMessagesV1">{(detail.messages||[]).map(m=>{const admin=m.sender_role==="admin";const url=attachmentUrl(m.attachment_ref);return <article key={m.id} className={`supportBubbleV1 supportBubbleV2 ${admin?"admin":"customer"} ${m._pending?"pending":""}`}><div className="supportBubbleMetaV1"><b>{admin?pick("پشتیبانی","Support"):identity(detail)}</b><time>{dateText(m.created_at)}</time>{!m._pending&&<button type="button" className="supportMessageDeleteV2" onClick={()=>void deleteMessage(m.id)}>×</button>}</div>{m.message&&<p>{m.message}</p>}{url&&<a className="supportAttachmentV1" href={url} target="_blank" rel="noreferrer"><img src={url} alt=""/></a>}</article>})}<div ref={endRef}/></div><form className="supportComposerV1" onSubmit={submit}>{detail.status==="closed"?<div className="supportClosedV1">{pick("گفتگو بسته است.","Conversation is closed.")}</div>:<><textarea value={reply} onChange={e=>setReply(e.target.value)} placeholder={pick("پاسخ...","Reply...")} rows={2}/>{preview&&<div className="supportChatImagePreview compact"><img src={preview} alt=""/><button type="button" onClick={clearImage}>×</button></div>}<div className="supportComposerActionsV1"><div><button type="button" className="ghost" onClick={()=>setStickerOpen(v=>!v)}>✨ {pick("استیکر","Sticker")}</button>{stickerOpen&&<div className="supportStickerGridV2">{STICKERS.map(s=><button type="button" key={s} onClick={()=>{setStickerOpen(false);void sendText(s);}}>{s}</button>)}</div>}<button type="button" className="ghost" onClick={()=>fileRef.current?.click()}>📎 {pick("تصویر","Image")}</button></div><button type="submit" className="primary" disabled={!reply.trim()&&!image}>{pick("ارسال","Send")}</button></div></>}</form></>:<div className="runtime-error">{pick("دریافت پیام‌ها ناموفق بود؛ دوباره انتخاب کنید.","Could not load messages; select the conversation again.")}</div>}</Card></div></div></Shell>;
}
