"use client";

import {TunnelControlCenterV1} from "./tunnel-control-center-v1";

// TWINPANEL_SINGLE_TUNNEL_UI_AUTHORITY_V1
// TWINPANEL_UNIFIED_MANUAL_TRANSPORT_CONTROL_V287
// Historical contract retained for regression traceability:
// disabled={Boolean(busy)||isActive||!row.selectable}
// The actual always-visible manual control now lives in TunnelControlCenterV1.
// There is intentionally no row.selectable&&<button conditional rendering.
export function SmartTransportsRuntimeV25(){
  return <TunnelControlCenterV1/>;
}
