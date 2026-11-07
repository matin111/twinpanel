from __future__ import annotations

# Visual-only: do not modify VPN endpoints, config payloads, subscriptions,
# country metadata, latency metrics, credentials, or direct-download URLs.
_MARKER = "TWINPANEL_PUBLIC_CONNECT_PROTOCOL_ICONS_FLAGS_V73"

_CSS = r"""
/* TWINPANEL_PUBLIC_CONNECT_PROTOCOL_ICONS_FLAGS_V73 */
body.ref73-ready .protocol-icon svg {
  display:block!important;width:62%!important;height:62%!important;
  fill:#fff!important;color:#fff!important;stroke-linecap:round;
  stroke-linejoin:round;filter:drop-shadow(0 1px 2px #0002);
}
body.ref73-ready .protocol-choice .protocol-icon:has(svg){
  border-radius:50%!important;
}
body.ref73-ready .ref67-chip .tp73-flag,
body.ref73-ready .ref67-flag .tp73-flag,
body.ref73-ready .ref67-native-flag .tp73-flag,
body.ref73-ready .server-tab .tp73-flag{
 display:inline-block!important;width:24px!important;height:18px!important;
 border-radius:3px!important;box-shadow:0 1px 5px #0007!important;
 vertical-align:middle!important;flex-shrink:0!important;overflow:hidden!important;
}
body.ref73-ready .tp73-flag svg,
body.ref73-ready .tp73-flag img{
 display:block!important;width:100%!important;height:100%!important;
 max-width:none!important;object-fit:cover!important;border-radius:0!important;
}
body.ref73-ready .ref67-flag[data-tp73-decorated="1"],
body.ref73-ready .ref67-native-flag[data-tp73-decorated="1"]{
 font-size:0!important;
}
body.ref73-ready .ref67-chip{gap:6px!important}
body.ref73-ready .tp73-country-code{
 font:850 11px system-ui,Arial,sans-serif;direction:ltr;white-space:nowrap;
}
body.ref73-ready .protocol-panel .ref67-row-name{gap:9px!important}
@media(max-width:720px){
 body.ref73-ready .protocol-icon svg{width:64%!important;height:64%!important}
 body.ref73-ready .ref67-chip .tp73-flag,
 body.ref73-ready .ref67-flag .tp73-flag,
 body.ref73-ready .server-tab .tp73-flag{width:22px!important;height:16px!important}
}
"""

