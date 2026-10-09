const backendBase=()=> (process.env.TWINPANEL_BACKEND_URL||"http://127.0.0.1:8095").replace(/\/+$/,"");

export const dynamic="force-dynamic";
export const runtime="nodejs";

export async function GET(){
  try{
    const upstream=await fetch(`${backendBase()}/health`,{cache:"no-store"});
    const headers=new Headers(upstream.headers);
    for(const key of ["connection","keep-alive","transfer-encoding","content-length","content-encoding"])headers.delete(key);
    headers.set("x-twinpanel-proxy","route-handler");
    return new Response(upstream.body,{status:upstream.status,statusText:upstream.statusText,headers});
  }catch(error){
    const detail=error instanceof Error?error.message:String(error);
    console.error("[TwinPanel health proxy]",detail);
    return Response.json({ok:false,detail:`Backend health proxy failed: ${detail}`},{status:502});
  }
}
