"use client";

import {TunnelControlCenterV1} from "./tunnel-control-center-v1";

// TWINPANEL_SINGLE_TUNNEL_UI_AUTHORITY_V1
// /admin/tunnels and /admin/tunnel-transports intentionally converge on the
// same data-driven control surface. Tunnel ID never selects a different UI.
export function TunnelsSimpleRuntimePage(){
  return <TunnelControlCenterV1/>;
}
