import {OutboundPerformanceV4} from "../../../components/outbound-performance-v4";
import {OutboundPolicyCenter} from "../../../components/outbound-policy-center";
import styles from "./page.module.css";

const compactHeaderCss=`
[data-outbounds-compact] .page-head{
  display:none!important;
}
[data-outbounds-compact] section:has(> div > h1):has(select){
  display:flex!important;
  align-items:center!important;
  justify-content:flex-start!important;
  grid-template-columns:none!important;
  gap:10px!important;
  min-height:0!important;
  padding:10px 14px!important;
  border:0!important;
  border-radius:0!important;
  background:transparent!important;
  box-shadow:none!important;
  overflow:visible!important;
}
[data-outbounds-compact] section:has(> div > h1):has(select) > div:not(:has(select)){
  display:none!important;
}
[data-outbounds-compact] section:has(> div > h1):has(select) > div:has(select){
  display:flex!important;
  flex:1 1 auto!important;
  align-items:flex-end!important;
  justify-content:flex-start!important;
  gap:10px!important;
  padding:0!important;
  border:0!important;
  border-radius:0!important;
  background:transparent!important;
  box-shadow:none!important;
  backdrop-filter:none!important;
}
[data-outbounds-compact] section:has(> div > h1):has(select) label{
  display:grid!important;
  gap:4px!important;
  width:min(360px,100%)!important;
  min-width:240px!important;
}
[data-outbounds-compact] section:has(> div > h1):has(select) select,
[data-outbounds-compact] section:has(> div > h1):has(select) button{
  min-height:38px!important;
}

html[data-theme="light"] [data-outbounds-compact]{
  --text:#171725;
  --muted:#5f6375;
  --panel:#ffffff;
  --panel-2:#f7f7fb;
  --border:#d9ddea;
}
html[data-theme="light"] [data-outbounds-compact] section,
html[data-theme="light"] [data-outbounds-compact] article{
  color:#171725;
}
html[data-theme="light"] [data-outbounds-compact] small,
html[data-theme="light"] [data-outbounds-compact] label,
html[data-theme="light"] [data-outbounds-compact] .muted,
html[data-theme="light"] [data-outbounds-compact] [class*="muted"],
html[data-theme="light"] [data-outbounds-compact] [class*="Meta"],
html[data-theme="light"] [data-outbounds-compact] [class*="meta"]{
  color:#5f6375!important;
}
html[data-theme="light"] [data-outbounds-compact] input,
html[data-theme="light"] [data-outbounds-compact] select,
html[data-theme="light"] [data-outbounds-compact] textarea{
  color:#171725!important;
  background:#ffffff!important;
  border-color:#d9ddea!important;
}
html[data-theme="light"] [data-outbounds-compact] input::placeholder,
html[data-theme="light"] [data-outbounds-compact] textarea::placeholder{
  color:#8a8fa3!important;
  opacity:1!important;
}
html[data-theme="light"] [data-outbounds-compact] button:not(.primary):not([class*="refresh"]){
  color:#3f4352;
}
html[data-theme="light"] [data-outbounds-compact] button:disabled{
  opacity:.68!important;
}
html[data-theme="light"] [data-outbounds-compact] [class*="tabActive"],
html[data-theme="light"] [data-outbounds-compact] [class*="routePill"],
html[data-theme="light"] [data-outbounds-compact] [class*="protocolChips"] span,
html[data-theme="light"] [data-outbounds-compact] [class*="typeBadge"],
html[data-theme="light"] [data-outbounds-compact] [class*="defaultBadge"]{
  color:#5b21b6!important;
}
html[data-theme="light"] [data-outbounds-compact] [class*="healthOk"]{
  color:#047857!important;
}
html[data-theme="light"] [data-outbounds-compact] [class*="healthIdle"],
html[data-theme="light"] [data-outbounds-compact] [class*="healthNeutral"]{
  color:#5f6375!important;
}
html[data-theme="light"] [data-outbounds-compact] h1,
html[data-theme="light"] [data-outbounds-compact] h2,
html[data-theme="light"] [data-outbounds-compact] h3,
html[data-theme="light"] [data-outbounds-compact] strong,
html[data-theme="light"] [data-outbounds-compact] b{
  color:#171725;
}
html[data-theme="light"] [data-outbounds-compact] [class*="controlBar"],
html[data-theme="light"] [data-outbounds-compact] [class*="panel"],
html[data-theme="light"] [data-outbounds-compact] [class*="statCard"],
html[data-theme="light"] [data-outbounds-compact] [class*="outboundCard"]{
  background:#ffffff!important;
  border-color:#d9ddea!important;
}

@media (max-width:720px){
  [data-outbounds-compact] section:has(> div > h1):has(select){
    padding:8px 10px!important;
  }
  [data-outbounds-compact] section:has(> div > h1):has(select) > div:has(select){
    align-items:stretch!important;
    flex-direction:column!important;
  }
  [data-outbounds-compact] section:has(> div > h1):has(select) label{
    width:100%!important;
    min-width:0!important;
  }
}
`;

export default function Page(){
  return <div className={styles.fullWidth} data-outbounds-compact>
    <style>{compactHeaderCss}</style>
    <OutboundPolicyCenter/>
    <OutboundPerformanceV4/>
  </div>;
}
