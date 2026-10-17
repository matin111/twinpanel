import {cpSync, existsSync, mkdirSync, rmSync} from "node:fs";
import {join} from "node:path";

const root=process.cwd();
const standalone=join(root,".next","standalone");

if(!existsSync(join(standalone,"server.js"))){
  throw new Error("Next.js standalone server.js was not generated");
}

const staticSource=join(root,".next","static");
const staticTarget=join(standalone,".next","static");
if(existsSync(staticTarget))rmSync(staticTarget,{recursive:true,force:true});
mkdirSync(join(standalone,".next"),{recursive:true});
cpSync(staticSource,staticTarget,{recursive:true});

const publicSource=join(root,"public");
const publicTarget=join(standalone,"public");
if(existsSync(publicTarget))rmSync(publicTarget,{recursive:true,force:true});
if(existsSync(publicSource))cpSync(publicSource,publicTarget,{recursive:true});

console.log("TwinPanel standalone runtime staged");
