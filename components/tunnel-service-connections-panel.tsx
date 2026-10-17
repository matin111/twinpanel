"use client";

import {useEffect,useMemo,useState} from "react";

import {Badge} from "./ui";
import {TunnelManageModalPolishV45} from "./tunnel-manage-modal-polish-v45";
import {
  legacyControlApi,
  type TunnelServiceConnection,
  type TunnelServiceConnectionsResponse,
} from "../lib/legacy-control-api";
import {serviceConnectionsV36Api} from "../lib/service-connections-v36-api";
import {useI18n} from "../lib/i18n";


const HIDDEN_XRAY_SERVICE_PROFILES = new Set([
  "xhttp_reality",
  "legacy",
]);


function visibleServiceConnection(item: TunnelServiceConnection) {
  if (String(item.protocol || "").toLowerCase() !== "v2ray") {
    return true;
  }

  return !HIDDEN_XRAY_SERVICE_PROFILES.has(
    String(item.profile || "").toLowerCase(),
  );
}


function reasonLabel(value: string | null | undefined, pick: (fa:string,en:string)=>string) {
  switch (String(value || "")) {
    case "tls_domain_unavailable":
      return pick("نیازمند دامنه و TLS", "Domain and TLS required");
    case "listener_not_running":
      return pick("Listener فعال نیست", "Listener is not running");
    case "listener_health_unknown":
    case "xray_health_not_probed":
      return pick("سلامت زنده نامشخص است", "Live health is unknown");
    case "protocol_not_online":
      return pick("پروتکل آنلاین نیست", "Protocol is not online");
    default:
      return value || "";
  }
}


function connectionTone(item: TunnelServiceConnection): "ok" | "warn" | "bad" {
  if (item.available === false) {
    return "warn";
  }
  if (item.healthy === true) {
    return "ok";
  }
  if (item.healthy === false) {
    return "bad";
  }
  return "warn";
}


function connectionStatus(item: TunnelServiceConnection, pick: (fa:string,en:string)=>string) {
  if (item.available === false) {
    return pick("غیرفعال", "Unavailable");
  }
  if (item.healthy === true) {
    return "ONLINE";
  }
  if (item.healthy === false) {
    return "CHECK";
  }
  return pick("نامشخص", "Unknown");
}


function portText(value: number | null | undefined, transport?: string) {
  if (value == null) {
    return String(transport || "").toLowerCase() === "esp" ? "ESP" : "—";
  }
  return String(value);
}


