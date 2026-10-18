import {readFileSync} from "node:fs";
import {join} from "node:path";
import type {NextConfig} from "next";

function releaseVersion(){
  const explicit=String(process.env.NEXT_PUBLIC_TWINPANEL_VERSION||"").trim();
  if(explicit)return explicit;
  try{
    return readFileSync(join(process.cwd(),"VERSION"),"utf8").trim();
  }catch{
    return "";
  }
}

const nextConfig:NextConfig={
  reactStrictMode:true,
  poweredByHeader:false,
  output:"standalone",
  env:{
    NEXT_PUBLIC_TWINPANEL_VERSION:releaseVersion()
  }
};

export default nextConfig;
