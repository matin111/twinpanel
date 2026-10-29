"use client";

import {TunnelControlCenterV1} from "./tunnel-control-center-v1";
import styles from "./smart-transports-runtime-v25.module.css";

// TWINPANEL_SINGLE_TUNNEL_UI_AUTHORITY_V1
// TWINPANEL_SINGLE_TUNNEL_UI_AUTHORITY_V293
// Keep /admin/tunnel-transports on the shared tunnel control surface while
// trimming non-operational explanatory copy from the Smart Transports route.
export function SmartTransportsRuntimeV25(){
  return <div className={styles.clean}><TunnelControlCenterV1/></div>;
}
