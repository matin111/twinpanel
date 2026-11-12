"use client";

import {useId,useMemo,useState} from "react";
import type {SalesSeriesPoint} from "../lib/sales-analytics-api";
import styles from "./premium-revenue-chart.module.css";

type SeriesKey="subscription_revenue_toman"|"wallet_topup_revenue_toman";
type Pick=(fa:string,en:string)=>string;
type Props={series:SalesSeriesPoint[];pick:Pick};
type XY={x:number;y:number;value:number;index:number};
const W=940,H=310,LEFT=68,RIGHT=22,TOP=34,BOTTOM=45;
const PW=W-LEFT-RIGHT,PH=H-TOP-BOTTOM;
const c=(v:number,min:number,max:number)=>Math.max(min,Math.min(max,v));
const amount=(v:number)=>Math.max(0,Number(v)||0).toLocaleString("fa-IR");
const value=(row:SalesSeriesPoint,key:SeriesKey)=>Math.max(0,Number(row[key]||0));
const sum=(rows:SalesSeriesPoint[],key:SeriesKey)=>rows.reduce((acc,row)=>acc+value(row,key),0);
const compact=(v:number,pick:Pick)=>{
  if(v>=1_000_000_000)return (v/1_000_000_000).toLocaleString("fa-IR",{maximumFractionDigits:1})+" "+pick("میلیارد","B");
  if(v>=1_000_000)return (v/1_000_000).toLocaleString("fa-IR",{maximumFractionDigits:1})+" "+pick("میلیون","M");
  if(v>=1_000)return (v/1_000).toLocaleString("fa-IR",{maximumFractionDigits:1})+" "+pick("هزار","K");
  return amount(v);
};
const dayLabel=(iso:string,pick:Pick,long=false)=>{
  const date=new Date(iso);
  if(Number.isNaN(date.getTime()))return "—";
  return date.toLocaleDateString(pick("fa-IR","en-US"),long?{month:"long",day:"numeric",year:"numeric"}:{month:"short",day:"numeric"});
};

// A monotonic cubic keeps the glowing curve smooth without inventing negative
// revenue or spikes between days. All points remain on the real values.
function smoothPath(points:XY[]){
  if(!points.length)return "";
  if(points.length===1)return "M "+points[0].x+" "+points[0].y;
  const slopes=points.map((point,i)=>{
    const a=points[Math.max(0,i-1)],b=points[Math.min(points.length-1,i+1)];
    if(i===0)return (points[1].y-point.y)/(points[1].x-point.x);
    if(i===points.length-1)return (point.y-points[i-1].y)/(point.x-points[i-1].x);
    const prev=(point.y-a.y)/(point.x-a.x),next=(b.y-point.y)/(b.x-point.x);
    return prev*next<=0?0:Math.sign(prev)*Math.min(Math.abs(prev),Math.abs(next),Math.abs((prev+next)/2));
  });
  let path="M "+points[0].x.toFixed(2)+" "+points[0].y.toFixed(2);
  for(let i=1;i<points.length;i++){
    const a=points[i-1],b=points[i],dx=(b.x-a.x)/3;
    path+=" C "+(a.x+dx).toFixed(2)+" "+(a.y+slopes[i-1]*dx).toFixed(2)+
      " "+(b.x-dx).toFixed(2)+" "+(b.y-slopes[i]*dx).toFixed(2)+
      " "+b.x.toFixed(2)+" "+b.y.toFixed(2);
  }
  return path;
}
const areaPath=(points:XY[],line:string)=>points.length?
  line+" L "+points[points.length-1].x+" "+(TOP+PH)+" L "+points[0].x+" "+(TOP+PH)+" Z":"";

