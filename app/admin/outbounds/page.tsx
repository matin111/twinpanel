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
