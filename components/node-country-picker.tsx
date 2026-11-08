"use client";

import {useEffect,useId,useMemo,useRef,useState} from "react";

const CODES="AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW".split(" ");
const CODE_SET=new Set(CODES);
const displayName=(code:string,locale:string)=>{
  try{return new Intl.DisplayNames([locale],{type:"region"}).of(code)||code;}
  catch{return code;}
};
export const normalizeNodeCountry=(raw:string)=>String(raw||"").trim().toUpperCase()==="UK"?"GB":String(raw||"").trim().toUpperCase();
export const isSupportedNodeCountry=(raw:string)=>CODE_SET.has(normalizeNodeCountry(raw));
export const nodeCountryFlag=(raw:string)=>{
  const code=normalizeNodeCountry(raw);
  return CODE_SET.has(code)?[...code].map(c=>String.fromCodePoint(127397+c.charCodeAt(0))).join(""):"🌐";
};


const normalizedQuery=(text:string)=>text.trim().toLocaleLowerCase()
  .replace(/[يى]/g,"ی").replace(/ك/g,"ک").replace(/[\u064B-\u065F\u200C]/g,"")
  .replace(/\s+/g," ");
const displayCountry=(code:string,language:"fa"|"en")=>displayName(code,language);
type Country={code:string;name:string;english:string;flag:string};