export function PremiumRevenueChart({series,pick}:Props){
  const [days,setDays]=useState<7|14|30>(30);
  const [seriesVisible,setSeriesVisible]=useState<Record<SeriesKey,boolean>>({
    subscription_revenue_toman:true,wallet_topup_revenue_toman:true,
  });
  const [hover,setHover]=useState<number|null>(null);
  const uid=useId().replace(/:/g,"");
  const rows=useMemo(()=>series.slice(-days),[series,days]);
  const geometry=useMemo(()=>{
    const peak=Math.max(1,...rows.flatMap(row=>[
      seriesVisible.subscription_revenue_toman?value(row,"subscription_revenue_toman"):0,
      seriesVisible.wallet_topup_revenue_toman?value(row,"wallet_topup_revenue_toman"):0,
    ]));
    const ceiling=peak*1.14;
    const build=(key:SeriesKey):XY[]=>rows.map((row,index)=>({
      index,
      value:value(row,key),
      x:LEFT+index*PW/Math.max(1,rows.length-1),
      y:TOP+PH-(value(row,key)/ceiling)*PH,
    }));
    const subscription=build("subscription_revenue_toman");
    const wallet=build("wallet_topup_revenue_toman");
    const subscriptionPath=smoothPath(subscription),walletPath=smoothPath(wallet);
    const peakIndex=rows.reduce((best,row,index)=>value(row,"subscription_revenue_toman")>value(rows[best],"subscription_revenue_toman")?index:best,0);
    return {
      subscription,wallet,subscriptionPath,walletPath,
      subscriptionArea:areaPath(subscription,subscriptionPath),
      walletArea:areaPath(wallet,walletPath),
      ceiling,peakIndex,
    };
  },[rows,seriesVisible]);
  const hasData=rows.some(row=>value(row,"subscription_revenue_toman")>0||value(row,"wallet_topup_revenue_toman")>0);
  const chosen=hover!=null&&hover<rows.length?hover:null;
  const selected=chosen==null?null:rows[chosen];
  const x=chosen==null?0:geometry.subscription[chosen]?.x||0;
  const salesTotal=sum(rows,"subscription_revenue_toman");
  const walletTotal=sum(rows,"wallet_topup_revenue_toman");
  const high=rows.length?rows[geometry.peakIndex]:null;
  const highValue=high?value(high,"subscription_revenue_toman"):0;
  const show=({key}:{key:SeriesKey})=>setSeriesVisible(previous=>{
    if(previous[key]&&!previous[key==="subscription_revenue_toman"?"wallet_topup_revenue_toman":"subscription_revenue_toman"])return previous;
    return {...previous,[key]:!previous[key]};
  });
  const selectPointer=(clientX:number,target:SVGSVGElement)=>{
    if(!rows.length)return;
    const bounds=target.getBoundingClientRect();
    if(!bounds.width)return;
    const svgX=(clientX-bounds.left)*W/bounds.width;
    setHover(c(Math.round(((svgX-LEFT)/PW)*Math.max(1,rows.length-1)),0,rows.length-1));
  };
  const tickIndexes=rows.length<=3?rows.map((_,i)=>i):
    Array.from(new Set([0,Math.floor((rows.length-1)/2),rows.length-1]));
  const gradientSubscription="revenue-sub-"+uid;
  const gradientWallet="revenue-wallet-"+uid;
  const glow="revenue-glow-"+uid;

  return <div className={styles.root} dir="rtl">
    <header className={styles.header}>
      <div className={styles.headline}>
        <span className={styles.eyebrow}><i/>{pick("تحلیل زنده فروش","LIVE SALES ANALYTICS")}</span>
        <h2>{pick("نبض فروش","Sales pulse")}</h2>
        <p>{pick("روند فروش اشتراک و شارژ کیف پول، بر اساس تراکنش‌های ثبت‌شده","Subscription sales and wallet top-ups from recorded transactions")}</p>
      </div>
      <div className={styles.period} role="group" aria-label={pick("بازه نمایش نمودار","Chart period")}>
        {([7,14,30] as const).map(n=><button key={n} type="button" aria-pressed={days===n} className={days===n?styles.activePeriod:""} onClick={()=>{setDays(n);setHover(null);}}>{amount(n)} {pick("روز","days")}</button>)}
      </div>
    </header>

    <div className={styles.insightGrid}>
      <div className={styles.insight}>
        <div className={styles.insightLabel}><i className={styles.violetDot}/>{pick("فروش اشتراک","Subscription sales")}</div>
        <strong>{amount(salesTotal)} <small>{pick("تومان","IRR toman")}</small></strong>
        <span>{pick("جمع فروش در بازه انتخابی","Total sales in selected period")}</span>
      </div>
      <div className={styles.insight}>
        <div className={styles.insightLabel}><i className={styles.mintDot}/>{pick("شارژ کیف پول","Wallet top-ups")}</div>
        <strong>{amount(walletTotal)} <small>{pick("تومان","IRR toman")}</small></strong>
        <span>{pick("ورودی کیف پول؛ جدا از درآمد فروش","Wallet inflow, separate from sales revenue")}</span>
      </div>
      <div className={styles.insight}>
        <div className={styles.insightLabel}><span className={styles.peakIcon}>↗</span>{pick("اوج فروش روزانه","Peak sales day")}</div>
        <strong>{amount(highValue)} <small>{pick("تومان","IRR toman")}</small></strong>
        <span>{high&&highValue>0?dayLabel(high.start_at,pick,true):pick("هنوز فروشی ثبت نشده","No sales recorded yet")}</span>
      </div>
    </div>

    <div className={styles.graphShell}>
      <div className={styles.graphTopline}>
        <div className={styles.legend}>
          <button type="button" aria-pressed={seriesVisible.subscription_revenue_toman} className={!seriesVisible.subscription_revenue_toman?styles.dimmed:""} onClick={()=>show({key:"subscription_revenue_toman"})}><i className={styles.violetDot}/>{pick("فروش اشتراک","Subscription sales")}</button>
          <button type="button" aria-pressed={seriesVisible.wallet_topup_revenue_toman} className={!seriesVisible.wallet_topup_revenue_toman?styles.dimmed:""} onClick={()=>show({key:"wallet_topup_revenue_toman"})}><i className={styles.mintDot}/>{pick("شارژ کیف پول","Wallet top-ups")}</button>
        </div>
        <span className={styles.livePill}><i/>{pick("داده واقعی","Real data")}</span>
      </div>

      {hasData?<div className={styles.graphArea}>
        <svg viewBox={"0 0 "+W+" "+H} preserveAspectRatio="xMidYMid meet" className={styles.svg} role="img"
          tabIndex={0}
          aria-label={pick("نمودار تعاملی فروش روزانه. برای مرور روزها از کلیدهای چپ و راست استفاده کنید.","Interactive daily sales chart. Use arrow keys to browse dates.")}
          onPointerMove={e=>selectPointer(e.clientX,e.currentTarget)}
          onPointerLeave={()=>setHover(null)}
          onKeyDown={e=>{
            if(e.key==="ArrowLeft"||e.key==="ArrowRight"){
              e.preventDefault();
              setHover(i=>c((i==null?rows.length-1:i)+(e.key==="ArrowRight"?1:-1),0,rows.length-1));
            }else if(e.key==="Escape")setHover(null);
          }}>
          <defs>
            <linearGradient id={gradientSubscription} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#9178ff" stopOpacity=".40"/>
              <stop offset="56%" stopColor="#9178ff" stopOpacity=".095"/>
              <stop offset="100%" stopColor="#9178ff" stopOpacity="0"/>
            </linearGradient>
            <linearGradient id={gradientWallet} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#23dac6" stopOpacity=".27"/>
              <stop offset="100%" stopColor="#23dac6" stopOpacity="0"/>
            </linearGradient>
            <filter id={glow} x="-60%" y="-70%" width="220%" height="240%">
              <feGaussianBlur stdDeviation="5" result="blur"/>
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
          </defs>
          {[0,.25,.5,.75,1].map((ratio,index)=>{
            const ty=TOP+ratio*PH;
            return <g key={index}>
              <line x1={LEFT} x2={W-RIGHT} y1={ty} y2={ty} className={styles.gridline}/>
              <text x={LEFT-13} y={ty+4} textAnchor="end" className={styles.yLabel}>{compact((1-ratio)*geometry.ceiling,pick)}</text>
            </g>;
          })}
          {seriesVisible.subscription_revenue_toman&&<>
            <path d={geometry.subscriptionArea} fill={"url(#"+gradientSubscription+")"} className={styles.area}/>
            <path d={geometry.subscriptionPath} stroke="#9178ff" strokeWidth="3.6" className={styles.lineGlow} filter={"url(#"+glow+")"}/>
            <path d={geometry.subscriptionPath} stroke="#aa96ff" strokeWidth="3.2" className={styles.line}/>
          </>}
          {seriesVisible.wallet_topup_revenue_toman&&<>
            <path d={geometry.walletArea} fill={"url(#"+gradientWallet+")"} className={styles.area}/>
            <path d={geometry.walletPath} stroke="#23dac6" strokeWidth="2.8" className={styles.line}/>
          </>}
          {seriesVisible.subscription_revenue_toman&&highValue>0&&chosen==null&&<g className={styles.peakMark}>
            <circle cx={geometry.subscription[geometry.peakIndex].x} cy={geometry.subscription[geometry.peakIndex].y} r="10" fill="#9178ff" fillOpacity=".13"/>
            <circle cx={geometry.subscription[geometry.peakIndex].x} cy={geometry.subscription[geometry.peakIndex].y} r="4" fill="#aa96ff" stroke="#e2dafe" strokeWidth="1.5"/>
          </g>}
          {chosen!=null&&<g className={styles.focusLayer}>
            <line x1={x} x2={x} y1={TOP} y2={TOP+PH} stroke="#a4adc2" strokeWidth="1.3" strokeDasharray="4 6" strokeOpacity=".65"/>
            {seriesVisible.subscription_revenue_toman&&<><circle cx={x} cy={geometry.subscription[chosen].y} r="10" fill="#9178ff" fillOpacity=".17"/><circle cx={x} cy={geometry.subscription[chosen].y} r="5.5" fill="#aa96ff" stroke="#fff" strokeWidth="2"/></>}
            {seriesVisible.wallet_topup_revenue_toman&&<><circle cx={x} cy={geometry.wallet[chosen].y} r="9" fill="#23dac6" fillOpacity=".16"/><circle cx={x} cy={geometry.wallet[chosen].y} r="4.5" fill="#23dac6" stroke="#e8ffff" strokeWidth="1.5"/></>}
          </g>}
          {tickIndexes.map(i=><text key={i} x={LEFT+i*PW/Math.max(1,rows.length-1)} y={H-12} textAnchor={i===0?"start":i===rows.length-1?"end":"middle"} className={styles.xLabel}>{dayLabel(rows[i].start_at,pick)}</text>)}
        </svg>
        {selected!=null&&<div className={styles.tooltip} style={{left:c((x/W)*100,19,81)+"%"}}>
          <small>{dayLabel(selected.start_at,pick,true)}</small>
          {seriesVisible.subscription_revenue_toman&&<div><i className={styles.violetDot}/><span>{pick("فروش اشتراک","Sales")}</span><b>{amount(value(selected,"subscription_revenue_toman"))}</b></div>}
          {seriesVisible.wallet_topup_revenue_toman&&<div><i className={styles.mintDot}/><span>{pick("شارژ کیف پول","Wallet")}</span><b>{amount(value(selected,"wallet_topup_revenue_toman"))}</b></div>}
        </div>}
      </div>:<div className={styles.empty}>
        <span>◌</span>
        <b>{pick("در این بازه تراکنشی ثبت نشده","No transactions in this period")}</b>
        <small>{pick("با ثبت فروش یا شارژ کیف پول، روند واقعی اینجا نمایش داده می‌شود.","The trend will appear when sales or wallet credits are recorded.")}</small>
      </div>}
      <div className={styles.graphFooter}>
        <span>{pick("مبالغ به تومان • آخرین داده‌های ثبت‌شده","Amounts in toman • Latest recorded data")}</span>
        <span>{rows.length.toLocaleString("fa-IR")} {pick("روز داده","days of data")}</span>
      </div>
    </div>
  </div>;
}
