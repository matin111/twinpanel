"use client";

import {FormEvent,useEffect,useRef,useState} from "react";
import {API_BASE} from "../lib/api";
import {useBranding} from "../lib/branding";
import {useI18n} from "../lib/i18n";
import {playNotificationSound,primeNotificationSound} from "../lib/notification-sound";

type ChatMessage={id:number;sender_role:string;message:string|null;attachment_type?:string|null;attachment_ref?:string|null;created_at:string;_pending?:boolean};
type ChatTicket={id:number;status:string;subject?:string|null;messages?:ChatMessage[];guest_token?:string};
type GuestSession={ticketId:number;token:string;name:string;contact:string};
type UploadResult={attachment_type:string;attachment_ref:string};
type Props={customerToken?:string|null};

const GUEST_STORAGE_KEY="twinpanel_guest_chat_v2";
const GUEST_SESSION_BACKUP_KEY="twinpanel_guest_chat_session_v2";
const GUEST_COOKIE_KEY="twinpanel_guest_chat";
const GUEST_TICKET_CACHE_KEY="twinpanel_guest_chat_ticket_v2";
const CHAT_OPEN_KEY="twinpanel_guest_chat_open_v2";
const CUSTOMER_TOKEN_KEY="twinpanel_customer_token";
const ALLOWED_IMAGES=new Set(["image/jpeg","image/png","image/webp","image/gif"]);
const MAX_IMAGE_BYTES=5*1024*1024;
const CHAT_EMOJIS=["😀","😁","😂","😍","🥰","😊","😉","😎","🤩","🥳","👍","👌","🙏","👏","💜","❤️","🔥","✨","✅","💯","🎉","🚀","📌","🤝"];
const STICKERS=["👍","❤️","🙏","😊","😂","🎉","✅","🔥","💜","👋","⭐","🤝","😍","👏","💯","🚀"];

class ChatApiError extends Error{status:number;constructor(message:string,status:number){super(message);this.name="ChatApiError";this.status=status;}}

function parseSession(raw:string|null):GuestSession|null{
  if(!raw)return null;
  try{
    const value=JSON.parse(raw) as Partial<GuestSession>;
    const ticketId=Number(value.ticketId||0);const token=String(value.token||"").trim();
    if(!ticketId||!token)return null;
    return {ticketId,token,name:String(value.name||""),contact:String(value.contact||"")};
  }catch{return null;}
}
function cookieValue(){
  if(typeof document==="undefined")return null;
  const prefix=`${GUEST_COOKIE_KEY}=`;
  const row=document.cookie.split(";").map(x=>x.trim()).find(x=>x.startsWith(prefix));
  if(!row)return null;
  try{return decodeURIComponent(row.slice(prefix.length));}catch{return null;}
}
function loadGuestSession():GuestSession|null{
  if(typeof window==="undefined")return null;
  try{const row=parseSession(localStorage.getItem(GUEST_STORAGE_KEY));if(row)return row;}catch{}
  try{const row=parseSession(sessionStorage.getItem(GUEST_SESSION_BACKUP_KEY));if(row)return row;}catch{}
  return parseSession(cookieValue());
}
function saveGuestSession(value:GuestSession){
  if(typeof window==="undefined")return;
  const raw=JSON.stringify(value);
  try{localStorage.setItem(GUEST_STORAGE_KEY,raw);}catch{}
  try{sessionStorage.setItem(GUEST_SESSION_BACKUP_KEY,raw);}catch{}
  try{document.cookie=`${GUEST_COOKIE_KEY}=${encodeURIComponent(raw)}; Max-Age=31536000; Path=/; SameSite=Lax`;}catch{}
}
function clearGuestSession(){
  try{localStorage.removeItem(GUEST_STORAGE_KEY);localStorage.removeItem(GUEST_TICKET_CACHE_KEY);localStorage.removeItem(CHAT_OPEN_KEY);}catch{}
  try{sessionStorage.removeItem(GUEST_SESSION_BACKUP_KEY);}catch{}
  try{document.cookie=`${GUEST_COOKIE_KEY}=; Max-Age=0; Path=/; SameSite=Lax`;}catch{}
}
function loadCachedTicket(session:GuestSession|null):ChatTicket|null{
  if(!session||typeof window==="undefined")return null;
  try{const row=JSON.parse(localStorage.getItem(GUEST_TICKET_CACHE_KEY)||"null") as ChatTicket|null;return row&&Number(row.id)===session.ticketId?row:null;}catch{return null;}
}
function saveCachedTicket(ticket:ChatTicket|null){if(!ticket||typeof window==="undefined")return;try{localStorage.setItem(GUEST_TICKET_CACHE_KEY,JSON.stringify(ticket));}catch{}}