export function NodeCountryPicker({
  value,onChange,disabled=false,language="fa",label,
}:{value:string;onChange:(value:string)=>void;disabled?:boolean;language?:"fa"|"en";label?:string}){
  const [search,setSearch]=useState("");
  const [expanded,setExpanded]=useState(false);
  const [highlight,setHighlight]=useState(0);
  const outer=useRef<HTMLDivElement>(null);
  const searchRef=useRef<HTMLInputElement>(null);
  const listId=useId();
  const active=normalizeNodeCountry(value);
  const all=useMemo<Country[]>(()=>CODES.map(code=>({
    code,name:displayCountry(code,language),english:displayName(code,"en"),flag:nodeCountryFlag(code),
  })).sort((a,b)=>a.name.localeCompare(b.name,language)),[language]);
  const selected=all.find(c=>c.code===active);
  const matches=useMemo(()=>{
    const query=normalizedQuery(search);
    if(!query)return all;
    return all.filter(c=>{
      const terms=[c.code,c.name,c.english,c.code==="GB"?"UK United Kingdom Britain انگلیس بریتانیا":"",
      c.code==="NL"?"Netherlands Holland هلند":""].map(normalizedQuery);
      return terms.some(term=>term.includes(query));
    }).sort((a,b)=>{
      const score=(c:Country)=>c.code.toLowerCase()===query?0:c.code.toLowerCase().startsWith(query)?1:
        normalizedQuery(c.name).startsWith(query)||normalizedQuery(c.english).startsWith(query)?2:3;
      return score(a)-score(b)||a.name.localeCompare(b.name,language);
    });
  },[all,search,language]);
  const visible=matches.slice(0,250);
  const choose=(code:string)=>{
    onChange(code);
    setSearch("");setExpanded(false);setHighlight(0);
  };
  const open=()=>{
    if(disabled)return;
    setExpanded(true);setHighlight(0);
    requestAnimationFrame(()=>searchRef.current?.focus());
  };
  useEffect(()=>{
    if(!expanded)return;
    const outside=(event:PointerEvent)=>{
      if(outer.current&&!outer.current.contains(event.target as Node))setExpanded(false);
    };
    document.addEventListener("pointerdown",outside);
    return()=>document.removeEventListener("pointerdown",outside);
  },[expanded]);
  return <div className="tp-country-picker" ref={outer}>
    <style>{`
      .tp-country-picker{position:relative;min-width:0;display:flex;flex-direction:column;gap:7px;text-align:start}
      .tp-country-picker .tp-country-label{font-size:12px;font-weight:700;color:var(--muted,#9caac2)}
      .tp-country-trigger{display:flex!important;width:100%;height:44px!important;min-height:44px!important;align-items:center;gap:10px;
        border:1px solid #34435e!important;border-radius:12px!important;background:linear-gradient(115deg,#151f33,#10192b)!important;
        padding:7px 12px!important;color:#e7efff!important;text-align:start!important;cursor:pointer;transition:border-color .15s,box-shadow .15s}
      .tp-country-trigger:hover,.tp-country-trigger[aria-expanded="true"]{border-color:#5689f2!important;box-shadow:0 0 0 3px rgba(50,113,240,.13)}
      .tp-country-trigger:disabled{opacity:.6;cursor:not-allowed}
      .tp-country-flag{font-size:23px;line-height:1;flex:none}
      .tp-country-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px;font-weight:750}
      .tp-country-code{font:600 11px ui-monospace,monospace;color:#9fb2d0;direction:ltr}
      .tp-country-arrow{color:#9fb2d0;font-size:12px}
      .tp-country-popover{position:relative;z-index:30;background:#121d31;border:1px solid #345179;border-radius:13px;
        box-shadow:0 14px 28px rgba(0,0,0,.25);padding:9px;display:grid;gap:8px;max-width:100%}
      .tp-country-search{width:100%!important;min-height:39px!important;height:39px!important;border:1px solid #3c506d!important;
        border-radius:9px!important;background:#0c1628!important;color:#eaf1ff!important;padding:8px 11px!important;outline:none}
      .tp-country-search:focus{border-color:#4f8bff!important;box-shadow:0 0 0 2px rgba(64,120,252,.16)}
      .tp-country-results{display:grid;gap:2px;max-height:204px;overflow:auto;overscroll-behavior:contain;padding:2px;scrollbar-width:thin}
      .tp-country-option{display:flex!important;align-items:center;gap:10px;width:100%;border:0!important;border-radius:9px!important;
        min-height:39px!important;padding:6px 9px!important;background:transparent!important;color:#dbe7fa!important;
        cursor:pointer;text-align:start!important}
      .tp-country-option:hover,.tp-country-option.is-highlighted{background:#223657!important}
      .tp-country-option.is-selected{color:#8ebaff!important}
      .tp-country-result-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}
      .tp-country-empty{padding:18px 8px;text-align:center;color:#b4c3db;font-size:12px}
      .tp-country-hint{color:#91a5c3;font-size:11px}
      html[data-theme="light"] .tp-country-trigger{background:#fff!important;color:#23314b!important;border-color:#ccd8e7!important}
      html[data-theme="light"] .tp-country-popover{background:#fff;border-color:#ccdaf1}
      html[data-theme="light"] .tp-country-search{background:#f4f7fd!important;color:#1a2a43!important}
      html[data-theme="light"] .tp-country-option{color:#203352!important}
      html[data-theme="light"] .tp-country-option:hover,html[data-theme="light"] .tp-country-option.is-highlighted{background:#e9f1ff!important}
    `}</style>
    <span className="tp-country-label">{label||(language==="fa"?"کشور سرور":"Server country")}</span>
    <button type="button" className="tp-country-trigger" disabled={disabled} aria-haspopup="listbox"
      aria-expanded={expanded} aria-controls={listId} onClick={()=>expanded?setExpanded(false):open()}>
      <span className="tp-country-flag" aria-hidden="true">{selected?.flag||"🌍"}</span>
      <span className="tp-country-name">{selected?.name||(language==="fa"?"انتخاب کشور":"Select country")}</span>
      <span className="tp-country-code">{selected?.code||""}</span>
      <span className="tp-country-arrow" aria-hidden="true">{expanded?"▴":"▾"}</span>
    </button>
    {expanded&&!disabled?<div className="tp-country-popover">
      <input ref={searchRef} className="tp-country-search" role="combobox"
        aria-autocomplete="list" aria-controls={listId} aria-expanded={true}
        aria-label={language==="fa"?"جست‌وجوی کشور":"Search country"}
        placeholder={language==="fa"?"نام یا کد کشور؛ مثل هلند، NL":"Name or code, e.g. Netherlands, NL"}
        value={search} onChange={event=>{setSearch(event.target.value);setHighlight(0);}}
        onKeyDown={event=>{
          if(event.key==="Escape"){event.preventDefault();setExpanded(false);}
          if(event.key==="ArrowDown"){event.preventDefault();setHighlight(i=>Math.min(i+1,visible.length-1));}
          if(event.key==="ArrowUp"){event.preventDefault();setHighlight(i=>Math.max(i-1,0));}
          if(event.key==="Enter"){event.preventDefault();if(visible[highlight])choose(visible[highlight].code);}
        }}/>
      <div id={listId} className="tp-country-results" role="listbox" aria-label={language==="fa"?"نتایج کشور":"Countries"}>
        {visible.length?visible.map((country,i)=><button type="button" role="option"
          aria-selected={country.code===active} key={country.code}
          className={"tp-country-option"+(i===highlight?" is-highlighted":"")+(country.code===active?" is-selected":"")}
          onMouseEnter={()=>setHighlight(i)} onClick={()=>choose(country.code)}>
          <span className="tp-country-flag" aria-hidden="true">{country.flag}</span>
          <span className="tp-country-result-name">{country.name}</span>
          <span className="tp-country-code">{country.code}</span>
          {country.code===active?<span aria-hidden="true">✓</span>:null}
        </button>):<div className="tp-country-empty">{language==="fa"?"کشوری با این عبارت پیدا نشد":"No matching country found"}</div>}
      </div>
      <small className="tp-country-hint">{language==="fa"?"برای انتخاب Enter بزنید یا روی کشور کلیک کنید":"Press Enter or click to select"} · {matches.length}</small>
    </div>:null}
  </div>;
}
