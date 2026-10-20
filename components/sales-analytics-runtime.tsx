"use client";

import {useEffect,useMemo,useState} from "react";
import {salesAnalyticsApi,SalesAnalyticsResponse,SalesRange,SalesSeriesPoint} from "../lib/sales-analytics-api";
import {useI18n} from "../lib/i18n";
import {Card,Shell} from "./ui";
import {PortalShell} from "./portal-shells";

const money=(value:number)=>`${Number(value||0).toLocaleString("fa-IR")} تومان`;
const compactMoney=(value:number)=>{
  const n=Number(value||0);
  if(n>=1_000_000_000)return `${(n/1_000_000_000).toLocaleString("fa-IR",{maximumFractionDigits:1})} میلیارد`;
  if(n>=1_000_000)return `${(n/1_000_000).toLocaleString("fa-IR",{maximumFractionDigits:1})} میلیون`;
  if(n>=1_000)return `${(n/1_000).toLocaleString("fa-IR",{maximumFractionDigits:1})} هزار`;
  return n.toLocaleString("fa-IR");
};

const rangeItems:{key:SalesRange;fa:string;en:string}[]=[
  {key:"daily",fa:"روزانه",en:"Daily"},
  {key:"weekly",fa:"هفتگی",en:"Weekly"},
  {key:"monthly",fa:"ماهانه",en:"Monthly"},
  {key:"yearly",fa:"سالانه",en:"Yearly"},
];

function periodLabel(point:SalesSeriesPoint,range:SalesRange){
  const date=new Date(point.start_at);
  if(range==="yearly")return date.toLocaleDateString("fa-IR",{year:"numeric"});
  if(range==="monthly")return date.toLocaleDateString("fa-IR",{year:"numeric",month:"short"});
  if(range==="weekly")return date.toLocaleDateString("fa-IR",{month:"short",day:"numeric"});
  return date.toLocaleDateString("fa-IR",{month:"short",day:"numeric"});
}

