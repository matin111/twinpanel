import type {NextConfig} from "next";

const backend=(process.env.TWINPANEL_BACKEND_URL||"http://127.0.0.1:8095").replace(/\/+$/,"");

const nextConfig:NextConfig={
  reactStrictMode:true,
  poweredByHeader:false,
  async rewrites(){
    return {
      beforeFiles:[
        {
          source:"/v1/:path*",
          destination:`${backend}/v1/:path*`
        }
      ],
      afterFiles:[],
      fallback:[]
    };
  }
};

export default nextConfig;
