import {NextRequest} from "next/server";

const HOP_BY_HOP=new Set([
  "connection","keep-alive","proxy-authenticate","proxy-authorization",
  "te","trailer","transfer-encoding","upgrade","host","content-length"
]);

const backendBase=()=>
  (process.env.TWINPANEL_BACKEND_URL||"http://127.0.0.1:8095").replace(/\/+$/,"");

function responseFrom(upstream:Response,extra:Record<string,string>={}){
  const headers=new Headers(upstream.headers);
  for(const key of ["connection","keep-alive","transfer-encoding","content-length","content-encoding"]){
    headers.delete(key);
  }
  headers.set("x-twinpanel-proxy","subscription-create-compat");
  for(const [key,value] of Object.entries(extra))headers.set(key,value);
  return new Response(upstream.body,{status:upstream.status,statusText:upstream.statusText,headers});
}

function forwardHeaders(request:NextRequest){
  const headers=new Headers();
  request.headers.forEach((value,key)=>{
    if(!HOP_BY_HOP.has(key.toLowerCase()))headers.set(key,value);
  });
  headers.set("content-type","application/json");
  return headers;
}

export const dynamic="force-dynamic";
export const runtime="nodejs";

export async function POST(request:NextRequest){
  let payload:Record<string,unknown>;
  try{
    payload=await request.json() as Record<string,unknown>;
  }catch{
    return Response.json({detail:"بدنه درخواست ساخت اشتراک نامعتبر است"},{status:400});
  }

  const headers=forwardHeaders(request);
  const body=JSON.stringify(payload);

  try{
    // Prefer the newer backend when it is available. It supports per-subscription
    // device_limit and the extended unlimited flags.
    const modern=await fetch(`${backendBase()}/v1/subscriptions/admin-create-v2`,{
      method:"POST",headers,body,cache:"no-store",redirect:"manual"
    });

    if(modern.status!==404&&modern.status!==405){
      return responseFrom(modern,{"x-twinpanel-subscription-create":"v2"});
    }

    // Current production API exposes the legacy POST /v1/subscriptions route.
    // Keep the plan meaningful: an empty protocols array tells the backend to
    // inherit the enabled protocols from the selected plan. Empty traffic/time
    // stay omitted, which the legacy backend stores as unlimited (0).
    const legacyPayload:Record<string,unknown>={
      user_id:payload.user_id,
      plan_id:payload.plan_id,
      node_ids:Array.isArray(payload.node_ids)?payload.node_ids:[],
      protocols:Array.isArray(payload.protocols)?payload.protocols:[]
    };

    if(payload.traffic_gb!==undefined&&payload.traffic_gb!==null&&payload.traffic_gb!=="")legacyPayload.traffic_gb=payload.traffic_gb;
    if(payload.duration_days!==undefined&&payload.duration_days!==null&&payload.duration_days!=="")legacyPayload.duration_days=payload.duration_days;
    if(typeof payload.username==="string"&&payload.username.trim())legacyPayload.username=payload.username.trim();
    if(typeof payload.password==="string"&&payload.password.trim())legacyPayload.password=payload.password.trim();

    const legacy=await fetch(`${backendBase()}/v1/subscriptions`,{
      method:"POST",headers,body:JSON.stringify(legacyPayload),cache:"no-store",redirect:"manual"
    });

    return responseFrom(legacy,{
      "x-twinpanel-subscription-create":"legacy-plan-device-limit"
    });
  }catch(error){
    const detail=error instanceof Error?error.message:String(error);
    console.error("[TwinPanel subscription create compat]",detail);
    return Response.json({detail:`Subscription API proxy failed: ${detail}`},{status:502});
  }
}