function chartGeometry(series:SalesSeriesPoint[]){
  const width=900;
  const height=320;
  const left=72;
  const right=20;
  const top=24;
  const bottom=48;
  const plotWidth=width-left-right;
  const plotHeight=height-top-bottom;
  const max=Math.max(1,...series.map(row=>Number(row.revenue_toman||0)));
  const denom=Math.max(1,series.length-1);
  const points=series.map((row,index)=>{
    const x=left+(index/denom)*plotWidth;
    const y=top+plotHeight-(Number(row.revenue_toman||0)/max)*plotHeight;
    return {x,y,row,index};
  });
  const line=points.map(point=>`${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  const area=points.length?`${left},${top+plotHeight} ${line} ${left+plotWidth},${top+plotHeight}`:"";
  const ticks=Array.from({length:5},(_,index)=>{
    const ratio=index/4;
    return {
      y:top+ratio*plotHeight,
      value:Math.round(max*(1-ratio)),
    };
  });
  return {width,height,left,right,top,bottom,plotWidth,plotHeight,max,points,line,area,ticks};
}

function sourceLabel(key:string,pick:(fa:string,en:string)=>string){
  const labels:Record<string,[string,string]>={
    card:["کارت به کارت","Card transfer"],
    usdt_bep20:["USDT BEP20","USDT BEP20"],
    crypto:["ارز دیجیتال","Crypto"],
    bot_sale:["فروش ربات","Bot sale"],
    bot_renewal:["تمدید ربات","Bot renewal"],
    direct_sale:["فروش مستقیم","Direct sale"],
    unknown:["سایر","Other"],
  };
  const item=labels[key]||[key,key];
  return pick(item[0],item[1]);
}

function SalesAnalyticsContent({scope}:{scope:"admin"|"reseller"}){
  const {pick}=useI18n();
  const [range,setRange]=useState<SalesRange>("daily");
  const [data,setData]=useState<SalesAnalyticsResponse|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [hoverIndex,setHoverIndex]=useState<number|null>(null);

  useEffect(()=>{
    let alive=true;
    setLoading(true);
    setError("");
    setHoverIndex(null);
    const task=scope==="admin"?salesAnalyticsApi.admin(range):salesAnalyticsApi.reseller(range);
    task.then(value=>{if(alive)setData(value);}).catch(reason=>{if(alive)setError(reason instanceof Error?reason.message:String(reason));}).finally(()=>{if(alive)setLoading(false);});
    return()=>{alive=false};
  },[range,scope]);

  const series=data?.series||[];
  const chart=useMemo(()=>chartGeometry(series),[series]);
  const activePoint=hoverIndex==null?null:chart.points[hoverIndex]||null;
  const xLabelIndexes=useMemo(()=>{
    if(series.length<=5)return series.map((_,index)=>index);
    return Array.from(new Set([0,Math.floor((series.length-1)*.25),Math.floor((series.length-1)*.5),Math.floor((series.length-1)*.75),series.length-1]));
  },[series]);

  const periodCards=[
    {key:"today",title:pick("فروش امروز","Today"),icon:"◷"},
    {key:"week",title:pick("فروش این هفته","This week"),icon:"▥"},
    {key:"month",title:pick("فروش این ماه","This month"),icon:"▦"},
    {key:"year",title:pick("فروش امسال","This year"),icon:"◈"},
  ] as const;

  return <div className="page sales-analytics-page">
    <div className="page-head sales-analytics-head">
      <div>
        <h1>{pick("آمار فروش","Sales Analytics")}</h1>
      </div>
      <div className="sales-range-switch" role="tablist" aria-label={pick("بازه گزارش","Report range")}>
        {rangeItems.map(item=><button key={item.key} type="button" className={range===item.key?"active":""} onClick={()=>setRange(item.key)}>{pick(item.fa,item.en)}</button>)}
      </div>
    </div>

    {error&&<div className="sales-error"><b>{pick("دریافت آمار فروش ناموفق بود","Could not load sales analytics")}</b><span>{error}</span></div>}

    <div className="sales-period-grid">
      {periodCards.map(item=>{
        const metric=data?.summary[item.key];
        return <Card key={item.key} className="sales-period-card">
          <span className="sales-period-icon">{item.icon}</span>
          <div><small>{item.title}</small><b>{loading&&!data?"…":money(metric?.revenue_toman||0)}</b><em>{(metric?.sales_count||0).toLocaleString("fa-IR")} {pick("فروش موفق","successful sales")}</em></div>
        </Card>;
      })}
    </div>

    <Card className="sales-chart-card">
      <div className="sales-card-head">
        <div>
          <h2>{pick("روند درآمد فروش","Sales revenue trend")}</h2>
        </div>
        <div className="sales-selected-summary">
          <span><small>{pick("درآمد بازه","Period revenue")}</small><b>{money(data?.selected.revenue_toman||0)}</b></span>
          <span><small>{pick("تعداد فروش","Sales")}</small><b>{(data?.selected.sales_count||0).toLocaleString("fa-IR")}</b></span>
          <span><small>{pick("میانگین هر فروش","Average sale")}</small><b>{money(data?.selected.average_sale_toman||0)}</b></span>
        </div>
      </div>

      <div className={`sales-chart-wrap ${loading?"loading":""}`} onMouseLeave={()=>setHoverIndex(null)}>
        {series.length?<svg viewBox={`0 0 ${chart.width} ${chart.height}`} role="img" aria-label={pick("نمودار درآمد فروش","Sales revenue chart")}>
          <defs>
            <linearGradient id={`salesArea-${scope}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#8b5cf6" stopOpacity=".36"/>
              <stop offset="1" stopColor="#8b5cf6" stopOpacity=".015"/>
            </linearGradient>
          </defs>
          {chart.ticks.map((tick,index)=><g key={index}>
            <line x1={chart.left} y1={tick.y} x2={chart.width-chart.right} y2={tick.y} className="sales-grid-line"/>
            <text x={chart.left-12} y={tick.y+5} textAnchor="end" className="sales-axis-label">{compactMoney(tick.value)}</text>
          </g>)}
          <polygon points={chart.area} fill={`url(#salesArea-${scope})`}/>
          <polyline points={chart.line} className="sales-chart-line"/>
          {chart.points.map(point=><g key={point.index}>
            <rect x={Math.max(chart.left,point.x-14)} y={chart.top} width="28" height={chart.plotHeight} fill="transparent" onMouseEnter={()=>setHoverIndex(point.index)} onPointerEnter={()=>setHoverIndex(point.index)}/>
            <circle cx={point.x} cy={point.y} r={hoverIndex===point.index?6:3.5} className={hoverIndex===point.index?"sales-chart-point active":"sales-chart-point"}/>
          </g>)}
          {xLabelIndexes.map(index=>{
            const point=chart.points[index];
            if(!point)return null;
            return <text key={index} x={point.x} y={chart.height-14} textAnchor={index===0?"start":index===series.length-1?"end":"middle"} className="sales-axis-label sales-x-label">{periodLabel(point.row,range)}</text>;
          })}
        </svg>:<div className="sales-empty">{loading?pick("در حال دریافت نمودار...","Loading chart..."):pick("برای این بازه فروش تأییدشده‌ای ثبت نشده است","No confirmed sales in this period")}</div>}

        {activePoint&&<div className="sales-tooltip" style={{left:`${Math.min(88,Math.max(12,(activePoint.x/chart.width)*100))}%`,top:`${Math.max(8,(activePoint.y/chart.height)*100-4)}%`}}>
          <small>{periodLabel(activePoint.row,range)}</small>
          <b>{money(activePoint.row.revenue_toman)}</b>
          <span>{activePoint.row.sales_count.toLocaleString("fa-IR")} {pick("فروش","sales")}</span>
        </div>}
      </div>
    </Card>

    <div className="sales-bottom-grid">
      <Card className="sales-breakdown-card">
        <div className="sales-card-head compact"><div><small>{pick("ترکیب درآمد بازه","Period mix")}</small><h2>{scope==="admin"?pick("روش‌های پرداخت","Payment methods"):pick("مسیرهای فروش","Sales channels")}</h2></div></div>
        <div className="sales-breakdown-list">
          {(data?.breakdown||[]).length?(data?.breakdown||[]).map((item,index)=>{
            const total=Math.max(1,data?.selected.revenue_toman||0);
            const share=Math.round((item.revenue_toman/total)*100);
            return <div className="sales-breakdown-row" key={item.key}>
              <div><span className="sales-rank">{index+1}</span><div><b>{sourceLabel(item.key,pick)}</b><small>{item.sales_count.toLocaleString("fa-IR")} {pick("فروش","sales")} · {share.toLocaleString("fa-IR")}٪</small></div></div>
              <strong>{money(item.revenue_toman)}</strong>
              <span className="sales-share-track"><i style={{width:`${Math.min(100,share)}%`}}/></span>
            </div>;
          }):<div className="sales-empty small">{pick("داده‌ای برای تفکیک درآمد وجود ندارد","No revenue breakdown yet")}</div>}
        </div>
      </Card>
    </div>

    <style jsx>{`
      .sales-analytics-page{display:grid;gap:18px}
      .sales-analytics-head{align-items:flex-end;gap:18px}
      .sales-range-switch{display:flex;gap:4px;padding:4px;border:1px solid rgba(139,92,246,.18);border-radius:14px;background:rgba(139,92,246,.055)}
      .sales-range-switch button{border:0;background:transparent;color:inherit;padding:9px 14px;border-radius:10px;font:inherit;font-size:12px;cursor:pointer;opacity:.68;transition:.18s ease}
      .sales-range-switch button:hover{opacity:1;background:rgba(139,92,246,.08)}
      .sales-range-switch button.active{opacity:1;color:#fff;background:linear-gradient(135deg,#7c3aed,#8b5cf6);box-shadow:0 8px 24px rgba(124,58,237,.22)}
      .sales-error{display:flex;gap:10px;align-items:center;padding:12px 14px;border:1px solid rgba(239,68,68,.3);border-radius:14px;background:rgba(239,68,68,.08);font-size:13px}
      .sales-error span{opacity:.72}
      .sales-period-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
      :global(.sales-period-card){display:flex;align-items:center;gap:13px;min-width:0}
      .sales-period-icon{width:42px;height:42px;display:grid;place-items:center;border-radius:13px;background:rgba(139,92,246,.11);color:#8b5cf6;font-size:18px;flex:0 0 auto}
      :global(.sales-period-card)>div{min-width:0;display:grid;gap:5px}
      :global(.sales-period-card small){opacity:.62;font-size:11px}
      :global(.sales-period-card b){font-size:18px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      :global(.sales-period-card em){font-style:normal;font-size:11px;color:#8b5cf6}
      :global(.sales-chart-card){overflow:visible}
      .sales-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:14px}
      .sales-card-head.compact{margin-bottom:10px}
      .sales-card-head small{opacity:.56;font-size:11px}
      .sales-card-head h2{font-size:16px;margin:4px 0 0}
      .sales-selected-summary{display:grid;grid-template-columns:repeat(3,minmax(125px,1fr));gap:8px}
      .sales-selected-summary span{display:grid;gap:4px;padding:8px 12px;border-radius:11px;background:rgba(139,92,246,.06);border:1px solid rgba(139,92,246,.12)}
      .sales-selected-summary b{font-size:12px;white-space:nowrap}
      .sales-chart-wrap{position:relative;min-height:320px;border-radius:16px;overflow:hidden;background:linear-gradient(180deg,rgba(139,92,246,.04),rgba(139,92,246,.012))}
      .sales-chart-wrap.loading{opacity:.68}
      .sales-chart-wrap svg{display:block;width:100%;height:auto;min-height:300px;overflow:visible}
      .sales-grid-line{stroke:currentColor;stroke-opacity:.09;stroke-width:1}
      .sales-axis-label{fill:currentColor;fill-opacity:.5;font-size:11px;font-family:inherit}
      .sales-x-label{font-size:10px}
      .sales-chart-line{fill:none;stroke:#8b5cf6;stroke-width:4;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 7px 10px rgba(124,58,237,.2))}
      .sales-chart-point{fill:#8b5cf6;stroke:#fff;stroke-width:2;transition:r .12s ease}
      .sales-chart-point.active{fill:#7c3aed;stroke-width:3}
      .sales-tooltip{position:absolute;transform:translate(-50%,-100%);pointer-events:none;z-index:4;display:grid;gap:3px;min-width:145px;padding:10px 12px;border-radius:12px;background:rgba(22,17,36,.95);color:#fff;box-shadow:0 14px 35px rgba(0,0,0,.22);font-size:11px}
      .sales-tooltip small{opacity:.65}.sales-tooltip b{font-size:13px}.sales-tooltip span{opacity:.72}
      .sales-empty{height:300px;display:grid;place-items:center;opacity:.55;font-size:13px}.sales-empty.small{height:auto;min-height:100px}
      .sales-bottom-grid{display:grid;grid-template-columns:1fr;gap:14px}
      .sales-breakdown-list{display:grid;gap:9px}
      .sales-breakdown-row{position:relative;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:9px 14px;padding:11px 0}
      .sales-breakdown-row>div{display:flex;align-items:center;gap:10px}.sales-breakdown-row>div>div{display:grid;gap:3px}
      .sales-breakdown-row b{font-size:12px}.sales-breakdown-row small{font-size:10px;opacity:.55}.sales-breakdown-row strong{font-size:12px;align-self:center}
      .sales-rank{width:28px;height:28px;display:grid;place-items:center;border-radius:9px;background:rgba(139,92,246,.09);color:#8b5cf6;font-size:11px;font-weight:700}
      .sales-share-track{grid-column:1/-1;height:4px;border-radius:99px;background:rgba(139,92,246,.08);overflow:hidden}.sales-share-track i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#7c3aed,#a78bfa)}
      @media(max-width:1100px){.sales-period-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.sales-card-head{display:grid}.sales-selected-summary{grid-template-columns:repeat(3,1fr)}.sales-bottom-grid{grid-template-columns:1fr}}
      @media(max-width:680px){.sales-analytics-head{align-items:stretch}.sales-range-switch{width:100%;overflow:auto}.sales-range-switch button{flex:1;white-space:nowrap}.sales-period-grid{grid-template-columns:1fr}.sales-selected-summary{grid-template-columns:1fr}.sales-chart-wrap{min-height:260px}.sales-chart-wrap svg{min-height:250px}.sales-breakdown-row{grid-template-columns:1fr}.sales-breakdown-row strong{padding-inline-start:38px}.sales-share-track{grid-column:1}.sales-card-head{gap:10px}}
    `}</style>
  </div>;
}

export function AdminSalesAnalyticsRuntime(){
  return <Shell active="/admin/sales-analytics"><SalesAnalyticsContent scope="admin"/></Shell>;
}

export function ResellerSalesAnalyticsRuntime(){
  return <PortalShell type="reseller" active="/reseller/sales-analytics"><SalesAnalyticsContent scope="reseller"/></PortalShell>;
}