async function chatApi<T>(path:string,options:RequestInit={},customerToken?:string|null):Promise<T>{
  if(!API_BASE)throw new Error("NEXT_PUBLIC_API_BASE is not configured");
  const headers=new Headers(options.headers);
  if(options.body&&!headers.has("Content-Type")&&!(options.body instanceof Blob)&&!(options.body instanceof FormData))headers.set("Content-Type","application/json");
  if(customerToken)headers.set("Authorization",`Bearer ${customerToken}`);
  const response=await fetch(`${API_BASE}${path}`,{...options,headers,cache:"no-store",signal:options.signal??AbortSignal.timeout(4000)});
  if(!response.ok){let message="Support connection failed";try{const payload=await response.json() as {detail?:string;message?:string};message=payload.detail??payload.message??message;}catch{}throw new ChatApiError(message,response.status);}
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}
function attachmentUrl(value?:string|null){if(!value)return "";if(value.startsWith("http://")||value.startsWith("https://"))return value;return `${API_BASE}${value.startsWith("/")?value:`/v1/support/files/${encodeURIComponent(value)}`}`;}
function maxAdminMessageId(ticket:ChatTicket|null){return Math.max(0,...(ticket?.messages||[]).filter(x=>String(x.sender_role).toLowerCase()==="admin").map(x=>Number(x.id)||0));}

