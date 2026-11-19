import assert from "node:assert/strict";
import fs from "node:fs";
import {stripTypeScriptTypes} from "node:module";

const library=fs.readFileSync(new URL("../lib/nova-articles.ts",import.meta.url),"utf8");
const oldUrl="data:text/javascript;charset=utf-8,"+encodeURIComponent(stripTypeScriptTypes(library));
const text=fs.readFileSync(new URL("../lib/nova-blog-rich-text.ts",import.meta.url),"utf8");
const compiled=stripTypeScriptTypes(text.replace('from "./nova-articles"',`from "${oldUrl}"`));
const format=await import("data:text/javascript;charset=utf-8,"+encodeURIComponent(compiled));
const original=await import(oldUrl);

assert.equal(format.safeNovaBlogHref("https://example.com/path?foo=1"),"https://example.com/path?foo=1");
assert.equal(format.safeNovaBlogHref("http://example.com"),"http://example.com");
assert.equal(format.safeNovaBlogHref("#section-2"),"#section-2");
for(const url of ["javascript:alert(1)","data:text/html,hi","file:///etc/passwd","//evil.example","https://user:pass@example.com","https://example.com\nscript"]){
 assert.equal(format.safeNovaBlogHref(url),"",`unsafe href was accepted: ${url}`);
}
assert.equal(format.safeNovaBlogAnchor("my-section"),"my-section");
assert.equal(format.safeNovaBlogAnchor("bad anchor"),"");
assert.equal(format.safeNovaBlogAnchor("123abc"),"");
assert.equal(format.parseNovaBlogInline("[bad](javascript:alert(1))").some(t=>t.kind==="link"),false);
assert.equal(format.parseNovaBlogInline("[good](https://example.com)")[0].kind,"link");
assert.equal(format.parseNovaBlogInline("[size:20]درشت[/size]")[0].size,20);
assert.equal(format.parseNovaBlogInline("[size:99]ناامن[/size]")[0].kind,"text");
assert.equal(format.parseNovaBlogInline("**bold** *italic* [u]underlined[/u] ~~strike~~").map(x=>x.kind).join(","),"bold,text,italic,text,underline,text,strike");
assert.equal(format.parseNovaBlogInline("<script>alert(1)</script>")[0].kind,"text");

const body=[
 "# عنوان اصلی {#my-title}",
 "",
 "[anchor:next-step]",
 "",
 "[align:center]متن وسط‌چین[/align]",
 "",
 "- مورد اول\n- مورد دوم",
 "",
 "1. اول\n2. دوم",
 "",
 "> توضیح ویژه",
 "",
 "| ویژگی | مقدار |\n| --- | --- |\n| سرعت | بالا |",
 "",
 "---",
 "",
 "![عکس معتبر](/v1/storefront/settings/media/nova-multipage-2027/blog-abcdefgh)",
].join("\n");
const blocks=format.parseNovaBlogBlocks(body);
assert.deepEqual(blocks.map(x=>x.kind),["heading","anchor","paragraph","list","list","quote","table","divider","image"]);
assert.equal(blocks[0].anchor,"my-title");
assert.equal(blocks[2].align,"center");
assert.equal(blocks[4].ordered,true);
assert.equal(blocks[8].src,"/v1/storefront/settings/media/nova-multipage-2027/blog-abcdefgh");
assert.equal(format.parseNovaBlogBlocks("![fake](https://evil.example)")[0].kind,"paragraph");
const overrides=original.cleanNovaBlogEntries([{slug:"future-guide",title:"Test",description:"",body:"x".repeat(20000),updated:"2026-11-19",published:true}]);
assert.equal(overrides[0].body.length,20000,"rich articles must not be cut at the old 5000-character limit");
assert.equal(original.novaArticlesWithOverrides([]).length,original.NOVA_ARTICLES.length,"legacy articles must remain visible");
console.log("Nova blog rich-text tests passed:",blocks.length,"block types, safe links, legacy articles, long content.");
