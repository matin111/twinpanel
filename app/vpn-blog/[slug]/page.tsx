import type {Metadata} from "next";
import Link from "next/link";
import {notFound} from "next/navigation";
import {novaArticlesWithOverrides,parseNovaBlogImageMarker,safeNovaBlogImage} from "../../../lib/nova-articles";
import {getStorefrontSeoContext} from "../../../lib/storefront-seo-server";
import styles from "../../../components/store-template-nova-article.module.css";
export const dynamic="force-dynamic";
async function findArticle(slug:string){
 const ctx=await getStorefrontSeoContext();
 if(ctx.activeTemplate!=="nova-multipage-2027")return null;
 return novaArticlesWithOverrides(ctx.templateValues.nova_articles).find(a=>a.slug===slug)||null;
}
export async function generateMetadata({params}:{params:Promise<{slug:string}>}):Promise<Metadata>{
 const article=await findArticle((await params).slug);
 return article?{title:article.title,description:article.description,robots:{index:true,follow:true}}:{title:"مطلب یافت نشد",robots:{index:false}};
}
export default async function Page({params}:{params:Promise<{slug:string}>}){
 const article=await findArticle((await params).slug);
 if(!article)notFound();
 return <main className={styles.page} dir="rtl"><header className={styles.header}><Link href="/">خانه</Link><span>/</span><Link href="/vpn-blog">مجله آموزشی</Link></header><article className={styles.article}>
 {safeNovaBlogImage(article.coverImage)&&<figure className={styles.cover}><img src={safeNovaBlogImage(article.coverImage)} alt={article.title} loading="eager" width={1120} height={590}/></figure>}
 <span className={styles.label}>راهنمای تخصصی VPN</span>
 <h1>{article.title}</h1><p className={styles.lead}>{article.description}</p>
 <div className={styles.meta}>آخرین بازبینی: {article.updated}</div>
 <nav aria-label="فهرست مطلب"><b>در این مقاله</b><ul>{article.sections.map((section,i)=><li key={section.title}><a href={"#section-"+i}>{section.title}</a></li>)}</ul></nav>
 {article.sections.map((section,i)=><section key={section.title} id={"section-"+i}><h2>{section.title}</h2>{section.paragraphs.map((p,j)=>{const photo=parseNovaBlogImageMarker(p);return photo?<figure key={j} className={styles.inlineImage}><img src={photo.src} alt={photo.alt} loading="lazy" width={960} height={640}/><figcaption>{photo.alt}</figcaption></figure>:<p key={j}>{p}</p>;})}</section>)}
 <aside><b>آماده انتخاب سرویس هستید؟</b><p>پیش از خرید، ویژگی‌های پلن و پروتکل‌های فعال آن را بررسی کنید.</p><Link href="/vpn-services#plans">مشاهده اشتراک‌ها ←</Link></aside></article>
 <footer><Link href="/vpn-blog">بازگشت به همه راهنماها ←</Link></footer></main>;
}