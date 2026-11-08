"use client";

import {useMemo,useState} from "react";

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

export function NodeCountryPicker({
  value,onChange,disabled=false,language="fa",label,
}:{value:string;onChange:(value:string)=>void;disabled?:boolean;language?:"fa"|"en";label?:string}){
  const [search,setSearch]=useState("");
  const active=normalizeNodeCountry(value);
  const countries=useMemo(()=>{
    const all=CODES.map(code=>({code,name:displayName(code,language)}));
    all.sort((a,b)=>a.name.localeCompare(b.name,language));
    const q=search.trim().toLocaleLowerCase(language);
    const visible=!q?all:all.filter(c=>c.code.toLowerCase().includes(q)||c.name.toLocaleLowerCase(language).includes(q)||displayName(c.code,"en").toLowerCase().includes(q));
    const selected=all.find(c=>c.code===active);
    return selected&&!visible.some(c=>c.code===active)?[selected,...visible]:visible;
  },[active,language,search]);
  return <div style={{display:"grid",gap:7,minWidth:0}}>
    <span>{label||(language==="fa"?"کشور سرور":"Server country")}</span>
    <input
      aria-label={language==="fa"?"جستجوی نام یا کد کشور":"Search country name or code"}
      placeholder={language==="fa"?"جستجوی کشور یا کد، مثل فنلاند یا FI":"Search country, e.g. Finland or FI"}
      value={search} onChange={event=>setSearch(event.target.value)}
      disabled={disabled} autoComplete="off"
      style={{width:"100%"}}
    />
    <select aria-label={language==="fa"?"انتخاب کشور سرور":"Choose server country"}
      required disabled={disabled} value={active} onChange={event=>{onChange(event.target.value);setSearch("");}}
      style={{width:"100%",minHeight:42}}>
      {!active?<option value="">{language==="fa"?"کشور را انتخاب کنید":"Choose a country"}</option>:null}
      {countries.map(c=><option key={c.code} value={c.code}>{nodeCountryFlag(c.code)} {c.name} ({c.code})</option>)}
    </select>
    <small>{nodeCountryFlag(active)} {active?displayName(active,language):language==="fa"?"کشور انتخاب نشده":"No country selected"}</small>
  </div>;
}
