"use client";

import {useEffect} from "react";

const BUILD_VERSION=String(process.env.NEXT_PUBLIC_TWINPANEL_VERSION||"").trim();
const POLL_MS=15_000;
const CONFIRM_MS=1_200;
const REQUEST_TIMEOUT_MS=4_000;
const CACHE_BUSTER="__tpv";

function sleep(ms:number){
  return new Promise<void>(resolve=>window.setTimeout(resolve,ms));
}

async function healthyServerVersion():Promise<string>{
  const controller=new AbortController();
  const timeout=window.setTimeout(()=>controller.abort(),REQUEST_TIMEOUT_MS);
  try{
    const response=await fetch(`/health?runtime-version-check=${Date.now()}`,{
      cache:"no-store",
      headers:{"Cache-Control":"no-cache"},
      signal:controller.signal
    });
    if(!response.ok)return "";
    const payload=await response.json() as {ok?:unknown;version?:unknown};
    if(payload?.ok!==true)return "";
    return String(payload.version||"").trim();
  }catch{
    return "";
  }finally{
    window.clearTimeout(timeout);
  }
}

function clearConvergenceMarker(){
  const url=new URL(window.location.href);
  if(!url.searchParams.has(CACHE_BUSTER))return;
  url.searchParams.delete(CACHE_BUSTER);
  const query=url.searchParams.toString();
  window.history.replaceState(
    window.history.state,
    "",
    `${url.pathname}${query?`?${query}`:""}${url.hash}`
  );
}

export function RuntimeVersionConvergence(){
  useEffect(()=>{
    if(!BUILD_VERSION)return;

    let disposed=false;
    let timer:number|undefined;
    let checking=false;

    const schedule=()=>{
      if(disposed)return;
      if(timer!==undefined)window.clearTimeout(timer);
      timer=window.setTimeout(()=>void check(),POLL_MS);
    };

    const converge=async(serverVersion:string)=>{
      await sleep(CONFIRM_MS);
      if(disposed)return false;
      const confirmed=await healthyServerVersion();
      if(!confirmed||confirmed!==serverVersion||confirmed===BUILD_VERSION)return false;

      const url=new URL(window.location.href);
      url.searchParams.set(CACHE_BUSTER,confirmed);
      window.location.replace(url.toString());
      return true;
    };

    const check=async()=>{
      if(disposed||checking)return;
      checking=true;
      try{
        const serverVersion=await healthyServerVersion();
        if(!serverVersion){
          return;
        }
        if(serverVersion===BUILD_VERSION){
          clearConvergenceMarker();
          return;
        }
        if(await converge(serverVersion))return;
      }finally{
        checking=false;
        schedule();
      }
    };

    const onVisibility=()=>{
      if(document.visibilityState==="visible")void check();
    };
    const onPageShow=()=>void check();

    document.addEventListener("visibilitychange",onVisibility);
    window.addEventListener("pageshow",onPageShow);
    timer=window.setTimeout(()=>void check(),2_500);

    return ()=>{
      disposed=true;
      if(timer!==undefined)window.clearTimeout(timer);
      document.removeEventListener("visibilitychange",onVisibility);
      window.removeEventListener("pageshow",onPageShow);
    };
  },[]);

  return null;
}
