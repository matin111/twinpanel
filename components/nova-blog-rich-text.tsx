import type {ReactNode} from "react";
import {parseNovaBlogBlocks,parseNovaBlogInline,type NovaInline} from "../lib/nova-blog-rich-text";
import styles from "./nova-blog-rich-text.module.css";

function inlineTokens(value:string):ReactNode[]{
 return parseNovaBlogInline(value).map((node,index)=>renderInline(node,index));
}
function renderInline(node:NovaInline,key:number):ReactNode{
 const content=node.children?.map((child,i)=>renderInline(child,i));
 switch(node.kind){
  case "bold":return <strong key={key}>{content}</strong>;
  case "italic":return <em key={key}>{content}</em>;
  case "underline":return <u key={key}>{content}</u>;
  case "strike":return <s key={key}>{content}</s>;
  case "code":return <code key={key}>{node.text}</code>;
  case "link":return <a key={key} href={node.href} target={node.href?.startsWith("#")?undefined:"_blank"} rel={node.href?.startsWith("#")?undefined:"noopener noreferrer nofollow ugc"}>{content}</a>;
  case "size":return <span key={key} style={{fontSize:`${node.size}px`}}>{content}</span>;
  case "color":return <span key={key} className={styles[`color_${node.color}`]||""}>{content}</span>;
  default:return node.text;
 }
}

/** Shared by the admin preview and the public blog. No raw HTML is interpreted. */
export function NovaBlogRichText({source}:{source:string}){
 const blocks=parseNovaBlogBlocks(source);
 return <div className={styles.root} dir="rtl">{blocks.map((block,i)=>{
  switch(block.kind){
   case "heading":{const heading=inlineTokens(block.value);return block.level===2?<h2 key={i} id={block.anchor||undefined}>{heading}</h2>:block.level===3?<h3 key={i} id={block.anchor||undefined}>{heading}</h3>:<h4 key={i} id={block.anchor||undefined}>{heading}</h4>;}
   case "anchor":return <span key={i} id={block.id} className={styles.anchor} aria-hidden="true"/>;
   case "divider":return <hr key={i}/>;
   case "image":return <figure key={i}><img src={block.src} alt={block.alt} loading="lazy"/><figcaption>{block.alt}</figcaption></figure>;
   case "quote":return <blockquote key={i}>{inlineTokens(block.value)}</blockquote>;
   case "list":return block.ordered?<ol key={i}>{block.items.map((item,j)=><li key={j}>{inlineTokens(item)}</li>)}</ol>:<ul key={i}>{block.items.map((item,j)=><li key={j}>{inlineTokens(item)}</li>)}</ul>;
   case "table":return <div key={i} className={styles.tableScroll}><table><thead><tr>{block.rows[0].map((cell,j)=><th key={j}>{inlineTokens(cell)}</th>)}</tr></thead><tbody>{block.rows.slice(1).map((row,j)=><tr key={j}>{row.map((cell,k)=><td key={k}>{inlineTokens(cell)}</td>)}</tr>)}</tbody></table></div>;
   default:return <p key={i} dir="auto" className={block.align?styles[`align_${block.align}`]:undefined}>{inlineTokens(block.value)}</p>;
  }
 })}</div>;
}