export function TunnelServiceConnectionsPanel({tunnelId}:{tunnelId:number}) {
  const {pick} = useI18n();
  const [data,setData] = useState<TunnelServiceConnectionsResponse|null>(null);
  const [loading,setLoading] = useState(true);
  const [busy,setBusy] = useState<""|"speed"|"xray">("");
  const [error,setError] = useState("");
  const [message,setMessage] = useState("");

  const load = async (silent=false) => {
    if(!silent)setLoading(true);
    if(!silent)setError("");
    try {
      setData(await legacyControlApi.tunnelServiceConnections(tunnelId));
    }
    catch (reason) {
      if(!silent)setData(null);
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      if(!silent)setLoading(false);
    }
  };

  useEffect(() => {
    void load();

    // Service routes are reconciled by Node Agent. Keep this panel live so a
    // transport repair or a freshly restored Iran service route appears without
    // a manual page refresh.
    const timer=window.setInterval(
      ()=>void load(true),
      5000,
    );

    return ()=>window.clearInterval(timer);
  }, [tunnelId]);

  const rawConnections = Array.isArray(data?.connections) ? data.connections : [];
  const connections = useMemo(
    ()=>rawConnections.filter(visibleServiceConnection),
    [rawConnections],
  );
  const hasXray = useMemo(
    ()=>connections.some(item=>String(item.protocol||"").toLowerCase()==="v2ray"),
    [connections],
  );

  const highSpeed = async () => {
    if(busy)return;
    setBusy("speed");
    setError("");
    setMessage("");

    try {
      const result=await serviceConnectionsV36Api.repairRealEgress(tunnelId);
      const selected=result.selected;
      const latency=selected?.latency_ms??result.latency_ms;
      const loss=selected?.loss_pct;

      setMessage(
        result.ok
          ? pick(
              `مسیر واقعی ${result.active_transport||selected?.transport||"سالم"} با خروج اینترنت تایید و فعال شد${latency!=null?`؛ پینگ ${latency.toLocaleString("fa-IR")}ms`:""}${loss!=null?`؛ افت ${loss.toLocaleString("fa-IR")}%`:""}.`,
              `Verified real Internet egress on ${result.active_transport||selected?.transport||"a healthy transport"}${latency!=null?`; ${latency}ms`:""}${loss!=null?`; ${loss}% loss`:""}.`,
            )
          : pick(
              "قوانین خروج اصلاح شد اما هنوز هیچ مسیر واقعی سالمی تایید نشد.",
              "Exit routing was repaired, but no real healthy dataplane was verified yet.",
            ),
      );

      // The repair action is short. Give Node Agent a small window to publish
      // the service DNAT routes that depend on the newly verified active tunnel.
      for(let i=0;i<8;i+=1){
        await new Promise<void>(resolve=>window.setTimeout(resolve,2000));
        await load(true);
      }
    }
    catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }
    finally{
      setBusy("");
    }
  };

  const reconcileXray = async () => {
    if(busy)return;
    setBusy("xray");
    setError("");
    setMessage("");

    try{
      const job=await serviceConnectionsV36Api.reconcileXray(tunnelId);
      const result=job.result;
      const migrated=Number(result?.migrated??job.migrated??0);
      const skipped=Number(result?.skipped??job.skipped??0);
      const errors=Array.isArray(result?.errors)?result?.errors:(Array.isArray(job.errors)?job.errors:[]);

      setMessage(
        pick(
          `Xray تکمیل شد: ${migrated.toLocaleString("fa-IR")} اشتراک بروزرسانی، ${skipped.toLocaleString("fa-IR")} بدون تغییر${errors.length?`، ${errors.length.toLocaleString("fa-IR")} خطا`:""}.`,
          `Xray reconciliation completed: ${migrated} updated, ${skipped} unchanged${errors.length?`, ${errors.length} errors`:""}.`,
        ),
      );

      // Give the Exit listener and the Iran service route a short window to
      // publish their final health after reconcile, then refresh the cards.
      for(let i=0;i<6;i+=1){
        await load(true);
        await new Promise<void>(resolve=>window.setTimeout(resolve,1500));
      }
    }
    catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }
    finally{
      setBusy("");
    }
  };

  return (
    <div className="manage-card-section tunnel-service-connections-compact">
      <TunnelManageModalPolishV45/>

      <div className="tunnel-service-compact-head">
        <div>
          <b>{pick("اتصال‌های عبوری", "Service connections")}</b>
          <small>
            {connections.length.toLocaleString("fa-IR")} {pick("مسیر سرویس", "service routes")}
          </small>
        </div>

        <div className="tunnel-service-compact-actions">
          {data && (
            <>
              <span className="tunnel-service-chip" dir="ltr">
                {data.active_transport || "—"}
              </span>
              <Badge tone={data.route_active ? "ok" : "warn"}>
                {data.route_active ? pick("مسیریابی فعال", "Routing active") : pick("مسیریابی غیرفعال", "Routing inactive")}
              </Badge>
            </>
          )}

          {data && (
            <button
              type="button"
              className="primary-soft"
              disabled={Boolean(busy)}
              onClick={()=>void highSpeed()}
            >
              {busy==="speed"?"…":pick("تعمیر مسیر واقعی", "Repair real route")}
            </button>
          )}

          {hasXray && (
            <button
              type="button"
              className="primary-soft"
              disabled={Boolean(busy)}
              onClick={()=>void reconcileXray()}
            >
              {busy==="xray"?"…":pick("تکمیل Xray", "Complete Xray")}
            </button>
          )}

          <button
            type="button"
            className="ghost tunnel-service-refresh"
            disabled={loading||Boolean(busy)}
            onClick={() => void load()}
          >
            {loading ? "…" : pick("بروزرسانی", "Refresh")}
          </button>
        </div>
      </div>

      {error && <div className="runtime-error compact">{error}</div>}
      {message && <div className="runtime-success compact">{message}</div>}

      {!error && !loading && connections.length === 0 && (
        <div className="runtime-empty">
          {pick("اتصال عبوری فعالی برای این تانل ثبت نشده است.", "No routed service connections are registered for this tunnel.")}
        </div>
      )}

      {connections.length > 0 && (
        <div className="tunnel-service-compact-grid">
          {connections.map((item,index) => {
            const reason = reasonLabel(item.health_reason,pick);
            const ingress = portText(item.public_port,item.transport);
            const target = portText(item.target_port,item.transport);
            const transport = item.transport || "—";

            return (
              <div
                className="tunnel-service-compact-item"
                key={`${item.protocol}-${item.profile}-${item.public_port ?? "none"}-${index}`}
              >
                <div className="tunnel-service-compact-item-head">
                  <div className="tunnel-service-compact-title">
                    <b>{item.title || item.profile || item.protocol}</b>
                    <small dir="ltr">{item.profile || item.protocol}</small>
                  </div>

                  <Badge tone={connectionTone(item)}>
                    {connectionStatus(item,pick)}
                  </Badge>
                </div>

                <div className="tunnel-service-route-line" dir="ltr">
                  <strong>{ingress}</strong>
                  <span>→</span>
                  <strong>{target}</strong>
                  <span className="tunnel-service-route-separator">•</span>
                  <span>{transport}</span>
                </div>

                {reason && (
                  <small className="tunnel-service-reason">{reason}</small>
                )}
              </div>
            );
          })}
        </div>
      )}

      {data?.xray_health?.error && (
        <div className="runtime-warning compact">
          {pick("وضعیت Xray", "Xray status")}: {data.xray_health.error}
        </div>
      )}
    </div>
  );
}
