"use client";

import {useEffect,useState} from "react";

import {Badge} from "./ui";
import {
  legacyControlApi,
  type TunnelServiceConnection,
  type TunnelServiceConnectionsResponse,
} from "../lib/legacy-control-api";
import {useI18n} from "../lib/i18n";


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
  const [error,setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setData(await legacyControlApi.tunnelServiceConnections(tunnelId));
    }
    catch (reason) {
      setData(null);
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [tunnelId]);

  const connections = Array.isArray(data?.connections) ? data.connections : [];

  return (
    <div className="manage-card-section">
      <div className="manage-section-head">
        <div>
          <b>{pick("اتصال‌های عبوری سرویس‌ها", "Service connections through tunnel")}</b>
          <small>
            {pick(
              "این‌ها سرویس‌های عبوری هستند و از Transport فیزیکی تانل جدا مدیریت می‌شوند.",
              "These are routed services and are separate from the tunnel's physical transport.",
            )}
          </small>
        </div>

        <button
          type="button"
          className="ghost"
          disabled={loading}
          onClick={() => void load()}
        >
          {loading ? "…" : pick("بروزرسانی", "Refresh")}
        </button>
      </div>

      {data && (
        <div className="runtime-info-list">
          <div>
            <span>{pick("Transport فعلی تانل", "Current tunnel transport")}</span>
            <b dir="ltr">{data.active_transport || "—"}</b>
          </div>
          <div>
            <span>{pick("مسیریابی سرویس", "Service routing")}</span>
            <Badge tone={data.route_active ? "ok" : "warn"}>
              {data.route_active ? pick("فعال", "Active") : pick("غیرفعال", "Inactive")}
            </Badge>
          </div>
        </div>
      )}

      {error && <div className="runtime-error compact">{error}</div>}

      {!error && !loading && connections.length === 0 && (
        <div className="runtime-empty">
          {pick("اتصال عبوری فعالی برای این تانل ثبت نشده است.", "No routed service connections are registered for this tunnel.")}
        </div>
      )}

      {connections.length > 0 && (
        <div className="setting-grid">
          {connections.map((item,index) => {
            const reason = reasonLabel(item.health_reason,pick);
            return (
              <div
                className="setting-box transport-runtime-card"
                key={`${item.protocol}-${item.profile}-${item.public_port ?? "none"}-${index}`}
              >
                <div className="card-head">
                  <div>
                    <b>{item.title || item.profile || item.protocol}</b>
                    <small dir="ltr">
                      {item.profile || item.protocol}
                    </small>
                  </div>
                  <Badge tone={connectionTone(item)}>
                    {connectionStatus(item,pick)}
                  </Badge>
                </div>

                <div className="runtime-info-list">
                  <div>
                    <span>{pick("پورت ورودی ایران", "Iran ingress port")}</span>
                    <b dir="ltr">{portText(item.public_port,item.transport)}</b>
                  </div>
                  <div>
                    <span>{pick("پورت سرویس خروجی", "Exit service port")}</span>
                    <b dir="ltr">{portText(item.target_port,item.transport)}</b>
                  </div>
                  <div>
                    <span>{pick("نوع", "Transport")}</span>
                    <b dir="ltr">{item.transport || "—"}</b>
                  </div>
                </div>

                {reason && (
                  <small>{reason}</small>
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
