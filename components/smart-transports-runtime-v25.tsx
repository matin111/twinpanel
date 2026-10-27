"use client";

import {TunnelControlCenterV1} from "./tunnel-control-center-v1";

// TWINPANEL_SINGLE_TUNNEL_UI_AUTHORITY_V293
// Kept only as a route-compatible adapter. /admin/tunnel-transports and
// /admin/tunnels must render the same data-driven control surface.
export function SmartTransportsRuntimeV25(){
  return <TunnelControlCenterV1/>;
}
