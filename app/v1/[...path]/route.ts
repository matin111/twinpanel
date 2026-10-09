import {NextRequest} from "next/server";

const HOP_BY_HOP_HEADERS=new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length"
]);

function backendBase(){
  return (process.env.TWINPANEL_BACKEND_URL||"http://127.0.0.1:8095").replace(/\/+$/,"");
}

async function proxy(request:NextRequest,context:{params:Promise<{path:string[]}>}){
  const {path}=await context.params;
  const incoming=new URL(request.url);
  const target=new URL(`${backendBase()}/v1/${path.map(encodeURIComponent).join("/")}`);
  target.search=incoming.search;

  const headers=new Headers();
  request.headers.forEach((value,key)=>{
    if(!HOP_BY_HOP_HEADERS.has(key.toLowerCase()))headers.set(key,value);
  });
  headers.set("x-forwarded-host",incoming.host);
  headers.set("x-forwarded-proto",incoming.protocol.replace(":",""));

  const method=request.method.toUpperCase();
  const body=method==="GET"||method==="HEAD"?undefined:await request.arrayBuffer();

  try{
    const upstream=await fetch(target,{method,headers,body,redirect:"manual",cache:"no-store"});
    const responseHeaders=new Headers(upstream.headers);
    for(const key of ["connection","keep-alive","transfer-encoding","content-length","content-encoding"])responseHeaders.delete(key);
    responseHeaders.set("x-twinpanel-proxy","route-handler");
    return new Response(method==="HEAD"?null:upstream.body,{status:upstream.status,statusText:upstream.statusText,headers:responseHeaders});
  }catch(error){
    const detail=error instanceof Error?error.message:String(error);
    console.error("[TwinPanel API proxy]",method,target.toString(),detail);
    return Response.json({detail:`API proxy failed: ${detail}`},{status:502});
  }
}

export const dynamic="force-dynamic";
export const runtime="nodejs";

export const GET=proxy;
export const POST=proxy;
export const PUT=proxy;
export const PATCH=proxy;
export const DELETE=proxy;
export const OPTIONS=proxy;
export const HEAD=proxy;