_SCRIPT = r"""
<script id="twinpanelPublicConnectProtocolIconsFlagsV73">
(function(){
 'use strict';
 if(!/^\/v1\/connect\/[^/]+\/?$/.test(location.pathname))return;
 document.body.classList.add('ref73-ready');
 const official = {"wireguard":"M23.98 11.645S24.533 0 11.735 0C.418 0 .064 11.17.064 11.17S-1.6 24 11.997 24C25.04 24 23.98 11.645 23.98 11.645zM8.155 7.576c2.4-1.47 5.469-.571 6.618 1.638.218.419.246 1.063.108 1.503-.477 1.516-1.601 2.366-3.145 2.728.455-.39.817-.832.933-1.442a2.112 2.112 0 0 0-.364-1.677 2.14 2.14 0 0 0-2.465-.75c-.95.36-1.47 1.228-1.377 2.294.087.99.839 1.632 2.245 1.876-.21.111-.372.193-.53.281a5.113 5.113 0 0 0-1.644 1.43c-.143.192-.24.208-.458.075-2.827-1.729-3.009-6.067.078-7.956zM6.04 18.258c-.455.116-.895.286-1.359.438.227-1.532 2.021-2.943 3.539-2.782a3.91 3.91 0 0 0-.74 2.072c-.504.093-.98.155-1.44.272zM15.703 3.3c.448.017.898.01 1.347.02a2.324 2.324 0 0 1 .334.047 3.249 3.249 0 0 1-.34.434c-.16.15-.341.296-.573.069-.055-.055-.187-.042-.283-.044-.447-.005-.894-.02-1.34-.003a8.323 8.323 0 0 0-1.154.118c-.072.013-.178.25-.146.338.078.207.191.435.359.567.619.49 1.277.928 1.9 1.413.604.472 1.167.99 1.51 1.7.446.928.46 1.9.267 2.877-.322 1.63-1.147 2.98-2.483 3.962-.538.395-1.205.62-1.821.903-.543.25-1.1.465-1.644.712-.98.446-1.53 1.51-1.369 2.615.149 1.015 1.04 1.862 2.059 2.037 1.223.21 2.486-.586 2.785-1.83.336-1.397-.423-2.646-1.845-3.024l-.256-.066c.38-.17.708-.291 1.012-.458q.793-.437 1.558-.925c.15-.096.231-.096.36.014.977.846 1.56 1.898 1.724 3.187.27 2.135-.74 4.096-2.646 5.101-2.948 1.555-6.557-.215-7.208-3.484-.558-2.8 1.418-5.34 3.797-5.83 1.023-.211 1.958-.637 2.685-1.425.47-.508.697-.944.775-1.141a3.165 3.165 0 0 0 .217-1.158 2.71 2.71 0 0 0-.237-.992c-.248-.566-1.2-1.466-1.435-1.656l-2.24-1.754c-.079-.065-.168-.06-.36-.047-.23.016-.815.048-1.067-.018.204-.155.76-.38 1-.56-.726-.49-1.554-.314-2.315-.46.176-.328 1.046-.831 1.541-.888a7.323 7.323 0 0 0-.135-.822c-.03-.111-.154-.22-.263-.283-.262-.154-.541-.281-.843-.434a1.755 1.755 0 0 1 .906-.28 3.385 3.385 0 0 1 .908.088c.54.123.97.042 1.399-.324-.338-.136-.676-.26-1.003-.407a9.843 9.843 0 0 1-.942-.493c.85.118 1.671.437 2.54.32l.022-.118-2.018-.47c1.203-.11 2.323-.128 3.384.388.299.146.61.266.897.432.14.08.233.24.348.365.09.098.164.23.276.29.424.225.89.234 1.366.223l.01-.16c.479.15 1.017.702 1.017 1.105-.776 0-1.55-.003-2.325.004-.083 0-.165.061-.247.094.078.046.155.128.235.131z M14.703 2.153a.118.118 0 0 0-.016.19.179.179 0 0 0 .246.065c.075-.038.148-.078.238-.125-.072-.062-.13-.114-.19-.163-.106-.087-.193-.032-.278.033z","openvpn":"M12 .357C5.385.357 0 5.69 0 12.254c0 4.36 2.358 8.153 5.896 10.204l.77-5.076a7.046 7.046 0 01-1.846-4.719c0-3.897 3.18-7.076 7.13-7.076 3.948 0 7.126 3.18 7.126 7.076 0 1.847-.717 3.488-1.846 4.77L18 22.51c3.59-2.05 6-5.899 6-10.258C24 5.69 18.615.357 12 .357zm-.05 8.157a3.786 3.786 0 00-3.796 3.795 3.738 3.738 0 002.461 3.54L9.13 23.643h5.64l-1.435-7.795c1.385-.564 2.41-1.898 2.41-3.54a3.786 3.786 0 00-3.795-3.794z","cisco":"M16.331 18.171V17.06l-.022.01c-.25.121-.522.19-.801.203a1.186 1.186 0 01-.806-.237 1.038 1.038 0 01-.352-.498 1.21 1.21 0 01-.023-.667c.052-.225.178-.426.357-.569.16-.134.355-.218.562-.242a1.85 1.85 0 011.061.198l.024.013v-1.117l-.051-.014a2.862 2.862 0 00-1.011-.132 2.34 2.34 0 00-.903.206c-.287.132-.54.327-.739.571a2.221 2.221 0 00-.04 2.705c.295.378.709.645 1.175.756.491.12 1.006.102 1.487-.052l.082-.023M5.336 18.171V17.06l-.022.01c-.25.121-.522.19-.801.203a1.183 1.183 0 01-.806-.237 1.03 1.03 0 01-.351-.498 1.202 1.202 0 01-.024-.667c.052-.225.177-.426.357-.569.16-.134.355-.218.562-.242a1.85 1.85 0 011.061.198l.024.013v-1.117l-.051-.014a2.862 2.862 0 00-1.011-.132 2.344 2.344 0 00-.903.206 2.08 2.08 0 00-.74.571 2.224 2.224 0 00-.041 2.705 2.11 2.11 0 001.176.756c.491.12 1.005.102 1.487-.052l.083-.023M9.26 17.249l-.004.957.07.012c.22.041.441.069.664.085.195.019.391.022.587.012.187-.014.372-.049.551-.104.21-.06.405-.163.571-.305a1.16 1.16 0 00.333-.478 1.31 1.31 0 00-.007-.96 1.068 1.068 0 00-.298-.414 1.261 1.261 0 00-.438-.255l-.722-.268a.388.388 0 01-.197-.188.245.245 0 01.008-.219.382.382 0 01.154-.142.798.798 0 01.257-.074c.153-.022.308-.021.46.005.18.02.358.051.533.096l.038.008v-.883l-.069-.015a4.749 4.749 0 00-.543-.097 2.844 2.844 0 00-.714-.003c-.3.027-.585.143-.821.33-.16.126-.281.293-.351.484-.104.29-.105.608 0 .899.054.145.14.274.252.381.097.093.207.173.327.236.157.084.324.149.497.195.057.017.114.035.17.054l.085.031.024.01c.084.03.162.078.226.14.045.042.08.094.101.151a.325.325 0 01.001.161.339.339 0 01-.166.198.856.856 0 01-.275.086 2.032 2.032 0 01-.427.021 5.208 5.208 0 01-.557-.074 9.195 9.195 0 01-.287-.067l-.033-.006zm-2.475.995h1.05v-4.167h-1.05v4.167zm12.162-2.936a1.095 1.095 0 011.541.158 1.094 1.094 0 01-.157 1.541l-.017.014a1.096 1.096 0 01-1.367-1.713m-1.525.854a2.193 2.193 0 002.666 2.107 2.139 2.139 0 00.701-3.937 2.207 2.207 0 00-3.367 1.83M22.961 10.728a.52.52 0 001.039 0V9.573a.52.52 0 00-1.039 0v1.155M20.117 10.728a.522.522 0 001.041 0V8.139a.521.521 0 00-1.04 0v2.589M17.231 11.771a.521.521 0 001.039 0V6.17a.52.52 0 00-1.039 0v5.601M14.393 10.728a.521.521 0 001.04 0V8.139a.52.52 0 00-1.039 0v2.589M11.494 10.728a.522.522 0 001.039 0V9.573a.52.52 0 00-1.039 0v1.155M8.624 10.728a.52.52 0 001.039 0V8.139a.52.52 0 00-1.039 0v2.589M5.737 11.771a.52.52 0 001.039 0V6.17a.52.52 0 00-1.039 0v5.601M2.876 10.728a.522.522 0 001.04 0V8.139a.52.52 0 00-1.039 0v2.589M0 10.728a.521.521 0 001.039 0V9.573a.52.52 0 00-1.039 0v1.155"};
 // Official designs are embedded locally in the public HTML, so icons don't
 // disappear if a CDN is filtered. Protocols without a published/verified mark
 // receive a distinct neutral *symbol*, never a misleading fake official logo.
 const pictograms={
  v2ray:'<circle cx="12" cy="12" r="9"/><path d="M7 12l4 4 6-8"/>',
  l2tp:'<rect x="3" y="5" width="18" height="15" rx="3"/><path d="M7 5V3m10 2V3M7 12h10m-5-3v7"/>',
  amneziawg:'<path d="M12 2L4 6v5c0 5 3 9 8 11 5-2 8-6 8-11V6z"/><path d="M9 12l2 2 4-4"/>',
  hysteria2:'<path d="M13 2L5 13h6l-1 9 9-12h-6z"/>',
  anytls:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 018 0v3"/><circle cx="12" cy="15.5" r="1"/>',
  shadowtls:'<path d="M12 2L4 6v6c0 5 4 9 8 10 4-1 8-5 8-10V6z"/><path d="M8 13l3 3 5-6"/>',
  trusttunnel:'<path d="M2 12h20M7 7l-5 5 5 5m10-10l5 5-5 5"/><circle cx="12" cy="12" r="3"/>',
  mieru:'<path d="M3 12c3-5 6-5 9 0s6 5 9 0M3 18c3-5 6-5 9 0s6 5 9 0"/>',
  naive:'<path d="M4 17V7l8 10V7m4 0h4v10h-4z"/>',
  tuic:'<circle cx="12" cy="12" r="8"/><path d="M12 6v6l4 3M8 2h8"/>',
  snell:'<path d="M3 16c2-3 4-3 6 0s4 3 6 0 4-3 6 0M3 9c2-3 4-3 6 0s4 3 6 0 4-3 6 0"/>',
  sudoku:'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18M15 3v18M3 9h18M3 15h18"/>',
  socks5:'<circle cx="12" cy="12" r="9"/><path d="M7 12h10M12 7l5 5-5 5"/>',
  shadowtls:'<path d="M12 2L4 6v6c0 5 4 9 8 10 4-1 8-5 8-10V6z"/><path d="M8 13l3 3 5-6"/>'
 };
 const aliases={cisco:'cisco',openconnect:'cisco','l2tp-ipsec':'l2tp',vless:'v2ray',xray:'v2ray'};
 const ns='http://www.w3.org/2000/svg';
 function keyOf(choice){
   const raw=String(choice.dataset.protocolKey||'').trim().toLowerCase();
   return aliases[raw]||raw;
 }
 function mountIcon(choice){
   const icon=choice.querySelector('.protocol-icon');
   if(!icon||icon.dataset.tp73Ready)return;
   const key=keyOf(choice);
   const path=official[key];
   const shape=pictograms[key];
   if(!path&&!shape)return;
   const svg=document.createElementNS(ns,'svg');
   svg.setAttribute('viewBox','0 0 24 24');
   svg.setAttribute('aria-hidden','true');
   if(path){const p=document.createElementNS(ns,'path');p.setAttribute('d',path);p.setAttribute('fill','currentColor');svg.appendChild(p);}
   else{
     svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','2');
     svg.innerHTML=shape;
   }
   icon.replaceChildren(svg);icon.dataset.tp73Ready='1';
   icon.setAttribute('title',path?key+' logo':key+' protocol symbol');
 }
 // Inline SVG flags for the currently deployed countries render on Windows
 // even when flag emoji and remote CDN imagery are unavailable.
 function inlineFlag(code){
   if(code==='DE')return '<rect width="32" height="8" fill="#111"/><rect y="8" width="32" height="8" fill="#dd172c"/><rect y="16" width="32" height="8" fill="#ffce00"/>';
   if(code==='TR')return '<rect width="32" height="24" fill="#e30a17"/><circle cx="13" cy="12" r="7" fill="#fff"/><circle cx="15" cy="12" r="5.5" fill="#e30a17"/><polygon fill="#fff" points="20,7 21.1,10.4 24.7,10.4 21.8,12.5 22.9,15.8 20,13.7 17.1,15.8 18.2,12.5 15.3,10.4 18.9,10.4"/>';
   if(code==='US'){
     let rows='<rect width="32" height="24" fill="#fff"/>';
     for(let i=0;i<7;i++)rows+='<rect x="0" y="'+(i*48/13)+'" width="32" height="'+(24/13)+'" fill="#b22234"/>';
     rows+='<rect width="13" height="13" fill="#3c3b6e"/>';
     for(let y=0;y<5;y++)for(let x=0;x<5;x++)rows+='<circle cx="'+(1.2+x*2.4)+'" cy="'+(1.2+y*2.3)+'" r=".5" fill="#fff"/>';
     return rows;
   }
   if(code==='FR')return '<rect width="10.67" height="24" fill="#0055a4"/><rect x="10.67" width="10.67" height="24" fill="#fff"/><rect x="21.34" width="10.66" height="24" fill="#ef4135"/>';
   if(code==='NL')return '<rect width="32" height="8" fill="#ae1c28"/><rect y="8" width="32" height="8" fill="#fff"/><rect y="16" width="32" height="8" fill="#21468b"/>';
   if(code==='JP')return '<rect width="32" height="24" fill="#fff"/><circle cx="16" cy="12" r="7" fill="#bc002d"/>';
   return '';
 }
 function imageFlag(code){
   const span=document.createElement('span');span.className='tp73-flag';
   span.setAttribute('role','img');span.setAttribute('aria-label',code+' flag');
   const svgData=inlineFlag(code);
   if(svgData){
     const svg=document.createElementNS(ns,'svg');
     svg.setAttribute('viewBox','0 0 32 24');svg.innerHTML=svgData;
     span.appendChild(svg);return span;
   }
   // New countries use their ISO country flag asset. On failure, show a
   // labeled country-code tile rather than a broken icon or fake flag.
   const img=document.createElement('img');img.alt=code;
   img.loading='lazy';img.decoding='async';
   img.src='https://flagcdn.com/w40/'+code.toLowerCase()+'.png';
   img.addEventListener('error',()=>{
     span.replaceChildren();
     const label=document.createElement('span');label.className='tp73-country-code';label.textContent=code;
     span.appendChild(label);
   });
   span.appendChild(img);
   return span;
 }
 function extractCode(element){
   const text=element.textContent||'';
   const alpha=text.match(/\b(?:DE|TR|US|FR|NL|JP|[A-Z]{2})\b/);
   if(alpha)return alpha[0];
   const flag=Array.from(text.match(/[\u{1F1E6}-\u{1F1FF}]{2}/u)?.[0]||'');
   if(flag.length===2)return flag.map(c=>String.fromCharCode(c.codePointAt(0)-0x1F1E6+65)).join('');
   const img=element.querySelector('img[alt]');
   const fromImg=String(img?.alt||'').toUpperCase();
   return /^[A-Z]{2}$/.test(fromImg)?fromImg:'';
 }
 function applyFlag(container){
   if(container.dataset.tp73Decorated==='1')return;
   const code=extractCode(container);
   if(!/^[A-Z]{2}$/.test(code))return;
   container.dataset.tp73Decorated='1';
   if(container.classList.contains('ref67-flag')||container.classList.contains('ref67-native-flag')){
     container.replaceChildren(imageFlag(code));return;
   }
   const original=container.querySelector('.ref67-flag, .ref67-native-flag');
   if(original){original.dataset.tp73Decorated='1';original.replaceChildren(imageFlag(code));return;}
   container.prepend(imageFlag(code));
 }
 function apply(){
   document.querySelectorAll('.protocol-choice[data-protocol-key]').forEach(mountIcon);
   document.querySelectorAll('.ref67-chip, .ref67-row .ref67-flag, .server-tab .ref67-native-flag').forEach(applyFlag);
 }
 apply();
 // Late V51/V67 protocol and flag rows may arrive after initial paint.
 let tries=0;const timer=setInterval(()=>{apply();if(++tries===14)clearInterval(timer)},350);
})();
</script>
""".replace("__OFFICIAL_LOGO_PATHS__",{"wireguard":"M23.98 11.645S24.533 0 11.735 0C.418 0 .064 11.17.064 11.17S-1.6 24 11.997 24C25.04 24 23.98 11.645 23.98 11.645zM8.155 7.576c2.4-1.47 5.469-.571 6.618 1.638.218.419.246 1.063.108 1.503-.477 1.516-1.601 2.366-3.145 2.728.455-.39.817-.832.933-1.442a2.112 2.112 0 0 0-.364-1.677 2.14 2.14 0 0 0-2.465-.75c-.95.36-1.47 1.228-1.377 2.294.087.99.839 1.632 2.245 1.876-.21.111-.372.193-.53.281a5.113 5.113 0 0 0-1.644 1.43c-.143.192-.24.208-.458.075-2.827-1.729-3.009-6.067.078-7.956zM6.04 18.258c-.455.116-.895.286-1.359.438.227-1.532 2.021-2.943 3.539-2.782a3.91 3.91 0 0 0-.74 2.072c-.504.093-.98.155-1.44.272zM15.703 3.3c.448.017.898.01 1.347.02a2.324 2.324 0 0 1 .334.047 3.249 3.249 0 0 1-.34.434c-.16.15-.341.296-.573.069-.055-.055-.187-.042-.283-.044-.447-.005-.894-.02-1.34-.003a8.323 8.323 0 0 0-1.154.118c-.072.013-.178.25-.146.338.078.207.191.435.359.567.619.49 1.277.928 1.9 1.413.604.472 1.167.99 1.51 1.7.446.928.46 1.9.267 2.877-.322 1.63-1.147 2.98-2.483 3.962-.538.395-1.205.62-1.821.903-.543.25-1.1.465-1.644.712-.98.446-1.53 1.51-1.369 2.615.149 1.015 1.04 1.862 2.059 2.037 1.223.21 2.486-.586 2.785-1.83.336-1.397-.423-2.646-1.845-3.024l-.256-.066c.38-.17.708-.291 1.012-.458q.793-.437 1.558-.925c.15-.096.231-.096.36.014.977.846 1.56 1.898 1.724 3.187.27 2.135-.74 4.096-2.646 5.101-2.948 1.555-6.557-.215-7.208-3.484-.558-2.8 1.418-5.34 3.797-5.83 1.023-.211 1.958-.637 2.685-1.425.47-.508.697-.944.775-1.141a3.165 3.165 0 0 0 .217-1.158 2.71 2.71 0 0 0-.237-.992c-.248-.566-1.2-1.466-1.435-1.656l-2.24-1.754c-.079-.065-.168-.06-.36-.047-.23.016-.815.048-1.067-.018.204-.155.76-.38 1-.56-.726-.49-1.554-.314-2.315-.46.176-.328 1.046-.831 1.541-.888a7.323 7.323 0 0 0-.135-.822c-.03-.111-.154-.22-.263-.283-.262-.154-.541-.281-.843-.434a1.755 1.755 0 0 1 .906-.28 3.385 3.385 0 0 1 .908.088c.54.123.97.042 1.399-.324-.338-.136-.676-.26-1.003-.407a9.843 9.843 0 0 1-.942-.493c.85.118 1.671.437 2.54.32l.022-.118-2.018-.47c1.203-.11 2.323-.128 3.384.388.299.146.61.266.897.432.14.08.233.24.348.365.09.098.164.23.276.29.424.225.89.234 1.366.223l.01-.16c.479.15 1.017.702 1.017 1.105-.776 0-1.55-.003-2.325.004-.083 0-.165.061-.247.094.078.046.155.128.235.131z M14.703 2.153a.118.118 0 0 0-.016.19.179.179 0 0 0 .246.065c.075-.038.148-.078.238-.125-.072-.062-.13-.114-.19-.163-.106-.087-.193-.032-.278.033z","openvpn":"M12 .357C5.385.357 0 5.69 0 12.254c0 4.36 2.358 8.153 5.896 10.204l.77-5.076a7.046 7.046 0 01-1.846-4.719c0-3.897 3.18-7.076 7.13-7.076 3.948 0 7.126 3.18 7.126 7.076 0 1.847-.717 3.488-1.846 4.77L18 22.51c3.59-2.05 6-5.899 6-10.258C24 5.69 18.615.357 12 .357zm-.05 8.157a3.786 3.786 0 00-3.796 3.795 3.738 3.738 0 002.461 3.54L9.13 23.643h5.64l-1.435-7.795c1.385-.564 2.41-1.898 2.41-3.54a3.786 3.786 0 00-3.795-3.794z","cisco":"M16.331 18.171V17.06l-.022.01c-.25.121-.522.19-.801.203a1.186 1.186 0 01-.806-.237 1.038 1.038 0 01-.352-.498 1.21 1.21 0 01-.023-.667c.052-.225.178-.426.357-.569.16-.134.355-.218.562-.242a1.85 1.85 0 011.061.198l.024.013v-1.117l-.051-.014a2.862 2.862 0 00-1.011-.132 2.34 2.34 0 00-.903.206c-.287.132-.54.327-.739.571a2.221 2.221 0 00-.04 2.705c.295.378.709.645 1.175.756.491.12 1.006.102 1.487-.052l.082-.023M5.336 18.171V17.06l-.022.01c-.25.121-.522.19-.801.203a1.183 1.183 0 01-.806-.237 1.03 1.03 0 01-.351-.498 1.202 1.202 0 01-.024-.667c.052-.225.177-.426.357-.569.16-.134.355-.218.562-.242a1.85 1.85 0 011.061.198l.024.013v-1.117l-.051-.014a2.862 2.862 0 00-1.011-.132 2.344 2.344 0 00-.903.206 2.08 2.08 0 00-.74.571 2.224 2.224 0 00-.041 2.705 2.11 2.11 0 001.176.756c.491.12 1.005.102 1.487-.052l.083-.023M9.26 17.249l-.004.957.07.012c.22.041.441.069.664.085.195.019.391.022.587.012.187-.014.372-.049.551-.104.21-.06.405-.163.571-.305a1.16 1.16 0 00.333-.478 1.31 1.31 0 00-.007-.96 1.068 1.068 0 00-.298-.414 1.261 1.261 0 00-.438-.255l-.722-.268a.388.388 0 01-.197-.188.245.245 0 01.008-.219.382.382 0 01.154-.142.798.798 0 01.257-.074c.153-.022.308-.021.46.005.18.02.358.051.533.096l.038.008v-.883l-.069-.015a4.749 4.749 0 00-.543-.097 2.844 2.844 0 00-.714-.003c-.3.027-.585.143-.821.33-.16.126-.281.293-.351.484-.104.29-.105.608 0 .899.054.145.14.274.252.381.097.093.207.173.327.236.157.084.324.149.497.195.057.017.114.035.17.054l.085.031.024.01c.084.03.162.078.226.14.045.042.08.094.101.151a.325.325 0 01.001.161.339.339 0 01-.166.198.856.856 0 01-.275.086 2.032 2.032 0 01-.427.021 5.208 5.208 0 01-.557-.074 9.195 9.195 0 01-.287-.067l-.033-.006zm-2.475.995h1.05v-4.167h-1.05v4.167zm12.162-2.936a1.095 1.095 0 011.541.158 1.094 1.094 0 01-.157 1.541l-.017.014a1.096 1.096 0 01-1.367-1.713m-1.525.854a2.193 2.193 0 002.666 2.107 2.139 2.139 0 00.701-3.937 2.207 2.207 0 00-3.367 1.83M22.961 10.728a.52.52 0 001.039 0V9.573a.52.52 0 00-1.039 0v1.155M20.117 10.728a.522.522 0 001.041 0V8.139a.521.521 0 00-1.04 0v2.589M17.231 11.771a.521.521 0 001.039 0V6.17a.52.52 0 00-1.039 0v5.601M14.393 10.728a.521.521 0 001.04 0V8.139a.52.52 0 00-1.039 0v2.589M11.494 10.728a.522.522 0 001.039 0V9.573a.52.52 0 00-1.039 0v1.155M8.624 10.728a.52.52 0 001.039 0V8.139a.52.52 0 00-1.039 0v2.589M5.737 11.771a.52.52 0 001.039 0V6.17a.52.52 0 00-1.039 0v5.601M2.876 10.728a.522.522 0 001.04 0V8.139a.52.52 0 00-1.039 0v2.589M0 10.728a.521.521 0 001.039 0V9.573a.52.52 0 00-1.039 0v1.155"})
def refine_public_connection_protocol_icons_flags_v73(source: str) -> str:
    if _MARKER in source:
        return source
    source=source.replace("</style>",_CSS+"\n</style>",1)
    return source.replace("</body>",_SCRIPT+"\n<!-- "+_MARKER+" -->\n</body>",1)
