"use client";

import {useEffect} from "react";
import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";

type LiveItem={subscription_id:number;online:boolean;protocols?:string[];last_seen_at?:string|null};
type LivePayload={items?:LiveItem[]};
type BulkOperation="add_traffic"|"subtract_traffic"|"add_days"|"subtract_days";
type BulkResult={ok?:boolean;operation?:BulkOperation;amount?:number;total?:number;updated?:number;skipped?:number;clamped?:number};

const protocolLabel=(value:string)=>({
  cisco:"Cisco",
  openvpn:"OpenVPN",
  wireguard:"WireGuard",
  l2tp:"L2TP",
  xray:"Xray",
  v2ray:"Xray",
} as Record<string,string>)[String(value||"").toLowerCase()]||value;

function rowSubscriptionId(row:HTMLTableRowElement){
  const text=row.textContent||"";
  const match=text.match(/MV-\s*(\d+)/i);
  return match?Number(match[1]):0;
}

function statusCell(row:HTMLTableRowElement){
  return row.cells.length>=2?row.cells[row.cells.length-2] as HTMLTableCellElement:null;
}

export function AdminSubscriptionLiveTable(){
  useEffect(()=>{
    if(typeof window==="undefined"||window.location.pathname!=="/admin/subscriptions")return;

    let disposed=false;
    let timer:number|undefined;
    let bulkTimer:number|undefined;
    let observer:MutationObserver|undefined;
    let observedBody:HTMLTableSectionElement|null=null;
    let frame:number|undefined;
    let loaded=false;
    let lastSuccessAt=0;
    // A failed or delayed poll must not masquerade as a confirmed disconnect.
    const STALE_AFTER_MS=45000;
    let inFlight=false;
    let controller:AbortController|undefined;
    let bulkModal:HTMLDivElement|null=null;
    const states=new Map<number,LiveItem>();

    const english=()=>document.documentElement.lang==="en";
    const tr=(fa:string,en:string)=>english()?en:fa;

    const closeBulkModal=()=>{
      bulkModal?.remove();
      bulkModal=null;
    };

    const refreshSubscriptionsTable=()=>{
      document.querySelector<HTMLButtonElement>(".legacy-subscriptions-page .runtime-toolbar button.ghost")?.click();
    };

    const openBulkModal=()=>{
      if(bulkModal||disposed)return;
      const token=getCustomerToken();
      if(!token)return;

      const modal=document.createElement("div");
      modal.className="runtime-modal";
      modal.setAttribute("role","dialog");
      modal.setAttribute("aria-modal","true");
      modal.dataset.subscriptionBulkModal="1";

      const backdrop=document.createElement("button");
      backdrop.className="runtime-modal-bg";
      backdrop.type="button";
      backdrop.setAttribute("aria-label",tr("بستن","Close"));
      backdrop.addEventListener("click",closeBulkModal);

      const card=document.createElement("div");
      card.className="runtime-modal-card";

      const head=document.createElement("div");
      head.className="card-head";
      const titleWrap=document.createElement("div");
      const title=document.createElement("b");
      title.textContent=tr("مدیریت گروهی اشتراک‌ها","Bulk subscription management");
      const sub=document.createElement("small");
      sub.textContent=tr("یک عملیات روی همه اشتراک‌های قابل‌ویرایش اعمال می‌شود","One operation will be applied to all editable subscriptions");
      titleWrap.append(title,sub);
      const close=document.createElement("button");
      close.type="button";
      close.className="icon-button";
      close.textContent="×";
      close.addEventListener("click",closeBulkModal);
      head.append(titleWrap,close);

      const grid=document.createElement("div");
      grid.className="setting-grid";

      const operationLabel=document.createElement("label");
      operationLabel.className="field";
      const operationText=document.createElement("span");
      operationText.textContent=tr("عملیات","Operation");
      const operation=document.createElement("select");
      const options:Array<[BulkOperation,string,string]>=[
        ["add_traffic","افزایش حجم","Add traffic"],
        ["subtract_traffic","کاهش حجم","Reduce traffic"],
        ["add_days","افزایش روز","Add days"],
        ["subtract_days","کاهش روز","Reduce days"],
      ];
      for(const [value,fa,en] of options){
        const option=document.createElement("option");
        option.value=value;
        option.textContent=tr(fa,en);
        operation.appendChild(option);
      }
      operationLabel.append(operationText,operation);

      const amountLabel=document.createElement("label");
      amountLabel.className="field";
      const amountText=document.createElement("span");
      const amount=document.createElement("input");
      amount.type="number";
      amount.min="0.1";
      amount.step="0.1";
      amount.value="10";
      amount.inputMode="decimal";
      const syncAmountUnit=()=>{
        const isDays=operation.value==="add_days"||operation.value==="subtract_days";
        amountText.textContent=isDays?tr("مقدار (روز)","Amount (days)"):tr("مقدار (GB)","Amount (GB)");
        amount.step=isDays?"1":"0.1";
        amount.min=isDays?"1":"0.1";
        if(isDays&&Number(amount.value)%1!==0)amount.value=String(Math.max(1,Math.round(Number(amount.value)||1)));
      };
      operation.addEventListener("change",syncAmountUnit);
      syncAmountUnit();
      amountLabel.append(amountText,amount);
      grid.append(operationLabel,amountLabel);

      const note=document.createElement("div");
      note.className="runtime-info";
      note.textContent=tr(
        "اشتراک لغوشده رد می‌شود. حجم نامحدود در عملیات حجم تغییر نمی‌کند. کاهش حجم پایین‌تر از مصرف واقعی نمی‌رود و کاهش روز پایین‌تر از زمان فعلی Clamp می‌شود.",
        "Canceled subscriptions are skipped. Unlimited traffic is unchanged by traffic operations. Traffic reduction never goes below actual usage and day reduction is clamped at the current time."
      );

      const result=document.createElement("div");
      result.style.display="none";

      const actions=document.createElement("div");
      actions.className="modalActions";
      const cancel=document.createElement("button");
      cancel.type="button";
      cancel.className="ghost";
      cancel.textContent=tr("انصراف","Cancel");
      cancel.addEventListener("click",closeBulkModal);
      const apply=document.createElement("button");
      apply.type="button";
      apply.className="primary";
      apply.textContent=tr("اعمال روی همه اشتراک‌ها","Apply to all subscriptions");

      apply.addEventListener("click",async()=>{
        const numeric=Number(amount.value);
        if(!Number.isFinite(numeric)||numeric<=0){
          result.className="runtime-error";
          result.textContent=tr("مقدار معتبر وارد کنید","Enter a valid amount");
          result.style.display="block";
          return;
        }
        const selected=operation.value as BulkOperation;
        const selectedTitle=operation.selectedOptions[0]?.textContent||selected;
        const unit=selected.includes("days")?tr("روز","days"):"GB";
        if(!window.confirm(tr(`«${selectedTitle}» به مقدار ${numeric} ${unit} روی همه اشتراک‌ها اعمال شود؟`,`Apply “${selectedTitle}” by ${numeric} ${unit} to all subscriptions?`)))return;

        apply.disabled=true;
        cancel.disabled=true;
        apply.textContent=tr("در حال اعمال…","Applying…");
        result.style.display="none";
        try{
          const response=await fetch(`${API_BASE}/v1/admin/subscriptions/bulk-adjust`,{
            method:"POST",
            cache:"no-store",
            headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json",Accept:"application/json"},
            body:JSON.stringify({operation:selected,amount:numeric}),
          });
          const raw=await response.text();
          let payload:BulkResult&{detail?:unknown}={};
          try{payload=raw?JSON.parse(raw):{};}catch{}
          if(!response.ok){
            const detail=typeof payload.detail==="string"?payload.detail:raw||`API error ${response.status}`;
            throw new Error(detail);
          }
          result.className="runtime-success";
          result.textContent=tr(
            `انجام شد: ${payload.updated??0} بروزرسانی، ${payload.skipped??0} ردشده، ${payload.clamped??0} محدودشده`,
            `Done: ${payload.updated??0} updated, ${payload.skipped??0} skipped, ${payload.clamped??0} clamped`
          );
          result.style.display="block";
          refreshSubscriptionsTable();
        }catch(reason){
          result.className="runtime-error";
          result.textContent=reason instanceof Error?reason.message:String(reason);
          result.style.display="block";
        }finally{
          apply.disabled=false;
          cancel.disabled=false;
          apply.textContent=tr("اعمال روی همه اشتراک‌ها","Apply to all subscriptions");
        }
      });

      actions.append(cancel,apply);
      card.append(head,grid,note,result,actions);
      modal.append(backdrop,card);
      document.body.appendChild(modal);
      bulkModal=modal;
    };

    const ensureBulkButton=()=>{
      if(disposed)return false;
      const head=document.querySelector<HTMLElement>(".legacy-subscriptions-page .page-head");
      if(!head)return false;
      if(head.querySelector("[data-subscription-bulk-button]"))return true;

      let actions=head.querySelector<HTMLDivElement>(":scope > .action-row[data-subscription-bulk-actions]");
      const create=head.querySelector<HTMLButtonElement>(":scope > button.primary");
      if(!actions){
        actions=document.createElement("div");
        actions.className="action-row";
        actions.dataset.subscriptionBulkActions="1";
        head.appendChild(actions);
        if(create)actions.appendChild(create);
      }

      const button=document.createElement("button");
      button.type="button";
      button.className="ghost";
      button.dataset.subscriptionBulkButton="1";
      button.textContent=`⚙ ${tr("مدیریت گروهی","Bulk management")}`;
      button.addEventListener("click",openBulkModal);
      actions.appendChild(button);
      return true;
    };

    const decorateNow=()=>{
      if(disposed)return;
      ensureBulkButton();
      const table=document.querySelector<HTMLTableElement>(".legacy-subscriptions-page .table table");
      const body=table?.tBodies?.[0]||null;
      if(!table||!body)return;

      for(const row of Array.from(body.rows)){
        const id=rowSubscriptionId(row);
        if(!Number.isFinite(id)||id<=0)continue;
        const cell=statusCell(row);
        if(!cell)continue;

        let host=cell.querySelector<HTMLDivElement>(":scope > div[data-live-sub-state]");
        if(!host){
          host=document.createElement("div");
          host.dataset.liveSubState="1";
          host.style.marginTop="6px";
          host.style.display="flex";
          host.style.alignItems="center";
          host.style.gap="5px";
          host.style.flexWrap="wrap";
          cell.appendChild(host);
        }

        const state=states.get(id);
        const online=Boolean(state?.online);
        const protocols=(state?.protocols||[]).map(protocolLabel).filter(Boolean);
        const stale=loaded&&(!lastSuccessAt||Date.now()-lastSuccessAt>STALE_AFTER_MS);
        const signature=loaded?`${stale?"stale":online?"1":"0"}:${protocols.join(",")}`:"loading";
        if(host.dataset.liveSignature===signature)continue;
        host.dataset.liveSignature=signature;
        host.replaceChildren();

        const badge=document.createElement("span");
        badge.className=`badge ${loaded?(stale?"violet":online?"ok":"bad"):"violet"}`;
        badge.textContent=!loaded?tr("در حال بررسی…","Checking…"):stale?tr("وضعیت نامشخص","Status unknown"):online?tr("آنلاین","Online"):tr("آفلاین","Offline");
        badge.title=stale?tr("گزارش وضعیت آنلاین به‌موقع دریافت نشده؛ قطع اتصال تأیید نشده است","Live telemetry is delayed; disconnection is not confirmed"):tr("وضعیت اتصال","Connection status");
        host.appendChild(badge);

        if(loaded&&!stale&&online&&protocols.length){
          const detail=document.createElement("small");
          detail.style.opacity=".72";
          detail.dir="ltr";
          detail.textContent=protocols.join(" · ");
          host.appendChild(detail);
        }
      }
    };

    const bindObserver=()=>{
      if(disposed)return;
      const body=document.querySelector<HTMLTableSectionElement>(".legacy-subscriptions-page .table table tbody");
      if(!body||body===observedBody)return;
      observer?.disconnect();
      observedBody=body;
      observer=new MutationObserver(()=>scheduleDecorate());
      observer.observe(body,{childList:true,subtree:false});
    };

    const scheduleDecorate=()=>{
      if(disposed||frame!==undefined)return;
      frame=window.requestAnimationFrame(()=>{
        frame=undefined;
        decorateNow();
        bindObserver();
      });
    };

    const refresh=async()=>{
      const token=getCustomerToken();
      if(!token||disposed||inFlight||document.visibilityState==="hidden")return;
      inFlight=true;
      controller=new AbortController();
      try{
        const response=await fetch(`${API_BASE}/v1/admin/subscriptions/live-status?ts=${Date.now()}`,{
          cache:"no-store",
          headers:{Authorization:`Bearer ${token}`,Accept:"application/json"},
          signal:controller.signal,
        });
        if(!response.ok)return;
        const payload=await response.json() as LivePayload;
        if(disposed)return;
        // Do not accept malformed/partial results as an all-offline snapshot.
        if(!Array.isArray(payload.items))return;
        states.clear();
        for(const item of payload.items){
          if(item&&Number.isFinite(Number(item.subscription_id)))states.set(Number(item.subscription_id),item);
        }
        loaded=true;
        lastSuccessAt=Date.now();
        scheduleDecorate();
      }catch{}
      finally{
        inFlight=false;
        controller=undefined;
      }
    };

    scheduleDecorate();
    bulkTimer=window.setInterval(()=>{
      if(ensureBulkButton()&&bulkTimer!==undefined){window.clearInterval(bulkTimer);bulkTimer=undefined;}
    },500);
    void refresh();
    timer=window.setInterval(()=>{void refresh();scheduleDecorate();},15000);
    const onVisibilityChange=()=>{if(document.visibilityState==="visible")void refresh();};
    document.addEventListener("visibilitychange",onVisibilityChange);

    return()=>{
      disposed=true;
      controller?.abort();
      closeBulkModal();
      document.querySelector("[data-subscription-bulk-button]")?.remove();
      if(timer)window.clearInterval(timer);
      if(bulkTimer)window.clearInterval(bulkTimer);
      if(frame!==undefined)window.cancelAnimationFrame(frame);
      observer?.disconnect();
      document.removeEventListener("visibilitychange",onVisibilityChange);
    };
  },[]);

  return null;
}
