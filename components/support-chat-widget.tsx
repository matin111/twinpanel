"use client";

import {FormEvent,useEffect,useRef,useState} from "react";
import {API_BASE} from "../lib/api";
import {useBranding} from "../lib/branding";
import {useI18n} from "../lib/i18n";

type ChatMessage={
  id:number;
  sender_role:string;
  message:string|null;
  attachment_type?:string|null;
  attachment_ref?:string|null;
  created_at:string;
};

type ChatTicket={
  id:number;
  status:string;
  subject?:string|null;
  messages?:ChatMessage[];
  guest_token?:string;
};

type GuestSession={
  ticketId:number;
  token:string;
  name:string;
  contact:string;
};

type UploadResult={attachment_type:string;attachment_ref:string};
type Props={customerToken?:string|null};

const GUEST_STORAGE_KEY="twinpanel_guest_chat_v1";
const CUSTOMER_TOKEN_KEY="twinpanel_customer_token";
const ALLOWED_IMAGES=new Set(["image/jpeg","image/png","image/webp","image/gif"]);
const MAX_IMAGE_BYTES=5*1024*1024;
const CHAT_EMOJIS=["😀","😁","😂","😍","🥰","😊","😉","😎","🤩","🥳","👍","👌","🙏","👏","💜","❤️","🔥","✨","✅","💯","🎉","🚀","📌","🤝"];

function loadGuestSession():GuestSession|null{
  try{
    const raw=window.localStorage.getItem(GUEST_STORAGE_KEY);
    if(!raw)return null;
    const parsed=JSON.parse(raw) as GuestSession;
    return parsed.ticketId&&parsed.token?parsed:null;
  }catch{return null;}
}
function saveGuestSession(value:GuestSession){try{window.localStorage.setItem(GUEST_STORAGE_KEY,JSON.stringify(value));}catch{}}
function clearGuestSession(){try{window.localStorage.removeItem(GUEST_STORAGE_KEY);}catch{}}

async function chatApi<T>(path:string,options:RequestInit={},customerToken?:string|null):Promise<T>{
  if(!API_BASE)throw new Error("NEXT_PUBLIC_API_BASE تنظیم نشده");
  const headers=new Headers(options.headers);
  if(options.body&&!headers.has("Content-Type")&&!(options.body instanceof FormData))headers.set("Content-Type","application/json");
  if(customerToken)headers.set("Authorization",`Bearer ${customerToken}`);
  const response=await fetch(`${API_BASE}${path}`,{...options,headers,cache:"no-store"});
  if(!response.ok){
    let message="ارتباط با پشتیبانی ناموفق بود";
    try{const payload=await response.json() as {detail?:string;message?:string};message=payload.detail??payload.message??message;}catch{}
    throw new Error(message);
  }
  if(response.status===204)return undefined as T;
  return response.json() as Promise<T>;
}

function attachmentUrl(value?:string|null){
  if(!value)return "";
  if(value.startsWith("http://")||value.startsWith("https://"))return value;
  return `${API_BASE}${value.startsWith("/")?value:`/v1/support/files/${encodeURIComponent(value)}`}`;
}

