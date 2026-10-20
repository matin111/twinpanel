import type {RuntimeRow} from "./admin-api";

const valueOf=(row:RuntimeRow,...keys:string[])=>{
  for(const key of keys){
    const value=row[key];
    if(value!==undefined&&value!==null)return value;
  }
  return undefined;
};

const numberOf=(row:RuntimeRow,...keys:string[])=>{
  const raw=valueOf(row,...keys);
  const parsed=Number(String(raw??0).replace(/[,٬]/g,""));
  return Number.isFinite(parsed)?parsed:0;
};

const stringOf=(row:RuntimeRow,...keys:string[])=>
  String(valueOf(row,...keys)??"");

export const successfulDashboardPayment=(row:RuntimeRow)=>[
  "paid",
  "approved",
  "auto_verified",
  "verified",
  "completed",
  "fulfilled",
  "success",
  "successful",
].includes(
  stringOf(row,"status","payment_status").toLowerCase()
);

export const dashboardPaymentAmount=(row:RuntimeRow)=>
  numberOf(
    row,
    "payable_amount_toman",
    "base_amount_toman",
    "amount_toman",
    "amount",
    "final_amount_toman",
    "total_toman",
  );

export function revenueSeries(
  payments:RuntimeRow[],
  now:Date=new Date(),
){
  const rows=Array.from({length:30},(_,index)=>{
    const date=new Date(now);
    date.setHours(0,0,0,0);
    date.setDate(date.getDate()-(29-index));
    return {
      key:date.toISOString().slice(0,10),
      date,
      value:0,
    };
  });

  const map=new Map(
    rows.map(item=>[item.key,item])
  );

  for(const payment of payments){
    if(!successfulDashboardPayment(payment))continue;

    const raw=stringOf(
      payment,
      "verified_at",
      "paid_at",
      "submitted_at",
      "created_at",
    );
    if(!raw)continue;

    const date=new Date(raw);
    if(Number.isNaN(date.getTime()))continue;

    const key=new Date(
      date.getFullYear(),
      date.getMonth(),
      date.getDate(),
    ).toISOString().slice(0,10);

    const item=map.get(key);
    if(!item)continue;

    item.value+=dashboardPaymentAmount(payment);
  }

  return rows;
}
