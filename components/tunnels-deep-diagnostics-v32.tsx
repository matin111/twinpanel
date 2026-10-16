"use client";

import {useEffect, useMemo, useState} from "react";

import {Badge, Card, Shell} from "./ui";
import type {AdminNode, AdminTunnel} from "../lib/admin-api";
import {legacyControlApi} from "../lib/legacy-control-api";
import {tunnelTransportApi} from "../lib/tunnel-transport-api";
import {useI18n} from "../lib/i18n";


type SideDiag = {
  ok?: boolean;
  service?: {ActiveState?: string; SubState?: string};
  interface?: {exists?: boolean; mtu?: number | null; addr?: string};
  listener?: {required?: boolean; present?: boolean | null};
  firewall?: {checked?: boolean; present?: boolean | null};
  ping?: {loss_pct?: number | null; latency_ms?: number | null; received?: number | null; transmitted?: number | null};
  physical_interface?: string | null;
  counter_delta?: unknown;
};


type DeepTransport = {
  transport?: string;
  root_cause_code?: string;
  summary?: string;
  secret_match?: boolean | null;
  db?: {status?: string; enabled?: boolean; last_error?: string | null};
  runtime?: {interface?: string; iran_ip?: string; exit_ip?: string; port?: number | null; protocol?: string; carrier_interface?: string | null};
  iran?: SideDiag;
  exit?: SideDiag;
};


type DeepDiagnosis = {
  ok?: boolean;
  read_only?: boolean;
  tunnel_id?: number;
  active_transport?: string | null;
  preferred_transport?: string | null;
  unhealthy?: string[];
  transports?: DeepTransport[];
  marker?: string;
};


type DeepRepairResult = {
  ok?: boolean;
  managed_error?: string | null;
  modern_errors?: Record<string, string>;
  deep_diagnosis?: DeepDiagnosis;
  marker?: string;
  safety?: Record<string, unknown>;
};


const labels: Record<string, string> = {
  kcp_2027: "KCP 2027",
  mtunnel: "MTunnel",
  kernel_gre: "Kernel GRE",
  gost_tun: "GOST TUN",
};


function statusTone(status: unknown): "ok" | "warn" | "bad" | "violet" {
  const value = String(status ?? "").toLowerCase();
  if (["online", "active", "healthy"].includes(value)) return "ok";
  if (["failed", "offline", "down", "error"].includes(value)) return "bad";
  return "warn";
}


function causeTone(code: unknown): "ok" | "warn" | "bad" | "violet" {
  const value = String(code ?? "");
  if (value === "healthy") return "ok";
  if (["diagnostic_unavailable", "diagnostic_error"].includes(value)) return "warn";
  return "bad";
}


function SideSummary({title, side}: {title: string; side?: SideDiag}) {
  const service = String(side?.service?.ActiveState || "—");
  const iface = Boolean(side?.interface?.exists);
  const listener = side?.listener?.required ? (side?.listener?.present ? "OK" : "Missing") : "—";
  const firewall = side?.firewall?.checked ? (side?.firewall?.present ? "OK" : "Missing") : "—";
  const loss = side?.ping?.loss_pct;

  return (
    <div className="card">
      <div className="card-head">
        <b>{title}</b>
        <Badge tone={side?.ok ? "ok" : "bad"}>{side?.ok ? "OK" : "Error"}</Badge>
      </div>
      <div className="runtime-info-list">
        <div><span>Service</span><b>{service}</b></div>
        <div><span>Interface</span><b>{iface ? "OK" : "Missing"}</b></div>
        <div><span>MTU</span><b>{side?.interface?.mtu ?? "—"}</b></div>
        <div><span>Peer loss</span><b>{loss == null ? "—" : `${loss}%`}</b></div>
        <div><span>Latency</span><b>{side?.ping?.latency_ms == null ? "—" : `${side.ping.latency_ms} ms`}</b></div>
        <div><span>Listener</span><b>{listener}</b></div>
        <div><span>Firewall</span><b>{firewall}</b></div>
        <div><span>Physical NIC</span><b>{side?.physical_interface || "—"}</b></div>
      </div>
    </div>
  );
}


