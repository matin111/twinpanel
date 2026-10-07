import type {NextConfig} from "next";

const backend=(process.env.TWINPANEL_BACKEND_URL||"").replace(/\/+$/,"");

const nextConfig:NextConfig={
  reactStrictMode:true,
  poweredByHeader:false,
  async rewrites(){
    if(!backend)return [];
    return [
      {source:"/v1/:path*",destination:`${backend}/v1/:path*`},
      {source:"/health",destination:`${backend}/health`}
    ];
  }
};

export default nextConfig;
