import {OutboundPerformanceInline} from "../../../components/outbound-performance-inline";
import {OutboundPolicyCenter} from "../../../components/outbound-policy-center";
import styles from "./page.module.css";

export default function Page(){
  return <div className={styles.fullWidth}>
    <OutboundPolicyCenter/>
    <OutboundPerformanceInline/>
  </div>;
}