export function TunnelsDeepDiagnosticsV32() {
  const {pick} = useI18n();
  const [tunnels, setTunnels] = useState<AdminTunnel[]>([]);
  const [nodes, setNodes] = useState<AdminNode[]>([]);
  const [tunnelId, setTunnelId] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [diagnosis, setDiagnosis] = useState<DeepDiagnosis | null>(null);
  const [repairResult, setRepairResult] = useState<DeepRepairResult | null>(null);

  const nodeMap = useMemo(() => new Map(nodes.map(row => [row.id, row])), [nodes]);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const [tunnelRows, nodeRows] = await Promise.all([
          legacyControlApi.tunnels(),
          legacyControlApi.nodes(),
        ]);
        setTunnels(tunnelRows);
        setNodes(nodeRows);
        setTunnelId(current => current || tunnelRows[0]?.id || 0);
      }
      catch (reason) {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
      finally {
        setLoading(false);
      }
    })();
  }, []);

  const selected = tunnels.find(row => row.id === tunnelId) || null;

  const diagnose = async () => {
    if (!tunnelId || busy) return;
    setBusy("diagnose");
    setError("");
    setRepairResult(null);
    try {
      const result = await tunnelTransportApi.managedDeepDiagnose(tunnelId) as DeepDiagnosis;
      setDiagnosis(result);
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };

  const repair = async () => {
    if (!tunnelId || busy) return;
    if (!window.confirm(pick(
      `تعمیر عمیق تانل #${tunnelId} اجرا شود؟ مسیرهای سالم دست‌نخورده می‌مانند و نتیجه تشخیص عمیق بعد از تعمیر نمایش داده می‌شود.`,
      `Run deep repair for tunnel #${tunnelId}? Healthy paths stay untouched and a deep post-repair diagnosis will be shown.`,
    ))) return;

    setBusy("repair");
    setError("");
    try {
      const result = await tunnelTransportApi.managedDeepRepair(tunnelId) as DeepRepairResult;
      setRepairResult(result);
      if (result.deep_diagnosis) setDiagnosis(result.deep_diagnosis);
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };

  return (
    <Shell active="/admin/tunnels">
      <div className="page legacy-control-page">
        <div className="page-head">
          <div>
            <h1>{pick("تشخیص عمیق تانل", "Deep tunnel diagnostics")}</h1>
            <small>{pick(
              "V32: بررسی Data Plane از خود پنل؛ بدون SSH دستی به سرور ایران یا خارج.",
              "V32: data-plane diagnostics from the panel, without manual SSH to either node.",
            )}</small>
          </div>
        </div>

        {error ? <div className="runtime-error">{error}</div> : null}

        <Card>
          <div className="card-head">
            <div>
              <b>{pick("انتخاب تانل", "Select tunnel")}</b>
              <small>{pick("تشخیص عمیق فقط خواندنی است.", "Deep diagnose is read-only.")}</small>
            </div>
          </div>

          <div className="action-row">
            <select
              value={tunnelId}
              disabled={loading || Boolean(busy)}
              onChange={event => {
                setTunnelId(Number(event.target.value));
                setDiagnosis(null);
                setRepairResult(null);
              }}
            >
              {tunnels.map(tunnel => {
                const iran = nodeMap.get(tunnel.iran_node_id);
                const exitNode = nodeMap.get(tunnel.exit_node_id);
                return (
                  <option key={tunnel.id} value={tunnel.id}>
                    #{tunnel.id} · {iran?.name || tunnel.iran_node_id} → {exitNode?.name || tunnel.exit_node_id}
                  </option>
                );
              })}
            </select>

            <button className="primary-soft" disabled={!tunnelId || Boolean(busy)} onClick={() => void diagnose()}>
              {busy === "diagnose" ? "…" : pick("تشخیص عمیق", "Deep diagnose")}
            </button>

            <button className="primary" disabled={!tunnelId || Boolean(busy)} onClick={() => void repair()}>
              {busy === "repair" ? "…" : pick("تعمیر عمیق", "Deep repair")}
            </button>
          </div>

          {selected ? (
            <div className="runtime-info-list">
              <div><span>{pick("تانل", "Tunnel")}</span><b>#{selected.id}</b></div>
              <div><span>{pick("وضعیت", "Status")}</span><Badge tone={statusTone(selected.status)}>{String(selected.status || "—")}</Badge></div>
            </div>
          ) : null}
        </Card>

        {repairResult ? (
          <Card>
            <div className="card-head">
              <div><b>{pick("نتیجه تعمیر عمیق", "Deep repair result")}</b><small>V32</small></div>
              <Badge tone={repairResult.ok ? "ok" : "warn"}>{repairResult.ok ? "OK" : pick("نیازمند بررسی", "Needs review")}</Badge>
            </div>
            {repairResult.managed_error ? <div className="runtime-error" dir="ltr">{repairResult.managed_error}</div> : null}
            {repairResult.modern_errors && Object.keys(repairResult.modern_errors).length ? (
              <pre className="runtime-log" dir="ltr">{JSON.stringify(repairResult.modern_errors, null, 2)}</pre>
            ) : null}
            <div className="runtime-success">{pick(
              "V32 هیچ Port/Key/MTU یا وزن Auto را تغییر نمی‌دهد.",
              "V32 does not rotate ports/keys or change MTU/Auto weights.",
            )}</div>
          </Card>
        ) : null}

        {diagnosis ? (
          <>
            <Card>
              <div className="card-head">
                <div><b>{pick("خلاصه تشخیص", "Diagnosis summary")}</b><small>Read-only</small></div>
                <Badge tone={(diagnosis.unhealthy?.length || 0) ? "warn" : "ok"}>
                  {(diagnosis.unhealthy?.length || 0) ? `${diagnosis.unhealthy?.length} issue` : "Healthy"}
                </Badge>
              </div>
              <div className="runtime-info-list">
                <div><span>{pick("فعال", "Active")}</span><b>{diagnosis.active_transport || "—"}</b></div>
                <div><span>{pick("پیشنهادی", "Preferred")}</span><b>{diagnosis.preferred_transport || "—"}</b></div>
                <div><span>{pick("خراب", "Unhealthy")}</span><b dir="ltr">{diagnosis.unhealthy?.join(", ") || "—"}</b></div>
              </div>
            </Card>

            {(diagnosis.transports || []).map(item => (
              <Card key={String(item.transport)}>
                <div className="card-head">
                  <div>
                    <b>{labels[String(item.transport)] || String(item.transport || "—")}</b>
                    <small dir="ltr">{item.runtime?.interface || "—"} · {item.runtime?.protocol || "—"}{item.runtime?.port ? `:${item.runtime.port}` : ""}</small>
                  </div>
                  <Badge tone={causeTone(item.root_cause_code)}>{item.root_cause_code || "—"}</Badge>
                </div>

                <div className={item.root_cause_code === "healthy" ? "runtime-success" : "runtime-warning"}>
                  {item.summary || "—"}
                </div>

                <div className="runtime-info-list">
                  <div><span>DB status</span><b>{item.db?.status || "—"}</b></div>
                  <div><span>Secret match</span><b>{item.secret_match == null ? "—" : item.secret_match ? "YES" : "NO"}</b></div>
                  <div><span>Carrier</span><b>{item.runtime?.carrier_interface || "—"}</b></div>
                </div>

                <div className="module-grid two">
                  <SideSummary title={pick("نود ایران", "Iran node")} side={item.iran} />
                  <SideSummary title={pick("نود خارج", "Exit node")} side={item.exit} />
                </div>

                <details>
                  <summary>{pick("جزئیات Counters", "Counter details")}</summary>
                  <pre className="runtime-log" dir="ltr">{JSON.stringify({iran: item.iran?.counter_delta, exit: item.exit?.counter_delta}, null, 2)}</pre>
                </details>
              </Card>
            ))}
          </>
        ) : null}
      </div>
    </Shell>
  );
}
