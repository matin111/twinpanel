/** A deliberately small, HTML-free blog markup dialect. Untrusted article data
 * is parsed to typed tokens and rendered by React (never innerHTML). */
import {parseNovaBlogImageMarker} from "./nova-articles";

export const NOVA_BLOG_BODY_LIMIT=30000;
export const NOVA_FONT_SIZES=[12,14,16,18,20,24,28,32] as const;
export const NOVA_TEXT_COLORS=["default","blue","purple","green","orange","red"] as const;
export type NovaColor=typeof NOVA_TEXT_COLORS[number];
export type NovaAlign="right"|"center"|"left";
export type NovaInline={kind:"text"|"bold"|"italic"|"underline"|"strike"|"code"|"link"|"size"|"color";text?:string;children?:NovaInline[];href?:string;size?:number;color?:NovaColor};
export type NovaBlogBlock=
 | {kind:"paragraph"|"quote";value:string;align?:NovaAlign}
 | {kind:"heading";level:2|3|4;value:string;anchor?:string}
 | {kind:"list";ordered:boolean;items:string[]}
 | {kind:"image";src:string;alt:string}
 | {kind:"anchor";id:string}
 | {kind:"table";rows:string[][]}
 | {kind:"divider"};

export function safeNovaBlogAnchor(value:string):string{
 const id=value.trim().toLowerCase();
 return /^[a-z][a-z0-9_-]{0,63}$/.test(id)?id:"";
}
export function safeNovaBlogHref(value:string):string{
 const href=value.trim();
 if(!href||href.length>2048||/[\u0000-\u001f\u007f]/.test(href))return "";
 if(href.startsWith("#")){const id=safeNovaBlogAnchor(href.slice(1));return id?`#${id}`:"";}
 try{
  const parsed=new URL(href);
  return (parsed.protocol==="https:"||parsed.protocol==="http:")&&!parsed.username&&!parsed.password?href:"";
 }catch{return "";}
}

/** Recognises only balanced, explicit formatting patterns; unsupported markup is text. */
export function parseNovaBlogInline(input:string,depth=0):NovaInline[]{
 if(depth>5)return [{kind:"text",text:input}];
 const tokens:NovaInline[]=[];
 const pattern=/\[([^\]\r\n]{1,180})\]\(([^)\r\n]{1,2048})\)|\[size:(\d{2})\]([\s\S]*?)\[\/size\]|\[color:(blue|purple|green|orange|red|default)\]([\s\S]*?)\[\/color\]|\[u\]([\s\S]*?)\[\/u\]|\*\*([^*\n]+)\*\*|~~([^~\n]+)~~|\*([^*\n]+)\*|`([^`\n]+)`/g;
 let cursor=0;
 for(const match of input.matchAll(pattern)){
  const index=match.index??0;
  if(index>cursor)tokens.push({kind:"text",text:input.slice(cursor,index)});
  const all=match[0];
  if(match[1]!==undefined){
   const href=safeNovaBlogHref(match[2]);
   tokens.push(href?{kind:"link",href,children:parseNovaBlogInline(match[1],depth+1)}:{kind:"text",text:all});
  }else if(match[3]!==undefined){
   const size=Number(match[3]);
   tokens.push((NOVA_FONT_SIZES as readonly number[]).includes(size)?{kind:"size",size,children:parseNovaBlogInline(match[4],depth+1)}:{kind:"text",text:all});
  }else if(match[5]!==undefined){tokens.push({kind:"color",color:match[5] as NovaColor,children:parseNovaBlogInline(match[6],depth+1)});}
  else if(match[7]!==undefined){tokens.push({kind:"underline",children:parseNovaBlogInline(match[7],depth+1)});}
  else if(match[8]!==undefined){tokens.push({kind:"bold",children:parseNovaBlogInline(match[8],depth+1)});}
  else if(match[9]!==undefined){tokens.push({kind:"strike",children:parseNovaBlogInline(match[9],depth+1)});}
  else if(match[10]!==undefined){tokens.push({kind:"italic",children:parseNovaBlogInline(match[10],depth+1)});}
  else{tokens.push({kind:"code",text:match[11]});}
  cursor=index+all.length;
 }
 if(cursor<input.length)tokens.push({kind:"text",text:input.slice(cursor)});
 return tokens;
}

const tableCells=(line:string)=>line.trim().replace(/^\|/,"").replace(/\|$/,"").split("|").map(x=>x.trim()).slice(0,8);
export function parseNovaBlogBlocks(source:string):NovaBlogBlock[]{
 const lines=source.replace(/\r\n?/g,"\n").split("\n");
 const blocks:NovaBlogBlock[]=[];
 for(let i=0;i<lines.length && blocks.length<350;){
  const raw=lines[i].trim();
  if(!raw){i++;continue;}
  const photo=parseNovaBlogImageMarker(raw);
  if(photo){blocks.push({kind:"image",...photo});i++;continue;}
  const anchor=/^\[anchor:([^\]\n]+)\]$/.exec(raw);
  if(anchor){const id=safeNovaBlogAnchor(anchor[1]);if(id)blocks.push({kind:"anchor",id});else blocks.push({kind:"paragraph",value:raw});i++;continue;}
  if(/^(-{3,}|\*{3,})$/.test(raw)){blocks.push({kind:"divider"});i++;continue;}
  const heading=/^(#{1,3})\s+(.+?)(?:\s+\{#([a-zA-Z0-9_-]+)\})?$/.exec(raw);
  if(heading){blocks.push({kind:"heading",level:Math.min(4,heading[1].length+1) as 2|3|4,value:heading[2],anchor:heading[3]?safeNovaBlogAnchor(heading[3]):undefined});i++;continue;}
  if(i+1<lines.length&&raw.startsWith("|")&&/^\|?[\s:|-]+\|?$/.test(lines[i+1].trim())&&lines[i+1].includes("-")){
   const rows=[tableCells(raw)];i+=2;
   while(i<lines.length&&lines[i].trim().startsWith("|")&&rows.length<31){rows.push(tableCells(lines[i]));i++;}
   blocks.push({kind:"table",rows});continue;
  }
  const bullet=/^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+)$/.exec(lines[i]);
  if(bullet){const ordered=/^\s*\d+[.)]\s+/.test(lines[i]);const items:string[]=[];
   while(i<lines.length&&items.length<100){const item=/^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+)$/.exec(lines[i]);if(!item||/^\s*\d+[.)]\s+/.test(lines[i])!==ordered)break;items.push(item[1]);i++;}
   blocks.push({kind:"list",ordered,items});continue;
  }
  if(raw.startsWith(">")){const quote:string[]=[];while(i<lines.length&&lines[i].trim().startsWith(">")){quote.push(lines[i].trim().replace(/^>\s?/,""));i++;}blocks.push({kind:"quote",value:quote.join("\n")});continue;}
  const aligned=/^\[align:(right|center|left)\]([\s\S]*?)\[\/align\]$/.exec(raw);
  if(aligned){blocks.push({kind:"paragraph",align:aligned[1] as NovaAlign,value:aligned[2]});i++;continue;}
  const paragraph:string[]=[];
  while(i<lines.length&&lines[i].trim()&&paragraph.length<60){
   if(paragraph.length&&(/^(#{1,3}\s|\[anchor:|\|\s|[-*+]\s|\d+[.)]\s|>\s|---)/.test(lines[i].trim())||parseNovaBlogImageMarker(lines[i].trim())))break;
   paragraph.push(lines[i]);i++;
  }
  blocks.push({kind:"paragraph",value:paragraph.join("\n")});
 }
 return blocks;
}