export function SupportChatWidgetV2({customerToken}:Props){
  const {pick}=useI18n();const {brand}=useBranding();
  const [visible,setVisible]=useState(false);const [open,setOpen]=useState(false);const [initialized,setInitialized]=useState(false);
  const [emojiOpen,setEmojiOpen]=useState(false);const [stickerOpen,setStickerOpen]=useState(false);
  const [resolvedToken,setResolvedToken]=useState<string|null>(customerToken??null);const [guestSession,setGuestSession]=useState<GuestSession|null>(null);
  const [ticket,setTicket]=useState<ChatTicket|null>(null);const [name,setName]=useState("");const [contact,setContact]=useState("");const [draft,setDraft]=useState("");
  const [loading,setLoading]=useState(false);const [sending,setSending]=useState(false);const [error,setError]=useState("");const [image,setImage]=useState<File|null>(null);const [preview,setPreview]=useState("");
  const fileRef=useRef<HTMLInputElement|null>(null);const endRef=useRef<HTMLDivElement|null>(null);const refreshBusy=useRef(false);const lastAdminMessage=useRef(0);const soundReady=useRef(false);

  useEffect(()=>{
    const path=window.location.pathname.replace(/\/$/,"")||"/";setVisible(path==="/"||path==="/store"||path==="/panel"||path.startsWith("/panel/"));
    const saved=loadGuestSession();if(saved){setGuestSession(saved);setName(saved.name);setContact(saved.contact);const cached=loadCachedTicket(saved);if(cached){setTicket(cached);lastAdminMessage.current=maxAdminMessageId(cached);}setInitialized(true);}
    try{if(localStorage.getItem(CHAT_OPEN_KEY)==="1")setOpen(true);}catch{}
    if(customerToken!==undefined)setResolvedToken(customerToken||null);else{try{setResolvedToken(sessionStorage.getItem(CUSTOMER_TOKEN_KEY)||null);}catch{setResolvedToken(null);}}
    const prime=()=>{void primeNotificationSound();soundReady.current=true;};window.addEventListener("pointerdown",prime,{once:true});window.addEventListener("keydown",prime,{once:true});
    return()=>{window.removeEventListener("pointerdown",prime);window.removeEventListener("keydown",prime);};
  },[customerToken]);

  const scrollBottom=()=>window.setTimeout(()=>endRef.current?.scrollIntoView({behavior:"smooth",block:"end"}),20);
  const applyTicket=(next:ChatTicket,play=true)=>{
    const nextAdmin=maxAdminMessageId(next);if(play&&lastAdminMessage.current>0&&nextAdmin>lastAdminMessage.current&&soundReady.current)void playNotificationSound("message");
    lastAdminMessage.current=Math.max(lastAdminMessage.current,nextAdmin);setTicket(next);if(!resolvedToken)saveCachedTicket(next);setInitialized(true);
  };

  const refresh=async(silent=false)=>{
    if(!visible||refreshBusy.current)return;refreshBusy.current=true;if(!silent)setLoading(true);
    try{
      if(resolvedToken){const rows=await chatApi<ChatTicket[]>("/v1/support/tickets/me",{},resolvedToken);const current=rows.find(x=>x.status!=="closed")??rows[0]??null;if(!current){setTicket(null);setInitialized(true);return;}applyTicket(await chatApi<ChatTicket>(`/v1/support/tickets/${current.id}`,{},resolvedToken),silent);}
      else{
        const saved=guestSession??loadGuestSession();if(!saved){setInitialized(true);return;}setGuestSession(saved);setName(saved.name);setContact(saved.contact);
        try{const detail=await chatApi<ChatTicket>(`/v1/support/guest/tickets/${saved.ticketId}`,{headers:{"X-Guest-Chat-Token":saved.token}});saveGuestSession(saved);applyTicket(detail,true);setError("");}
        catch(reason){if(!silent)setError(reason instanceof Error?reason.message:pick("ارتباط موقتاً برقرار نشد؛ گفتگوی قبلی حفظ شده است.","Connection is temporarily unavailable; your previous chat is preserved."));setInitialized(true);}
      }
    }catch(reason){if(!silent)setError(reason instanceof Error?reason.message:pick("دریافت گفتگو ناموفق بود","Could not load chat"));setInitialized(true);}
    finally{refreshBusy.current=false;if(!silent)setLoading(false);}
  };

  useEffect(()=>{if(open&&visible)void refresh(false);},[open,visible,resolvedToken]);
  useEffect(()=>{if(!open||!visible||!ticket)return;const timer=window.setInterval(()=>{if(document.visibilityState==="visible")void refresh(true);},500);return()=>window.clearInterval(timer);},[open,visible,ticket?.id,resolvedToken,guestSession?.token]);
  useEffect(()=>{if(open&&ticket?.messages?.length)scrollBottom();},[open,ticket?.messages?.length]);
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview);},[preview]);

  const setOpenPersist=(value:boolean)=>{setOpen(value);try{localStorage.setItem(CHAT_OPEN_KEY,value?"1":"0");}catch{}if(value)void primeNotificationSound();};
  const resetConversation=()=>{if(!window.confirm(pick("گفتگوی ذخیره‌شده پاک شود و گفتگوی جدید شروع شود؟","Clear the saved conversation and start a new one?")))return;clearGuestSession();setGuestSession(null);setTicket(null);setInitialized(true);setError("");setName("");setContact("");lastAdminMessage.current=0;};
  const resetImage=()=>{if(preview)URL.revokeObjectURL(preview);setImage(null);setPreview("");if(fileRef.current)fileRef.current.value="";};
  const pickImage=(file?:File|null)=>{if(!file)return;if(!ALLOWED_IMAGES.has(file.type)){setError(pick("فرمت تصویر باید JPG، PNG، WebP یا GIF باشد","Image must be JPG, PNG, WebP or GIF"));return;}if(file.size>MAX_IMAGE_BYTES){setError(pick("حداکثر حجم تصویر ۵ مگابایت است","Maximum image size is 5 MB"));return;}if(preview)URL.revokeObjectURL(preview);setImage(file);setPreview(URL.createObjectURL(file));setError("");};
  const uploadImage=async(ticketId:number,session:GuestSession|null)=>{if(!image)return null;const headers=new Headers({"Content-Type":image.type||"application/octet-stream"});let path="";if(resolvedToken){headers.set("Authorization",`Bearer ${resolvedToken}`);path=`/v1/support/tickets/${ticketId}/upload-image`;}else{if(!session)throw new Error("CHAT_SESSION_MISSING");headers.set("X-Guest-Chat-Token",session.token);path=`/v1/support/guest/tickets/${ticketId}/upload-image`;}const response=await fetch(`${API_BASE}${path}`,{method:"POST",headers,body:image,cache:"no-store",signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error(pick("آپلود تصویر ناموفق بود","Image upload failed"));return response.json() as Promise<UploadResult>;};
  const sendAttachment=async(ticketId:number,session:GuestSession|null)=>{const uploaded=await uploadImage(ticketId,session);if(!uploaded)return null;const payload={message:null,attachment_type:uploaded.attachment_type,attachment_ref:uploaded.attachment_ref};if(resolvedToken)return chatApi<ChatTicket>(`/v1/support/tickets/${ticketId}/messages`,{method:"POST",body:JSON.stringify(payload)},resolvedToken);if(!session)throw new Error("CHAT_SESSION_MISSING");return chatApi<ChatTicket>(`/v1/support/guest/tickets/${ticketId}/messages`,{method:"POST",headers:{"X-Guest-Chat-Token":session.token},body:JSON.stringify(payload)});};

  const startChat=async(event:FormEvent)=>{event.preventDefault();if(sending)return;const text=draft.trim();if(!text&&!image)return;if(!resolvedToken&&(name.trim().length<2||contact.trim().length<3)){setError(pick("نام و راه ارتباطی را وارد کنید","Enter your name and contact"));return;}setSending(true);setError("");try{const first=text||pick("📷 تصویر پیوست شد","📷 Image attached");if(resolvedToken){let created=await chatApi<ChatTicket>("/v1/support/tickets",{method:"POST",body:JSON.stringify({category:"other",subject:pick("گفتگوی آنلاین","Live chat"),message:first})},resolvedToken);if(image){const next=await sendAttachment(created.id,null);if(next)created=next;}applyTicket(created,false);setDraft("");resetImage();scrollBottom();return;}let created=await chatApi<ChatTicket>("/v1/support/guest/tickets",{method:"POST",body:JSON.stringify({name:name.trim(),contact:contact.trim(),message:first,source:"web"})});if(!created.guest_token||!created.id)throw new Error("CHAT_CREATE_FAILED");const session={ticketId:created.id,token:created.guest_token,name:name.trim(),contact:contact.trim()};saveGuestSession(session);setGuestSession(session);if(image){const next=await sendAttachment(created.id,session);if(next)created=next;}const clean={...created,guest_token:undefined};applyTicket(clean,false);setDraft("");resetImage();scrollBottom();}catch(reason){setError(reason instanceof Error?reason.message:pick("شروع گفتگو ناموفق بود","Could not start chat"));}finally{setSending(false);}};

  const sendText=async(textValue:string)=>{
    if(!ticket||sending)return;

    const text=textValue.trim();

    if(!text)return;

    setSending(true);
    setError("");

    const oldTicket=ticket;

    const temp:ChatMessage={
      id:-Date.now(),
      sender_role:resolvedToken
        ?"user"
        :"guest",
      message:text,
      created_at:new Date().toISOString(),
      _pending:true,
    };

    setTicket(current=>
      current
        ?{
            ...current,
            messages:[
              ...(current.messages||[]),
              temp,
            ],
          }
        :current
    );

    setDraft("");
    scrollBottom();

    try{
      const session=
        guestSession
        ??loadGuestSession();

      let updated:ChatTicket;

      if(resolvedToken){

        updated=await chatApi<ChatTicket>(
          `/v1/support/tickets/${oldTicket.id}/messages`,
          {
            method:"POST",
            body:JSON.stringify({
              message:text,
              source:"web",
            }),
          },
          resolvedToken,
        );

      }else{

        if(!session){
          throw new Error(
            "CHAT_SESSION_MISSING"
          );
        }

        updated=await chatApi<ChatTicket>(
          `/v1/support/guest/tickets/${oldTicket.id}/messages`,
          {
            method:"POST",
            headers:{
              "X-Guest-Chat-Token":
                session.token,
            },
            body:JSON.stringify({
              message:text,
              source:"web",
            }),
          },
        );
      }

      applyTicket(
        updated,
        false,
      );

      setError("");

    }catch(reason){

      // SELF_HEAL_DELETED_V2_TICKET
      if(
        reason instanceof ChatApiError
        && reason.status===404
      ){

        try{

          if(resolvedToken){

            const recreated=
              await chatApi<ChatTicket>(
                "/v1/support/tickets",
                {
                  method:"POST",
                  body:JSON.stringify({
                    category:"other",
                    subject:pick(
                      "گفتگوی آنلاین",
                      "Live chat",
                    ),
                    message:text,
                  }),
                },
                resolvedToken,
              );

            applyTicket(
              recreated,
              false,
            );

            setError("");
            scrollBottom();

            return;
          }

          const session=
            guestSession
            ??loadGuestSession();

          const rememberedName=
            String(
              session?.name
              ||name
              ||""
            ).trim();

          const rememberedContact=
            String(
              session?.contact
              ||contact
              ||""
            ).trim();

          if(
            rememberedName.length<2
            ||rememberedContact.length<3
          ){
            clearGuestSession();

            setGuestSession(null);
            setTicket(null);
            setDraft(text);

            setError(
              pick(
                "گفتگوی قبلی حذف شده بود؛ نام و راه ارتباطی را وارد و پیام را دوباره ارسال کنید.",
                "The previous chat was deleted. Enter your name/contact and send again.",
              )
            );

            return;
          }

          const recreated=
            await chatApi<ChatTicket>(
              "/v1/support/guest/tickets",
              {
                method:"POST",
                body:JSON.stringify({
                  name:rememberedName,
                  contact:rememberedContact,
                  message:text,
                  source:"web",
                }),
              },
            );

          if(
            !recreated.id
            ||!recreated.guest_token
          ){
            throw new Error(
              "CHAT_RECREATE_FAILED"
            );
          }

          const newSession={
            ticketId:recreated.id,
            token:recreated.guest_token,
            name:rememberedName,
            contact:rememberedContact,
          };

          saveGuestSession(
            newSession,
          );

          setGuestSession(
            newSession,
          );

          setName(
            rememberedName,
          );

          setContact(
            rememberedContact,
          );

          const clean={
            ...recreated,
            guest_token:undefined,
          };

          applyTicket(
            clean,
            false,
          );

          setError("");
          scrollBottom();

          return;

        }catch(recreateReason){

          setTicket(
            current=>
              current
                ?{
                    ...current,
                    messages:(
                      current.messages||[]
                    ).filter(
                      item=>
                        item.id!==temp.id
                    ),
                  }
                :current
          );

          setDraft(text);

          setError(
            recreateReason instanceof Error
              ?recreateReason.message
              :pick(
                  "ساخت گفتگوی جدید ناموفق بود",
                  "Could not recreate chat",
                )
          );

          return;
        }
      }

      setTicket(
        current=>
          current
            ?{
                ...current,
                messages:(
                  current.messages||[]
                ).filter(
                  item=>item.id!==temp.id
                ),
              }
            :current
      );

      setDraft(text);

      setError(
        reason instanceof Error
          ?reason.message
          :pick(
              "ارسال پیام ناموفق بود",
              "Could not send message",
            )
      );

    }finally{
      setSending(false);
    }
  };
  const sendMessage=async(event:FormEvent)=>{event.preventDefault();if(!ticket||sending)return;const text=draft.trim();if(!text&&!image)return;if(text&&!image){await sendText(text);return;}setSending(true);setError("");try{let updated=ticket;const session=guestSession??loadGuestSession();if(text){if(resolvedToken)updated=await chatApi<ChatTicket>(`/v1/support/tickets/${ticket.id}/messages`,{method:"POST",body:JSON.stringify({message:text,source:"web"})},resolvedToken);else{if(!session)throw new Error("CHAT_SESSION_MISSING");updated=await chatApi<ChatTicket>(`/v1/support/guest/tickets/${ticket.id}/messages`,{method:"POST",headers:{"X-Guest-Chat-Token":session.token},body:JSON.stringify({message:text,source:"web"})});}}if(image){const next=await sendAttachment(ticket.id,session);if(next)updated=next;}applyTicket(updated,false);setDraft("");resetImage();}catch(reason){setError(reason instanceof Error?reason.message:pick("ارسال پیام ناموفق بود","Could not send message"));}finally{setSending(false);}};

  if(!visible)return null;const messages=ticket?.messages||[];const savedSession=guestSession??loadGuestSession();
  const emojiPicker=<div className="supportEmojiRootV3"><button type="button" className="supportEmojiButtonV3" onClick={()=>{setEmojiOpen(v=>!v);setStickerOpen(false);}}>☺</button>{emojiOpen&&<div className="supportEmojiPickerV3">{CHAT_EMOJIS.map(x=><button type="button" key={x} onClick={()=>{setDraft(v=>v+x);setEmojiOpen(false);}}>{x}</button>)}</div>}</div>;
  const stickerPicker=<div className="supportEmojiRootV3"><button type="button" className="supportEmojiButtonV3" title={pick("استیکر","Sticker")} onClick={()=>{setStickerOpen(v=>!v);setEmojiOpen(false);}}>✨</button>{stickerOpen&&<div className="supportEmojiPickerV3">{STICKERS.map(x=><button type="button" key={x} onClick={()=>{setStickerOpen(false);void sendText(x);}}>{x}</button>)}</div>}</div>;

  return <div className="supportChatRoot"><input ref={fileRef} type="file" hidden accept="image/jpeg,image/png,image/webp,image/gif" onChange={e=>pickImage(e.target.files?.[0])}/>{open&&<section className="supportChatWindow"><header className="supportChatHeader"><div className="supportChatHeaderInfo"><span className="supportChatStatus"/><div><b>{pick("پشتیبانی آنلاین","Live support")}</b><small>{brand.name}</small></div></div><div><button type="button" className="supportChatClose" title={pick("گفتگوی جدید","New chat")} onClick={resetConversation}>↻</button><button type="button" className="supportChatClose" onClick={()=>setOpenPersist(false)}>×</button></div></header><div className="supportChatBody">
    {loading&&!initialized&&<div className="supportChatState">{pick("در حال بازیابی گفتگو...","Restoring chat...")}</div>}
    {initialized&&!ticket&&!savedSession&&<form className="supportChatStart" onSubmit={startChat}><h3>{pick("چطور می‌توانیم کمک کنیم؟","How can we help?")}</h3>{!resolvedToken&&<><label><span>{pick("نام","Name")}</span><input value={name} onChange={e=>setName(e.target.value)} required/></label><label><span>{pick("ایمیل یا شماره تماس","Email or phone")}</span><input dir="ltr" value={contact} onChange={e=>setContact(e.target.value)} required/></label></>}<label><span>{pick("پیام","Message")}</span><textarea value={draft} onChange={e=>setDraft(e.target.value)} rows={4}/></label>{preview&&<div className="supportChatImagePreview"><img src={preview} alt=""/><button type="button" onClick={resetImage}>×</button></div>}<div className="supportChatStartTools"><div className="supportChatToolRow">{emojiPicker}{stickerPicker}<button type="button" className="supportChatAttach" onClick={()=>fileRef.current?.click()}>📎 {pick("تصویر","Image")}</button></div>{error&&<div className="supportChatError">{error}</div>}</div><button type="submit" className="supportChatPrimary" disabled={sending||(!draft.trim()&&!image)}>{sending?pick("در حال ارسال...","Sending..."):pick("شروع گفتگو","Start chat")}</button></form>}
    {initialized&&!ticket&&savedSession&&<div className="supportChatState"><b>{pick("گفتگوی قبلی شما محفوظ است","Your previous chat is preserved")}</b><p>{error||pick("در حال تلاش برای اتصال دوباره...","Trying to reconnect...")}</p><button type="button" className="supportChatPrimary" onClick={()=>void refresh(false)}>{pick("تلاش دوباره","Retry")}</button></div>}
    {ticket&&<><div className="supportChatMessages">{messages.map(item=>{const own=item.sender_role==="user"||item.sender_role==="guest";return <article key={item.id} className={own?"supportChatMessage own":"supportChatMessage admin"}><small>{own?pick("شما","You"):pick("پشتیبانی","Support")}</small>{item.message&&<p>{item.message}</p>}{item.attachment_ref&&<a href={attachmentUrl(item.attachment_ref)} target="_blank" rel="noreferrer"><img className="supportChatImage" src={attachmentUrl(item.attachment_ref)} alt=""/></a>}<time>{new Date(item.created_at).toLocaleTimeString(undefined,{hour:"2-digit",minute:"2-digit"})}</time></article>})}<div ref={endRef}/></div><form className="supportChatComposer" onSubmit={sendMessage}>{preview&&<div className="supportChatImagePreview compact"><img src={preview} alt=""/><button type="button" onClick={resetImage}>×</button></div>}{error&&<div className="supportChatError">{error}</div>}<div>{emojiPicker}{stickerPicker}<button type="button" className="supportChatAttach" onClick={()=>fileRef.current?.click()}>📎</button><textarea value={draft} onChange={e=>setDraft(e.target.value)} placeholder={pick("پیام...","Message...")} rows={1}/><button className="supportChatSend" type="submit" disabled={sending||(!draft.trim()&&!image)}>{sending?"…":pick("ارسال","Send")}</button></div></form></>}
  </div></section>}<button type="button" className={open?"supportChatLauncher active":"supportChatLauncher"} onClick={()=>setOpenPersist(!open)}><span className="supportChatLauncherIcon">{open?"×":"✦"}</span>{!open&&<span><b>{pick("پشتیبانی آنلاین","Live support")}</b><small>{pick("گفتگو با پشتیبانی","Chat with support")}</small></span>}</button></div>;
}