export function SupportChatWidget({customerToken}:Props){
  const {pick}=useI18n();
  const {brand}=useBranding();
  const [visible,setVisible]=useState(false);
  const [open,setOpen]=useState(false);
  const [emojiOpen,setEmojiOpen]=useState(false);
  const [resolvedToken,setResolvedToken]=useState<string|null>(customerToken??null);
  const [ticket,setTicket]=useState<ChatTicket|null>(null);
  const [guestSession,setGuestSession]=useState<GuestSession|null>(null);
  const [name,setName]=useState("");
  const [contact,setContact]=useState("");
  const [draft,setDraft]=useState("");
  const [loading,setLoading]=useState(false);
  const [sending,setSending]=useState(false);
  const [initialized,setInitialized]=useState(false);
  const [error,setError]=useState("");
  const [image,setImage]=useState<File|null>(null);
  const [preview,setPreview]=useState("");
  const fileRef=useRef<HTMLInputElement|null>(null);
  const messagesEndRef=useRef<HTMLDivElement|null>(null);

  useEffect(()=>{
    const path=window.location.pathname.replace(/\/$/,"")||"/";
    setVisible(path==="/"||path==="/store"||path==="/panel"||path.startsWith("/panel/"));
    if(customerToken!==undefined){setResolvedToken(customerToken||null);return;}
    try{setResolvedToken(window.sessionStorage.getItem(CUSTOMER_TOKEN_KEY)||null);}catch{setResolvedToken(null);}
  },[customerToken]);

  const scrollBottom=()=>window.setTimeout(()=>messagesEndRef.current?.scrollIntoView({behavior:"smooth",block:"end"}),50);
  const addEmoji=(emoji:string)=>{setDraft(value=>value+emoji);setEmojiOpen(false);};

  const refresh=async(silent=false)=>{
    if(!visible)return;
    if(!silent)setLoading(true);
    try{
      if(!silent)setError("");
      if(resolvedToken){
        const rows=await chatApi<ChatTicket[]>("/v1/support/tickets/me",{},resolvedToken);
        const current=rows.find(item=>item.status!=="closed")??null;
        if(!current){setTicket(null);setInitialized(true);return;}
        const detail=await chatApi<ChatTicket>(`/v1/support/tickets/${current.id}`,{},resolvedToken);
        setTicket(detail);setInitialized(true);if(!silent)scrollBottom();return;
      }
      const saved=loadGuestSession();
      if(!saved){setGuestSession(null);setTicket(null);setInitialized(true);return;}
      setGuestSession(saved);setName(saved.name||"");setContact(saved.contact||"");
      try{
        const detail=await chatApi<ChatTicket>(`/v1/support/guest/tickets/${saved.ticketId}`,{headers:{"X-Guest-Chat-Token":saved.token}});
        setTicket(detail);setInitialized(true);if(!silent)scrollBottom();
      }catch{clearGuestSession();setGuestSession(null);setTicket(null);setInitialized(true);}
    }catch(reason){if(!silent)setError(reason instanceof Error?reason.message:pick("دریافت گفتگو ناموفق بود","Could not load chat"));}
    finally{if(!silent)setLoading(false);}
  };

  useEffect(()=>{if(open&&visible)void refresh();},[open,visible,resolvedToken]);
  useEffect(()=>{
    if(!open||!visible||!ticket)return;
    const timer=window.setInterval(()=>void refresh(true),3000);
    return()=>window.clearInterval(timer);
  },[open,visible,ticket?.id,resolvedToken,guestSession?.token]);
  useEffect(()=>{if(open&&ticket?.messages?.length)scrollBottom();},[open,ticket?.messages?.length]);
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview);},[preview]);

  const resetImage=()=>{
    if(preview)URL.revokeObjectURL(preview);
    setImage(null);setPreview("");if(fileRef.current)fileRef.current.value="";
  };
  const pickImage=(file?:File|null)=>{
    if(!file)return;
    if(!ALLOWED_IMAGES.has(file.type)){setError(pick("فرمت تصویر باید JPG، PNG، WebP یا GIF باشد","Image must be JPG, PNG, WebP or GIF"));return;}
    if(file.size>MAX_IMAGE_BYTES){setError(pick("حداکثر حجم تصویر ۵ مگابایت است","Maximum image size is 5 MB"));return;}
    if(preview)URL.revokeObjectURL(preview);
    setImage(file);setPreview(URL.createObjectURL(file));setError("");
  };

  const uploadImage=async(ticketId:number,session:GuestSession|null)=>{
    if(!image)return null;
    const form=new FormData();form.append("file",image);
    const headers=new Headers();let path="";
    if(resolvedToken){headers.set("Authorization",`Bearer ${resolvedToken}`);path=`/v1/support/tickets/${ticketId}/upload-image`;}
    else{
      if(!session)throw new Error(pick("شناسه گفتگو پیدا نشد","Chat session not found"));
      headers.set("X-Guest-Chat-Token",session.token);path=`/v1/support/guest/tickets/${ticketId}/upload-image`;
    }
    if(!API_BASE)throw new Error("NEXT_PUBLIC_API_BASE تنظیم نشده");
    const response=await fetch(`${API_BASE}${path}`,{method:"POST",headers,body:form,cache:"no-store"});
    if(!response.ok){let message=pick("آپلود تصویر ناموفق بود","Image upload failed");try{message=(await response.json()).detail||message;}catch{}throw new Error(message);}
    return response.json() as Promise<UploadResult>;
  };

  const sendAttachmentMessage=async(ticketId:number,session:GuestSession|null)=>{
    const uploaded=await uploadImage(ticketId,session);
    if(!uploaded)return null;
    const payload={message:null,attachment_type:uploaded.attachment_type,attachment_ref:uploaded.attachment_ref};
    if(resolvedToken)return chatApi<ChatTicket>(`/v1/support/tickets/${ticketId}/messages`,{method:"POST",body:JSON.stringify(payload)},resolvedToken);
    if(!session)throw new Error(pick("شناسه گفتگو پیدا نشد","Chat session not found"));
    return chatApi<ChatTicket>(`/v1/support/guest/tickets/${ticketId}/messages`,{method:"POST",headers:{"X-Guest-Chat-Token":session.token},body:JSON.stringify(payload)});
  };

  const startChat=async(event:FormEvent)=>{
    event.preventDefault();if(sending)return;
    const text=draft.trim();if(!text&&!image)return;
    if(!resolvedToken&&(name.trim().length<2||contact.trim().length<3)){setError(pick("نام و راه ارتباطی را وارد کنید","Enter your name and contact"));return;}
    setSending(true);setError("");setEmojiOpen(false);
    try{
      const first=text||pick("📷 تصویر پیوست شد","📷 Image attached");
      if(resolvedToken){
        let created=await chatApi<ChatTicket>("/v1/support/tickets",{method:"POST",body:JSON.stringify({category:"other",subject:pick("گفتگوی آنلاین","Live chat"),message:first})},resolvedToken);
        if(image){const next=await sendAttachmentMessage(created.id,null);if(next)created=next;}
        setTicket(created);setDraft("");resetImage();scrollBottom();return;
      }
      let created=await chatApi<ChatTicket>("/v1/support/guest/tickets",{method:"POST",body:JSON.stringify({name:name.trim(),contact:contact.trim(),message:first})});
      if(!created.guest_token||!created.id)throw new Error(pick("ایجاد گفتگو ناموفق بود","Could not start chat"));
      const session={ticketId:created.id,token:created.guest_token,name:name.trim(),contact:contact.trim()};
      saveGuestSession(session);setGuestSession(session);
      if(image){const next=await sendAttachmentMessage(created.id,session);if(next)created=next;}
      setTicket({...created,guest_token:undefined});setDraft("");resetImage();scrollBottom();
    }catch(reason){setError(reason instanceof Error?reason.message:pick("شروع گفتگو ناموفق بود","Could not start chat"));}
    finally{setSending(false);}
  };

  const sendMessage=async(event:FormEvent)=>{
    event.preventDefault();if(sending||!ticket)return;
    const text=draft.trim();if(!text&&!image)return;
    setSending(true);setError("");setEmojiOpen(false);
    try{
      let updated=ticket;const session=guestSession??loadGuestSession();
      if(text){
        if(resolvedToken)updated=await chatApi<ChatTicket>(`/v1/support/tickets/${ticket.id}/messages`,{method:"POST",body:JSON.stringify({message:text})},resolvedToken);
        else{
          if(!session)throw new Error(pick("شناسه گفتگو پیدا نشد","Chat session not found"));
          updated=await chatApi<ChatTicket>(`/v1/support/guest/tickets/${ticket.id}/messages`,{method:"POST",headers:{"X-Guest-Chat-Token":session.token},body:JSON.stringify({message:text})});
        }
      }
      if(image){const next=await sendAttachmentMessage(ticket.id,session);if(next)updated=next;}
      setTicket(updated);setDraft("");resetImage();scrollBottom();
    }catch(reason){setError(reason instanceof Error?reason.message:pick("ارسال پیام ناموفق بود","Could not send message"));}
    finally{setSending(false);}
  };

  const emojiPicker=<div className="supportEmojiRootV3">
    <button type="button" className="supportEmojiButtonV3" title={pick("ایموجی","Emoji")} onClick={()=>setEmojiOpen(value=>!value)}>☺</button>
    {emojiOpen&&<div className="supportEmojiPickerV3">{CHAT_EMOJIS.map(emoji=><button key={emoji} type="button" onClick={()=>addEmoji(emoji)}>{emoji}</button>)}</div>}
  </div>;

  if(!visible)return null;
  const messages=ticket?.messages??[];

  return <div className="supportChatRoot">
    <input ref={fileRef} type="file" hidden accept="image/jpeg,image/png,image/webp,image/gif" onChange={e=>pickImage(e.target.files?.[0])}/>
    {open&&<section className="supportChatWindow" aria-label={pick("پشتیبانی آنلاین","Live support")}>
      <header className="supportChatHeader"><div className="supportChatHeaderInfo"><span className="supportChatStatus"/><div><b>{pick("پشتیبانی آنلاین","Live support")}</b><small>{brand.name}</small></div></div><button type="button" className="supportChatClose" onClick={()=>{setOpen(false);setEmojiOpen(false);}}>×</button></header>
      <div className="supportChatBody">
        {loading&&!initialized&&<div className="supportChatState">{pick("در حال دریافت گفتگو...","Loading chat...")}</div>}
        {!loading&&initialized&&!ticket&&<form className="supportChatStart" onSubmit={startChat}>
          <h3>{pick("چطور می‌توانیم کمک کنیم؟","How can we help?")}</h3>
          {!resolvedToken&&<><label><span>{pick("نام","Name")}</span><input value={name} onChange={e=>setName(e.target.value)} placeholder={pick("نام شما","Your name")} maxLength={120} required/></label><label><span>{pick("ایمیل یا شماره تماس","Email or phone")}</span><input dir="ltr" value={contact} onChange={e=>setContact(e.target.value)} placeholder="email@example.com" maxLength={190} required/></label></>}
          <label><span>{pick("پیام","Message")}</span><textarea value={draft} onChange={e=>setDraft(e.target.value)} placeholder={pick("پیام خود را بنویسید...","Write your message...")} rows={4} maxLength={10000}/></label>
          {preview&&<div className="supportChatImagePreview"><img src={preview} alt=""/><button type="button" onClick={resetImage}>×</button></div>}
          <div className="supportChatStartTools"><div className="supportChatToolRow">{emojiPicker}<button type="button" className="supportChatAttach" onClick={()=>fileRef.current?.click()}>📎 {pick("تصویر","Image")}</button></div>{error&&<div className="supportChatError">{error}</div>}</div>
          <button type="submit" className="supportChatPrimary" disabled={sending||(!draft.trim()&&!image)}>{sending?pick("در حال ارسال...","Sending..."):pick("شروع گفتگو","Start chat")}</button>
        </form>}
        {ticket&&<>
          <div className="supportChatMessages">{messages.length===0&&<div className="supportChatState">{pick("هنوز پیامی ثبت نشده است.","No messages yet.")}</div>}{messages.map(item=>{const own=item.sender_role==="user"||item.sender_role==="guest";return <article key={item.id} className={own?"supportChatMessage own":"supportChatMessage admin"}><small>{own?pick("شما","You"):pick("پشتیبانی","Support")}</small>{item.message&&<p>{item.message}</p>}{item.attachment_ref&&<a href={attachmentUrl(item.attachment_ref)} target="_blank" rel="noreferrer"><img className="supportChatImage" src={attachmentUrl(item.attachment_ref)} alt={pick("تصویر پیوست","Attachment")}/></a>}<time>{new Date(item.created_at).toLocaleTimeString(undefined,{hour:"2-digit",minute:"2-digit"})}</time></article>})}<div ref={messagesEndRef}/></div>
          <form className="supportChatComposer" onSubmit={sendMessage}>
            {preview&&<div className="supportChatImagePreview compact"><img src={preview} alt=""/><button type="button" onClick={resetImage}>×</button></div>}
            {error&&<div className="supportChatError">{error}</div>}
            <div>{emojiPicker}<button type="button" className="supportChatAttach" onClick={()=>fileRef.current?.click()}>📎</button><textarea value={draft} onChange={e=>setDraft(e.target.value)} placeholder={pick("پیام...","Message...")} rows={1} maxLength={10000}/><button className="supportChatSend" type="submit" disabled={sending||(!draft.trim()&&!image)}>{sending?"…":pick("ارسال","Send")}</button></div>
          </form>
        </>}
      </div>
    </section>}
    <button type="button" className={open?"supportChatLauncher active":"supportChatLauncher"} onClick={()=>{setOpen(value=>!value);setEmojiOpen(false);}} aria-label={pick("پشتیبانی آنلاین","Live support")}><span className="supportChatLauncherIcon">{open?"×":"✦"}</span>{!open&&<span><b>{pick("پشتیبانی آنلاین","Live support")}</b><small>{pick("گفتگو با پشتیبانی","Chat with support")}</small></span>}</button>
  </div>;
}
