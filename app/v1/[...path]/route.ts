import {NextRequest} from "next/server";

export const dynamic="force-dynamic";
export const runtime="nodejs";

const hopByHop=new Set([
  "connection","keep-alive","proxy-authenticate","proxy-authorization",
  "te","trailer","transfer-encoding","upgrade","host","content-length"
]);

function backendBase(){
  return (process.env.TWINPANEL_BACKEND_URL||"http://127.0.0.1:8095").replace(/\/+$/,"");
}

function upstreamHeaders(request:NextRequest){
  const headers=new Headers();
  request.headers.forEach((value,key)=>{
    const lower=key.toLowerCase();
    if(!hopByHop.has(lower)&&lower!=="cookie")headers.set(key,value);
  });
  headers.set("accept-encoding","identity");
  return headers;
}

function responseHeaders(source:Headers){
  const headers=new Headers();
  for(const key of ["content-type","content-disposition","cache-control","etag","last-modified","location"]){
    const value=source.get(key);
    if(value)headers.set(key,value);
  }
  headers.set("x-twinpanel-proxy","runtime");
  return headers;
}

async function proxy(request:NextRequest,ctx:{params:Promise<{path:string[]}>}){
  const {path}=await ctx.params;
  const url=new URL(request.url);
  const target=`${backendBase()}/v1/${path.map(encodeURIComponent).join("/")}${url.search}`;

  try{
    const method=request.method.toUpperCase();
    const body=(method==="GET"||method==="HEAD")?undefined:await request.arrayBuffer();
    const upstream=await fetch(target,{
      method,
      headers:upstreamHeaders(request),
      body,
      redirect:"manual",
      cache:"no-store",
      signal:AbortSignal.timeout(20000)
    });

    const bytes=method==="HEAD"?null:await upstream.arrayBuffer();
    return new Response(bytes,{
      status:upstream.status,
      statusText:upstream.statusText,
      headers:responseHeaders(upstream.headers)
    });
  }catch(error){
    console.error("[TwinPanel API proxy] upstream unavailable",error);
    return Response.json({
      detail:"Backend API is unavailable",
      code:"TWINPANEL_UPSTREAM_UNAVAILABLE"
    },{status:502,headers:{"x-twinpanel-proxy":"runtime"}});
  }
}

export const GET=proxy;
export const POST=proxy;
export const PUT=proxy;
export const PATCH=proxy;
export const DELETE=proxy;
export const OPTIONS=proxy;
export const HEAD=proxy;
