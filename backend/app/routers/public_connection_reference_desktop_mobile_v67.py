from __future__ import annotations

# Reference-driven public Connection dashboard. Presentation layer ONLY.
# No modification to credential or subscription data, backend network endpoints,
# configs, transport, ports, SNI, UUID or URLs.
_MARKER = "TWINPANEL_PUBLIC_CONNECTION_REFERENCE_DESKTOP_MOBILE_V67"

_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECTION_REFERENCE_DESKTOP_MOBILE_V67 */
html[data-theme="dark"] body.ref67 {
  --ref-bg:#090e20;--ref-card:#111b33;--ref-edge:#334164;
  --ref-violet:#7c34ef;--ref-glow:#9846ff;
  background:radial-gradient(ellipse at 85% 8%,#30134f65,transparent 31%),
             radial-gradient(ellipse at 20% 60%,#17204e6b,transparent 44%),#080d1f!important;
  color:#eef2ff;
}
body.ref67 .page{width:min(1280px,95vw)!important;max-width:1280px!important;padding:24px 0 45px!important}
body.ref67 .top{background:#090e1ded!important;border-bottom:1px solid #333052!important}
body.ref67 .topin{height:76px!important;width:min(1300px,95vw)!important}
body.ref67 .brand{gap:12px!important}
body.ref67 .brand b{font-size:24px!important;letter-spacing:-.5px}
body.ref67 .mark{width:44px!important;height:44px!important;border-radius:14px!important;
 background:linear-gradient(145deg,#a254ff,#6421ea)!important;box-shadow:0 8px 22px #7a28fa42}
body.ref67 .top .profile{display:none!important}
body.ref67 .theme{width:42px;height:42px;background:#19213a;border-color:#3a4263;border-radius:50%}
body.ref67 .traffic{padding:16px 20px!important;display:flex!important;align-items:center!important;
 gap:20px!important;border:1px solid #513f97!important;border-radius:24px!important;
 min-height:110px;background:
 radial-gradient(ellipse at 83% 110%,#8229e04b,transparent 37%),
 linear-gradient(105deg,#141c39,#111a32 65%,#251448)!important;box-shadow:0 5px 35px #782dee1a!important}
body.ref67 .traffic .visual{display:none!important}
body.ref67 .traffic .ref67-user{display:flex;align-items:center;gap:13px;min-width:190px;
 border:1px solid #364262;padding:13px 16px;border-radius:20px;background:#151e3b}
body.ref67 .ref67-usericon{width:48px;height:48px;flex:0 0 48px;display:grid;place-items:center;
 border-radius:15px;background:linear-gradient(135deg,#6052fb,#253fd0);color:white;font-size:26px;font-weight:900}
body.ref67 .ref67-user strong{display:block;font-size:20px;line-height:1.4;color:white;direction:ltr}
body.ref67 .ref67-user small{display:block;color:#38ef9c;font-size:12px;font-weight:800;white-space:nowrap}
body.ref67 .traffic .stats{display:grid!important;grid-template-columns:repeat(5,minmax(0,1fr))!important;
 flex:1;gap:0!important;align-items:center}
body.ref67 .traffic .stat{border:0!important;border-inline-end:1px solid #3d476d!important;
 padding:8px 13px!important;min-height:65px;display:flex;flex-direction:column-reverse;justify-content:center;
 gap:5px;text-align:center!important;background:transparent!important}
body.ref67 .traffic .stat:last-child{border:0!important}
body.ref67 .traffic .stat small{color:#bdc6df!important;font-size:11px!important;line-height:1.4!important}
body.ref67 .traffic .stat strong{color:white!important;font-size:18px!important;line-height:1.3!important;
 margin:0!important;font-weight:900!important;font-variant-numeric:tabular-nums}
body.ref67 .traffic .ref67-decoration{display:grid;gap:5px;justify-items:center;flex:0 0 90px;
 transform:perspective(200px) rotateY(-15deg)}
body.ref67 .ref67-decoration i{display:block;width:68px;height:20px;border-radius:7px;
 background:linear-gradient(105deg,#261777,#6543f6 55%,#301a9b);border:1px solid #9267ff;
 box-shadow:6px 5px 0 #1a134c,0 0 18px #8753f367}
body.ref67 .ref67-decoration i:after{content:"●";float:right;margin-inline:9px;color:#6af1fd}
body.ref67 .section-head{margin:14px 0 9px!important}
body.ref67 .section-head h2{display:none!important}
body.ref67 .section-head small,body.ref67 .section-head p{display:none!important}
body.ref67 .smart-card{display:none!important}
body.ref67 .ref67-categories{display:flex;align-items:center;justify-content:flex-end;gap:9px;
 padding:8px 0 13px;border-bottom:1px solid #34385d;margin:0 0 10px}
body.ref67 .ref67-filter{height:42px;padding:0 19px;border:1px solid #293658;border-radius:13px;
 background:linear-gradient(#1b2441,#121a31);color:#e5e9ff;font:800 13px Tahoma,Arial,sans-serif;
 box-shadow:0 3px 12px #0001}
body.ref67 .ref67-filter.active{background:linear-gradient(120deg,#5426df,#902eff);border-color:#b07bff;
 box-shadow:0 0 0 1px #ad68fc70,0 0 19px #813afc6b;color:white}
body.ref67 .v51-mobile-categories{display:none!important}
body.ref67 .protocol-toolbar{display:none!important}
body.ref67 .protocols{display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr))!important;
 gap:11px!important;margin:14px 0 20px!important}
body.ref67 .protocol-choice{display:flex!important;align-items:center!important;flex-direction:row!important;
 justify-content:flex-start!important;text-align:right!important;min-height:82px!important;min-width:0;
 gap:12px!important;padding:12px 13px!important;border-radius:18px!important;
 border:1px solid #344464!important;background:linear-gradient(140deg,#16223f,#101a30)!important;
 box-shadow:0 4px 16px #0002;transform:none!important}
body.ref67 .protocol-choice[hidden],body.ref67 .protocol-choice.ref67-hidden{display:none!important}
body.ref67 .protocol-choice.active{border-color:#a982ff!important;box-shadow:0 0 0 1px #a16bff,0 0 19px #8a52f47b!important}
body.ref67 .protocol-choice .protocol-icon{display:grid!important;place-items:center;
 flex:0 0 51px!important;width:51px!important;height:51px!important;
 border-radius:50%!important;background:linear-gradient(135deg,var(--pc,#8943f5),#5422bc)!important;
 font-size:24px!important;color:white!important;box-shadow:inset 0 -4px 13px #0002}
body.ref67 .protocol-choice[data-protocol-key="v2ray"]{--ref67-icon:#7525e7}
body.ref67 .protocol-choice[data-protocol-key="wireguard"]{--ref67-icon:#df1749}
body.ref67 .protocol-choice[data-protocol-key="openvpn"]{--ref67-icon:#f4941e}
body.ref67 .protocol-choice[data-protocol-key="l2tp"]{--ref67-icon:#168cf2}
body.ref67 .protocol-choice[data-protocol-key="hysteria2"]{--ref67-icon:#09bcba}
body.ref67 .protocol-choice[data-protocol-key="anytls"]{--ref67-icon:#138eea}
body.ref67 .protocol-choice[data-protocol-key="naive"]{--ref67-icon:#305ad7}
body.ref67 .protocol-choice[data-protocol-key="tuic"]{--ref67-icon:#0ab4da}
body.ref67 .protocol-choice[data-protocol-key="cisco"]{--ref67-icon:#00b9ba}
body.ref67 .protocol-choice[data-protocol-key="amneziawg"]{--ref67-icon:#7823db}
body.ref67 .protocol-choice .protocol-icon{background:linear-gradient(135deg,var(--ref67-icon,var(--pc,#8943f5)),color-mix(in srgb,var(--ref67-icon,var(--pc,#8943f5)) 65%,#23184d))!important}
body.ref67 .protocol-choice .protocol-icon img{width:25px;height:25px;object-fit:contain;display:block}
body.ref67 .ref71-rtt{display:inline-flex;align-items:center;min-height:22px;margin-inline-start:4px;padding:2px 6px;border:1px solid #315e56;border-radius:8px;background:#15423955;color:#7ff3c2;font-size:10px;font-weight:900;direction:ltr}

body.ref67 .protocol-choice .protocol-text{min-width:0;text-align:right}
body.ref67 .protocol-choice .protocol-text b{display:block!important;font-size:14px!important;
 color:white;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
body.ref67 .protocol-choice .protocol-text small{display:block!important;font-size:11px!important;
 color:#d2d9ec!important;margin-top:6px!important}
body.ref67 .protocol-choice em{display:none!important}
body.ref67 .protocol-panel{border:1px solid #6942ae!important;border-radius:23px!important;
 background:linear-gradient(155deg,#131b35,#0b1025)!important;overflow:hidden!important;margin:12px 0!important}
body.ref67 .protocol-panel .panel-head{position:relative;display:flex!important;align-items:center!important;
 min-height:99px!important;padding:19px 23px!important;flex-direction:row!important;
 border-bottom:1px solid #383e73!important;background:
 radial-gradient(ellipse at 85% 110%,#8328e088,transparent 45%),
 linear-gradient(110deg,#1d1549,#121a37)!important}
body.ref67 .protocol-panel .panel-head>div:first-child{position:relative;z-index:1}
body.ref67 .protocol-panel .panel-head h3{font-size:25px!important;line-height:1.4;color:#fff!important}
body.ref67 .protocol-panel .panel-head span{font-size:12px!important;color:#44ee99!important}
body.ref67 .protocol-panel .panel-head .server-tabs{display:none!important}
body.ref67 .protocol-panel .ref67-tabs{display:flex;gap:9px;align-items:center;overflow:auto;
 padding:16px 18px 6px;scrollbar-width:none}
body.ref67 .ref67-tabs::-webkit-scrollbar{display:none}
body.ref67 .ref67-chip{flex:0 0 auto;min-height:43px;padding:8px 15px;
 border-radius:13px;background:linear-gradient(#1c2544,#151d35);border:1px solid #424c76;
 color:white;font:850 12px Tahoma,Arial,sans-serif;white-space:nowrap}
body.ref67 .ref67-chip.active{background:linear-gradient(130deg,#6226ed,#a33aff);
 border-color:#b878ff;box-shadow:0 0 17px #7b44fb66}
body.ref67 .v52-multi-card{background:transparent!important;border:0!important;margin:4px 17px 12px!important;
 padding:10px 0!important;box-shadow:none!important}
body.ref67 .v51-multi-head{display:none!important}
body.ref67 .v51-multi-actions{display:flex!important;flex-wrap:wrap;justify-content:flex-end;gap:9px}
body.ref67 .v51-multi-actions>*{min-height:46px!important;border-radius:12px!important;
 font-size:12px!important}
body.ref67 .v51-multi-actions .v51-primary,
body.ref67 .ref67-primary{background:linear-gradient(105deg,#6327ec,#a532ed)!important;border:1px solid #b874ff!important;
 color:white!important;box-shadow:0 0 20px #9a39f454}
body.ref67 .ref67-list{margin:0 17px 13px;border-radius:18px;overflow:hidden;
 border:1px solid #344565;background:linear-gradient(125deg,#111e38,#10182e)}
body.ref67 .ref67-row{display:grid;grid-template-columns: minmax(130px,1fr) auto;
 gap:12px;align-items:center;min-height:75px;padding:10px 14px;border-bottom:1px solid #34405f}
body.ref67 .ref67-row:last-child{border-bottom:0}
body.ref67 .ref67-row[hidden]{display:none!important}
body.ref67 .ref67-row-name{display:flex;gap:12px;align-items:center;min-width:0}
body.ref67 .ref67-flag{font-size:25px;line-height:1}
body.ref67 .ref67-flag img,body.ref67 .ref67-chip img,
body.ref67 .protocol-panel[data-ref67-native-protocol] .server-tab img{
 width:23px;height:17px;object-fit:cover;border-radius:3px;display:inline-block;
 vertical-align:middle;box-shadow:0 1px 4px #0005;flex:0 0 auto;
}
body.ref67 .ref67-chip{display:inline-flex;align-items:center;gap:6px}
body.ref67 .ref67-flag{display:inline-flex;align-items:center;justify-content:center;min-width:25px}

body.ref67 .ref67-row-name b{display:block;color:white;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
body.ref67 .ref67-row-name small{display:block;color:#b5c4e0;font-size:10px;margin-top:4px}
body.ref67 .ref67-status{font-size:11px;font-weight:900;color:#49f5a3}
body.ref67 .ref67-latency{font-size:11px;font-weight:800;color:#bbc8de}
body.ref67 .ref67-row-actions{display:flex;gap:7px;align-items:center;justify-content:flex-end}
body.ref67 .ref67-row-actions a,body.ref67 .ref67-row-actions button{min-height:39px;padding:8px 12px;
 border:1px solid #435176;background:#202943;color:white;border-radius:11px;
 font:850 11px Tahoma,Arial,sans-serif;text-decoration:none;cursor:pointer;white-space:nowrap}
body.ref67 .ref67-row-actions a.ref67-primary{border-color:#b874ff}
body.ref67 .ref67-row-actions button:disabled{opacity:.5}
body.ref67 .protocol-panel[data-ref67-mounted="1"] .server-views{display:none!important}
/* Never replace native file downloads or manual Cisco/L2TP details with
   fabricated URI-only server rows. These remain real per-node operations. */
body.ref67 .protocol-panel[data-ref67-native-protocol] .server-tabs{
  display:flex!important;overflow-x:auto!important;flex-wrap:nowrap!important;
  max-width:100%!important;gap:8px!important;scrollbar-width:none!important;
}
body.ref67 .protocol-panel[data-ref67-native-protocol] .server-views,
body.ref67 .protocol-panel[data-ref67-native-protocol] details.v34-mobile-servers .server-views{
  display:block!important;grid-template-columns:none!important;
  padding:12px 16px!important;gap:10px!important;
}
body.ref67 .protocol-panel[data-ref67-native-protocol] .server-view{
  display:none!important;min-width:0!important;border:1px solid #344665!important;
  border-radius:14px!important;background:#141d34!important;
  margin:0!important;padding:12px!important;
}
body.ref67 .protocol-panel[data-ref67-native-protocol] .server-view.active{display:block!important}
body.ref67 .protocol-panel[data-ref67-native-protocol] .server-view .facts{
  display:grid!important;gap:9px!important;grid-template-columns:1fr!important;
}
body.ref67 .protocol-panel[data-ref67-native-protocol] .server-view .v34-server-actions{
  display:flex!important;gap:8px!important;flex-wrap:wrap!important;
}
body.ref67 .protocol-panel[data-ref67-native-protocol] .server-view .download-config,
body.ref67 .protocol-panel[data-ref67-native-protocol] .server-view a.tp-v16-safe-download,
body.ref67 .protocol-panel[data-ref67-native-protocol] .server-view .v34-server-actions>button,
body.ref67 .protocol-panel[data-ref67-native-protocol] .server-view .v34-server-actions>a{
  min-height:44px!important;border-radius:11px!important;
}
body.ref67 .protocol-panel[data-ref67-native-protocol] .v34-single-label{
  display:block!important;margin:12px 16px 4px!important;color:#d4ddf6!important;
}
body.ref67 .protocol-panel[data-ref67-native-protocol] .v34-client-card{
  display:flex!important;align-items:center!important;justify-content:space-between!important;
  margin:12px 16px!important;padding:12px!important;border:1px solid #534879!important;
  border-radius:12px!important;background:linear-gradient(110deg,#201d48,#15213c)!important;
}
body.ref67 .protocol-panel[data-ref67-native-protocol] .server-tab span{
  white-space:nowrap!important;font-size:12px!important;
}
@media(max-width:720px){
 body.ref67 .protocol-panel[data-ref67-native-protocol] .server-views,
 body.ref67 .protocol-panel[data-ref67-native-protocol] details.v34-mobile-servers .server-views{
   grid-template-columns:1fr!important;padding:9px!important;gap:8px!important;
 }
 body.ref67 .protocol-panel[data-ref67-native-protocol] .server-view{
   padding:10px!important;
 }
 body.ref67 .protocol-panel[data-ref67-native-protocol] .v34-client-card{
   margin:9px!important;align-items:stretch!important;flex-direction:column!important;
 }
}

body.ref67 .protocol-panel[data-ref67-mounted="1"]:not([data-v34-protocol="v2ray"]) .v54-v2ray-groups{display:none!important}
body.ref67 .protocol-panel[data-ref67-mounted="1"] .v54-v2ray-groups{margin:9px 17px;padding:6px;border-radius:14px}
body.ref67 .ref67-footer{margin:12px 17px 18px;display:flex;gap:10px;justify-content:stretch}
body.ref67 .ref67-footer>*{min-height:51px;flex:1;display:flex;align-items:center;justify-content:center;
 border-radius:13px;border:1px solid #3a4971;background:#17213d;color:#f2f5ff;text-decoration:none;
 font:900 12px Tahoma,Arial,sans-serif}
body.ref67 .advanced,body.ref67 .apps{border-color:#353d61!important}
@media(max-width:1000px){
 body.ref67 .traffic .ref67-decoration{display:none}
 body.ref67 .protocols{grid-template-columns:repeat(3,minmax(0,1fr))!important}
}
@media(max-width:720px){
 /* Match approved compact phone layout; render all protocols 4-across. */
 body.ref67 .page{width:min(94vw,440px)!important;padding-top:9px!important}
 body.ref67 .topin{width:min(96vw,480px)!important;height:62px!important}
 body.ref67 .brand b{font-size:20px!important}
 body.ref67 .top .theme{width:35px;height:35px}
 body.ref67 .traffic{min-height:0!important;display:grid!important;gap:8px!important;
 padding:9px!important;border-radius:17px!important}
 body.ref67 .ref67-user{min-width:0!important;padding:9px 11px!important;gap:9px!important;width:100%}
 body.ref67 .ref67-usericon{width:38px;height:38px;flex-basis:38px;font-size:20px}
 body.ref67 .ref67-user strong{font-size:15px}
 body.ref67 .ref67-user small{font-size:10px}
 body.ref67 .traffic .stats{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:0}
 /* Keep first-connection and expiry visible on mobile too. */
 body.ref67 .traffic .stat:nth-child(n+4){display:flex!important}
 body.ref67 .traffic .stat{padding:8px 3px!important;min-height:62px}
 body.ref67 .traffic .stat strong{font-size:14px!important}
 body.ref67 .traffic .stat small{font-size:9px!important}
 body.ref67 .ref67-categories{gap:5px;justify-content:space-between;padding:8px 0 10px}
 body.ref67 .ref67-filter{flex:1;min-width:0;height:36px;font-size:10px;padding:0 4px}
 body.ref67 .protocols{grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:6px!important;margin:9px 0 13px!important}
 body.ref67 .protocol-choice{min-height:76px!important;padding:6px 2px!important;
 flex-direction:column!important;justify-content:center!important;gap:5px!important;border-radius:13px!important}
 body.ref67 .protocol-choice .protocol-icon{width:38px!important;height:38px!important;flex-basis:38px!important;font-size:18px!important}
 body.ref67 .protocol-choice .protocol-text{text-align:center!important;width:100%}
 body.ref67 .protocol-choice .protocol-text b{font-size:10px!important;letter-spacing:-.25px}
 body.ref67 .protocol-choice .protocol-text small{display:none!important}
 body.ref67 .protocol-panel{border-radius:17px!important}
 body.ref67 .protocol-panel .panel-head{min-height:79px!important;padding:13px!important}
 body.ref67 .protocol-panel .panel-head h3{font-size:17px!important}
 body.ref67 .ref67-tabs{padding:11px 9px 8px;gap:6px}
 body.ref67 .ref67-chip{padding:7px 9px;min-height:34px;font-size:10px;border-radius:10px}
 body.ref67 .ref67-flag{font-family:system-ui,'Apple Color Emoji','Segoe UI Emoji','Noto Color Emoji',sans-serif}
 body.ref67 .ref67-row-actions a,body.ref67 .ref67-row-actions button{width:36px!important;min-width:36px!important;height:36px!important;padding:5px!important;font-size:10px!important;border-radius:10px!important}
 body.ref67 .ref67-row-actions a.ref67-primary{font-size:0!important}
 body.ref67 .ref67-row-actions a.ref67-primary:after{content:'+';font-size:23px}
 body.ref67 .ref67-row-actions button{font-size:0!important}
 body.ref67 .ref67-row-actions button:after{content:'⧉';font-size:20px}
 body.ref67 .protocol-panel .panel-head{min-height:65px!important}
 body.ref67 .ref67-list{margin:4px 9px 10px;border-radius:13px}
 body.ref67 .ref67-row{grid-template-columns:minmax(0,1fr) auto;gap:7px;min-height:52px;padding:7px}
 body.ref67 .ref67-flag{font-size:19px}
 body.ref67 .ref67-row-name{gap:7px}
 body.ref67 .ref67-row-name b{font-size:11px}
 body.ref67 .ref67-row-name small{font-size:9px}
 body.ref67 .ref67-status{display:none}
 body.ref67 .ref67-latency{font-size:9px}
 body.ref67 .ref67-row-actions{gap:5px}
 body.ref67 .ref67-row-actions a,body.ref67 .ref67-row-actions button{
  padding:7px 8px;min-height:35px;font-size:10px;border-radius:9px}
 body.ref67 .v51-multi-actions{gap:6px}
 body.ref67 .v51-multi-actions>*{flex:1 1 40%;font-size:10px!important;min-height:40px!important}
 body.ref67 .ref67-footer{margin:10px 9px 12px;gap:6px}
 body.ref67 .ref67-footer>*{font-size:10px;min-height:45px}
}
@media(max-width:370px){
 body.ref67 .protocol-choice .protocol-text b{font-size:8px!important}
 body.ref67 .ref67-row{grid-template-columns:1fr}
 body.ref67 .ref67-row-actions{justify-content:stretch}
 body.ref67 .ref67-row-actions>*{flex:1;text-align:center}
}
"""

_SCRIPT = r"""
<script id="twinpanelPublicConnectionReferenceV67">
(function(){
 'use strict';
 if(!/^\/v1\/connect\/[^/]+\/?$/.test(location.pathname))return;
 const FLAG=(code)=>{
  const raw=String(code||'').toUpperCase();
  const x=raw==='UK'?'GB':raw;
  return /^[A-Z]{2}$/.test(x)?[...x].map(c=>String.fromCodePoint(127397+c.charCodeAt(0))).join(''):'🌐';
 };
 // Use ISO 3166-1 alpha-2 from Node.country_code, not a short country allowlist.
 // The server-rendered tab already contains the true country flag from Node.
 const displayCountries=typeof Intl!=='undefined'&&typeof Intl.DisplayNames==='function'
  ?new Intl.DisplayNames(['en'],{type:'region'}):null;
 const countryName=(code)=>code?(displayCountries?.of(code)||code):'Server';
 const flagToCode=(value)=>{
  const chars=Array.from(String(value||'').match(/[\u{1F1E6}-\u{1F1FF}]{2}/u)?.[0]||'');
  if(chars.length!==2)return '';
  return chars.map(x=>String.fromCharCode(x.codePointAt(0)-0x1F1E6+65)).join('');
 };
 const normalize=(k)=>String(k||'').trim().toLowerCase().replace('xray','v2ray');
 function copyExisting(node){
   if(!node)return false;
   node.click();return true;
 }
 function addUser(){
   const card=document.querySelector('.traffic'),top=document.querySelector('.top .profile');
   if(!card||card.querySelector('.ref67-user'))return;
   const user=top?.querySelector('.service')?.textContent?.trim()||
    document.querySelector('.top .service')?.textContent?.trim()||'Connection';
   const active=top?.querySelector('.status')?.textContent?.trim()||'وضعیت اشتراک';
   const box=document.createElement('div');box.className='ref67-user';
   const avatar=document.createElement('span');avatar.className='ref67-usericon';
   avatar.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true" width="27" height="27" fill="none" stroke="white" stroke-width="2.4" stroke-linecap="round"><circle cx="12" cy="7" r="4"/><path d="M4 21v-2c0-4.2 3.6-6.7 8-6.7s8 2.5 8 6.7v2"/></svg>';
   const info=document.createElement('div');const strong=document.createElement('strong');strong.textContent=user;
   const small=document.createElement('small');small.textContent='● '+active;
   info.append(strong,small);box.append(avatar,info);
   card.insertBefore(box,card.firstChild);
   const deco=document.createElement('div');deco.className='ref67-decoration';deco.setAttribute('aria-hidden','true');
   for(let i=0;i<3;i++)deco.appendChild(document.createElement('i'));
   card.appendChild(deco);
 }
 const families={
  classic:new Set(['openvpn','wireguard','cisco','l2tp','amneziawg']),
  modern:new Set(['v2ray','hysteria2','tuic','anytls','naive','shadowtls','snell','socks5','mieru','trusttunnel','sudoku'])
 };
 function key(choice){return normalize(choice.dataset.protocolKey||'').replace(/[\s_]/g,'')}
 function reorderProtocols(){
  const grid=document.querySelector('.protocols');
  if(!grid||grid.dataset.ref67Ordered==='1')return;
  grid.dataset.ref67Ordered='1';
  const order=['v2ray','wireguard','openvpn','l2tp','amneziawg','hysteria2',
    'anytls','shadowtls','trusttunnel','mieru','naive','tuic','snell','cisco',
    'sudoku','socks5'];
  const choices=[...grid.querySelectorAll('.protocol-choice')];
  choices.sort((a,b)=>{
   const x=order.indexOf(key(a)),y=order.indexOf(key(b));
   return (x<0?99:x)-(y<0?99:y);
  });
  choices.forEach(node=>grid.appendChild(node));
 }
 function categories(){
  const protocols=document.querySelector('.protocols');
  if(!protocols||document.querySelector('.ref67-categories'))return;
  const wrapper=document.createElement('nav');wrapper.className='ref67-categories';
  wrapper.setAttribute('aria-label','دسته‌بندی پروتکل‌ها');
  for(const [name,label] of [['recommended','پیشنهادی'],['modern','مدرن'],['classic','کلاسیک'],['all','همه پروتکل‌ها']]){
   const button=document.createElement('button');button.type='button';button.className='ref67-filter';
   button.dataset.ref67Filter=name;button.textContent=label;
   button.addEventListener('click',()=>{
    wrapper.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===button));
    const choices=[...document.querySelectorAll('.protocol-choice')];
    for(const choice of choices){
     const id=key(choice);
     const visible=name==='all'||(name==='classic'&&families.classic.has(id))||
      (name==='modern'&&families.modern.has(id))||
      (name==='recommended'&&new Set(['v2ray','wireguard','openvpn','hysteria2','tuic']).has(id));
     choice.classList.toggle('ref67-hidden',!visible);
     // Disable stale filtering from preexisting V51 without mutating protocol data.
     choice.dataset.v51Filtered='0';
    }
    const active=choices.find(x=>x.classList.contains('active')&&!x.classList.contains('ref67-hidden'));
    if(!active)choices.find(x=>!x.classList.contains('ref67-hidden'))?.click();
   });
   wrapper.appendChild(button);
  }
  protocols.parentNode.insertBefore(wrapper,protocols);
  wrapper.querySelector('[data-ref67-filter="all"]')?.click();
 }
 function flagImageOrEmoji(code,cls){
  const wrapper=document.createElement('span');
  wrapper.className=cls||'ref67-flag';
  wrapper.textContent=FLAG(code);
  if(!/^[A-Z]{2}$/.test(String(code||'')))return wrapper;
  // Windows does not render regional-indicator emoji flags reliably.
  // Load the actual ISO country flag; retain emoji if image access fails.
  const image=document.createElement('img');
  image.alt=code;
  image.loading='lazy';
  image.decoding='async';
  image.addEventListener('load',()=>{wrapper.replaceChildren(image)});
  image.src='https://flagcdn.com/w40/'+code.toLowerCase()+'.png';
  return wrapper;
 }
 function applyOfficialProtocolIcons(){
  const logos={openvpn:'openvpn',wireguard:'wireguard',cisco:'cisco'};
  document.querySelectorAll('.protocol-choice[data-protocol-key]').forEach(choice=>{
    const key=String(choice.dataset.protocolKey||'').toLowerCase();
    const slug=logos[key];
    const icon=choice.querySelector('.protocol-icon');
    if(!slug||!icon||icon.dataset.ref71OfficialIcon)return;
    icon.dataset.ref71OfficialIcon='1';
    const img=document.createElement('img');
    img.alt=key+' official logo';
    img.loading='lazy';
    img.decoding='async';
    img.addEventListener('load',()=>icon.replaceChildren(img));
    // Preserve the existing label if the external static logo cannot load.
    img.src='https://cdn.simpleicons.org/'+slug+'/FFFFFF';
  });
 }
 function decorateNativeTabs(panel){
  if(panel.dataset.ref67Flags==='1')return;
  panel.dataset.ref67Flags='1';
  [...panel.querySelectorAll('.server-tab')].forEach((tab,i)=>{
   const d=serverDescriptor(tab,i);
   if(!/^[A-Z]{2}$/.test(d.code))return;
   const span=tab.querySelector('span');
   if(!span)return;
   span.textContent=' '+d.code+' '+d.num;
   span.prepend(flagImageOrEmoji(d.code,'ref67-native-flag'));
  });
 }
 function serverDescriptor(tab,index){
  const raw=tab.querySelector('span')?.textContent?.trim()||tab.textContent.trim();
  // V5 tabs are rendered as "🇩🇪 · 13" (flag, then separator, then node id).
  // Earlier code expected "DE · 13", discarded the flag and displayed 🌐.
  const emojiCode=flagToCode(raw);
  const alphaCode=raw.match(/\b([A-Z]{2})\s*[·•\-\s]\s*\d+\b/)?.[1]||'';
  const code=emojiCode||alphaCode;
  const number=raw.match(/(?:·|•|-)\s*(\d+)\s*$/)?.[1]||'';
  const num=number||String(index+1);
  return {code,num,flag:code?FLAG(code):'🌐',name:countryName(code)};
 }
 function linkToOriginal(view){
  const deep=[...view.querySelectorAll('a[href]')].find(x=>
    /^(karing|hiddify|v2rayng|v2box|trusttunnel|sudoku):\/\//i.test(x.getAttribute('href')||''));
  const copy=view.querySelector('.tp-v15-copy-config,.v15-standard-link,.tp65-single-actions button,.v34-server-actions button')
    ||[...view.querySelectorAll('button')].find(x=>/کپی کانفیگ|کپی لینک اتصال/.test(x.textContent||''));
  return {deep,copy};
 }
 function mountPanel(panel){
  // Native files and manual protocols have legitimate per-node payloads that
  // are not share URIs. Keep the canonical download buttons and credential
  // facts, instead of replacing them with fake 'no single link' rows.
  const choice=[...document.querySelectorAll('.protocol-choice')].find(
    node=>String(node.dataset.protocol||'')===String(panel.id||'')
  );
  const protocol=String(choice?.dataset.protocolKey||panel.dataset.v34Protocol||'').toLowerCase();
  if(new Set(['openvpn','wireguard','amneziawg','cisco','l2tp']).has(protocol)){
    panel.dataset.ref67NativeProtocol=protocol;
    const folds=panel.querySelectorAll('details.v34-mobile-servers');
    folds.forEach(fold=>{fold.open=true});
    decorateNativeTabs(panel);
    return;
  }
  if(panel.dataset.ref67Mounted==='1')return;
  const tabs=[...panel.querySelectorAll('.server-tab')];
  const views=[...panel.querySelectorAll('.server-view')];
  if(!tabs.length)return;
  panel.dataset.ref67Mounted='1';
  const bar=document.createElement('div');bar.className='ref67-tabs';
  const all=document.createElement('button');all.type='button';all.className='ref67-chip active';
  all.textContent='همه';bar.appendChild(all);
  const list=document.createElement('div');list.className='ref67-list';
  const rows=[];
  tabs.forEach((tab,i)=>{
   const d=serverDescriptor(tab,i);
   const c=document.createElement('button');c.type='button';c.className='ref67-chip';
   c.append(flagImageOrEmoji(d.code,'ref67-flag'),document.createTextNode(' '+(d.code||'—')+' '+d.num));
   c.addEventListener('click',()=>{bar.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===c));
    rows.forEach((row,j)=>row.hidden=i!==j);tab.click();});
   bar.appendChild(c);
   const row=document.createElement('div');row.className='ref67-row';
   const name=document.createElement('div');name.className='ref67-row-name';
   const flag=flagImageOrEmoji(d.code,'ref67-flag');
   const info=document.createElement('div');const b=document.createElement('b');
   b.textContent=d.name+' - '+d.num;const sub=document.createElement('small');
   sub.textContent=panel.querySelector('.panel-head h3')?.textContent?.trim()||'Connection';
   info.append(b,sub);name.append(flag,info);
   const actions=document.createElement('div');actions.className='ref67-row-actions';
   // Bind actions to the real server view id, never a fragile array position.
   const serverId=tab.dataset.server||'';
   const matchingView=serverId?views.find(view=>view.id===serverId):null;
   const original=linkToOriginal(matchingView||document.createElement('div'));
   if(original.copy){
    const btn=document.createElement('button');btn.type='button';btn.textContent='⧉ کپی';
    btn.addEventListener('click',()=>copyExisting(original.copy));actions.appendChild(btn);
   }
   if(original.deep){
    const a=document.createElement('a');a.className='ref67-primary';
    a.textContent='＋ افزودن';a.href=original.deep.getAttribute('href');
    actions.appendChild(a);
   }
   // Do not display a fake action when no actual client URI exists.
   if(actions.children.length)row.append(name,actions);
   else row.append(name);
   list.appendChild(row);rows.push(row);
  });
  all.addEventListener('click',()=>{
   bar.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===all));
   rows.forEach(row=>row.hidden=false);
  });
  const head=panel.querySelector('.panel-head');
  if(head)head.insertAdjacentElement('afterend',bar);
  const multi=panel.querySelector('.v52-multi-card,.v51-multi-card');
  if(multi)multi.insertAdjacentElement('afterend',list);
  else bar.insertAdjacentElement('afterend',list);

 }
 function apply(){
  document.body.classList.add('ref67');
  const mark=document.querySelector('.brand .mark');
  if(mark&&!mark.dataset.ref67BrandIcon){
   mark.dataset.ref67BrandIcon='1';
   mark.innerHTML='<svg viewBox="0 0 24 24" width="27" height="27" fill="none" stroke="white" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.07 0l3-3a5 5 0 1 0-7.07-7.07l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.07 0l-3 3A5 5 0 1 0 11 21.07l1.7-1.7"/></svg>';
  }
  addUser();reorderProtocols();categories();applyOfficialProtocolIcons();
  if(!document.body.dataset.ref67InitialSelection){
   document.body.dataset.ref67InitialSelection='1';
   document.querySelector('.protocol-choice[data-protocol-key="v2ray"]')?.click();
  }
  document.querySelectorAll('.protocol-panel').forEach(mountPanel);
 }
 apply();
 // The legacy page asynchronously constructs the multilink controls.
 let n=0;const timer=setInterval(()=>{apply();if(++n===16)clearInterval(timer)},300);
})();
</script>
"""

def refine_public_connection_reference_desktop_mobile_v67(source: str) -> str:
    if _MARKER in source:
        return source
    source = source.replace("</style>", _CSS + "\n</style>", 1)
    return source.replace("</body>", _SCRIPT + f"\n<!-- {_MARKER} -->\n</body>", 1)
