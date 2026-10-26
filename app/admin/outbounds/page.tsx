import {OutboundPerformanceV4} from "../../../components/outbound-performance-v4";
import {OutboundPolicyCenter} from "../../../components/outbound-policy-center";
import styles from "./page.module.css";

export default function Page(){
  return <div className={styles.fullWidth}><OutboundPolicyCenter/><OutboundPerformanceV4/></div>;
}
