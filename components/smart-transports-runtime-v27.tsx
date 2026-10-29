"use client";

import {useEffect,useState} from "react";

import {SmartTransportsRuntimeV26} from "./smart-transports-runtime-v26";
import {MODERN_TRANSPORT_AUTHORITY_REFRESH_EVENT} from "../lib/modern-transport-api";


// TWINPANEL_SMART_TRANSPORT_AUTHORITY_REFRESH_V207
//
// V26 owns the production Smart Transports UI. During a long candidate install,
// its normal 10s polling can legitimately observe the DB row as `installing`.
// If the install then fails, the old component catches the request error without
// doing an immediate state reload, so that mid-install snapshot can remain on
// screen even though the authoritative DB row is already `failed`.
//
// The API client emits this narrow event only when an install request fails.
// Remounting V26 clears its local busy/snapshot state and immediately reloads the
// authoritative backend state. No transport, route or dataplane behavior changes.
export function SmartTransportsRuntimeV27(){
  const [authorityEpoch,setAuthorityEpoch]=useState(0);

  useEffect(()=>{
    const refresh=()=>setAuthorityEpoch(value=>value+1);
    window.addEventListener(MODERN_TRANSPORT_AUTHORITY_REFRESH_EVENT,refresh);
    return()=>window.removeEventListener(MODERN_TRANSPORT_AUTHORITY_REFRESH_EVENT,refresh);
  },[]);

  return <>
    <style>{`
      .tp-transport-page .tp-hero .tp-eyebrow,
      .tp-transport-page .tp-hero-copy > p,
      .tp-transport-page .tp-overview-card > small,
      .tp-transport-page .tp-service-plane .tp-eyebrow,
      .tp-transport-page .tp-protocol-chip > small,
      .tp-transport-page .tp-section-note,
      .tp-transport-page .tp-card-top > div > p,
      .tp-transport-page .tp-description,
      .tp-transport-page .tp-registry-card .tp-eyebrow,
      .tp-transport-page .tp-footnote {
        display:none !important;
      }
    `}</style>
    <SmartTransportsRuntimeV26 key={authorityEpoch}/>
  </>;
}
