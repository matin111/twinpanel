"use client";

import {useEffect, useMemo, useState} from "react";

import {Badge, Card, Shell} from "./ui";
import type {AdminNode, AdminTunnel} from "../lib/admin-api";
import {legacyControlApi} from "../lib/legacy-control-api";
import {tunnelTransportApi} from "../lib/tunnel-transport-api";
import {useI18n} from "../lib/i18n";


type SideDiag = {
  ok?: boolean;
  error?: string;
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


type AgentMeta = {
  available?: boolean;
  agent_version?: string | null;
  age_seconds?: number | null;
};


type DeepDiagnosis = {
  ok?: boolean;
  read_only?: boolean;
  source?: string;
  partial?: boolean;
  tunnel_id?: number;
  active_transport?: string | null;
  preferred_transport?: string | null;
  unhealthy?: string[];
  transports?: DeepTransport[];
  agents?: {iran?: AgentMeta; exit?: AgentMeta};
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


type AgentInstallResult = {
  ok?: boolean;
  results?: Record<string, {ok?: boolean; service?: string; error?: string; agent_version?: string}>;
  marker?: string;
};


type DeepDiagnosticsProps = {
  initialTunnelId?: number;
  onBack?: () => void;
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
  if (["diagnostic_unavailable", "diagnostic_error", "agent_unavailable", "agent_diagnostic_error"].includes(value)) return "warn";
  return "bad";
}


function agentText(meta?: AgentMeta) {
  if (!meta?.available) return "Offline / no fresh report";
  const version = meta.agent_version || "agent";
  const age = meta.age_seconds == null ? "" : ` · ${meta.age_seconds}s ago`;
  return `${version}${age}`;
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
        <Badge tone={side?.ok ? "ok" : "warn"}>{side?.ok ? "OK" : "Unavailable"}</Badge>
      </div>
      {side?.error ? <div className="runtime-warning" dir="ltr">{side.error}</div> : null}
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


export function TunnelsDeepDiagnosticsV32({
  initialTunnelId = 0,
  onBack,
}: DeepDiagnosticsProps = {}) {
  const {pick} = useI18n();
  const [tunnels, setTunnels] = useState<AdminTunnel[]>([]);
  const [nodes, setNodes] = useState<AdminNode[]>([]);
  const [tunnelId, setTunnelId] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
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
        setTunnelId(current => {
          const requested = Number(initialTunnelId || 0);
          if (requested > 0 && tunnelRows.some(row => row.id === requested)) {
            return requested;
          }
          return current || tunnelRows[0]?.id || 0;
        });
      }
      catch (reason) {
        setError(reason instanceof Error ? reason.message : String(reason));
      }
      finally {
        setLoading(false);
      }
    })();
  }, [initialTunnelId]);

  const selected = tunnels.find(row => row.id === tunnelId) || null;

  const diagnose = async () => {
    if (!tunnelId || busy) return;
    setBusy("diagnose");
    setError("");
    setNotice("");
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

  const installAgents = async () => {
    if (!tunnelId || busy) return;
    if (!window.confirm(pick(
      `Agent تشخیص روی هر دو نود تانل #${tunnelId} نصب/ارتقا شود؟ SSH ذخیره‌شده فقط برای همین Bootstrap استفاده می‌شود؛ بعد از آن تشخیص بدون SSH انجام می‌شود.`,
      `Install/upgrade the diagnostics agent on both nodes of tunnel #${tunnelId}? Saved SSH is used only for this bootstrap; routine diagnostics then run without SSH.`,
    ))) return;

    setBusy("agent");
    setError("");
    setNotice("");
    try {
      const result = await tunnelTransportApi.installDeepDiagnosticsAgent(tunnelId) as AgentInstallResult;
      const failures = Object.entries(result.results || {})
        .filter(([, value]) => value?.ok !== true)
        .map(([side, value]) => `${side}: ${value?.error || value?.service || "failed"}`);

      if (!result.ok || failures.length) {
        setError(failures.join(" | ") || pick("نصب Agent کامل نشد.", "Agent installation did not complete."));
        return;
      }

      setNotice(pick(
        "Agent تشخیص روی هر دو سرور فعال شد. حدود ۱۰ تا ۱۵ ثانیه برای اولین گزارش صبر می‌کنیم…",
        "Diagnostics agents are active on both servers. Waiting about 10–15 seconds for the first report…",
      ));

      await new Promise(resolve => window.setTimeout(resolve, 12000));
      const fresh = await tunnelTransportApi.managedDeepDiagnose(tunnelId) as DeepDiagnosis;
      setDiagnosis(fresh);
      setNotice(pick("گزارش Agentها دریافت شد.", "Agent reports received."));
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
      `تعمیر عمیق تانل #${tunnelId} اجرا شود؟ مسیرهای سالم دست‌نخورده می‌مانند و نتیجه Agentها بعد از تعمیر نمایش داده می‌شود.`,
      `Run deep repair for tunnel #${tunnelId}? Healthy paths stay untouched and node-agent diagnosis will be shown afterward.`,
    ))) return;

    setBusy("repair");
    setError("");
    setNotice("");
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

  const agentsReady = Boolean(diagnosis?.agents?.iran?.available && diagnosis?.agents?.exit?.available);

  return (
    <Shell active="/admin/tunnels">
      <div className="page legacy-control-page">
        <div className="page-head">
          <div>
            <h1>{pick("تشخیص عمیق تانل", "Deep tunnel diagnostics")}</h1>
            <small>{pick(
              "تشخیص برای همان مسیر ایران ↔ خارج انتخاب‌شده اجرا می‌شود؛ کنترلر فقط گزارش Agentها را جمع می‌کند.",
              "Diagnostics run for the selected Iran ↔ Exit tunnel pair; the controller only aggregates agent reports.",
            )}</small>
          </div>
          {onBack ? (
            <div className="action-row">
              <button type="button" className="ghost" disabled={Boolean(busy)} onClick={onBack}>
                {pick("بازگشت به تانل‌ها", "Back to tunnels")}
              </button>
            </div>
          ) : null}
        </div>

        {error ? <div className="runtime-error">{error}</div> : null}
        {notice ? <div className="runtime-success">{notice}</div> : null}

        <Card>
          <div className="card-head">
            <div>
              <b>{pick("سرورهای این تانل", "Tunnel servers")}</b>
              <small>{pick("تشخیص عمیق روی خود نود ایران و خارج اجرا می‌شود.", "Deep diagnostics run locally on the Iran and Exit nodes.")}</small>
            </div>
          </div>

          <div className="action-row">
            <select
              value={tunnelId}
              disabled={loading || Boolean(busy)}
              onChange={event => {
                const nextId = Number(event.target.value);
                setTunnelId(nextId);
                setDiagnosis(null);
                setRepairResult(null);
                setError("");
                setNotice("");
                if (nextId > 0) window.location.hash = `deep-diagnostics=${nextId}`;
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

            <button className="primary-soft" disabled={!tunnelId || Boolean(busy)} onClick={() => void installAgents()}>
              {busy === "agent" ? "…" : pick("نصب/ارتقای Agent تشخیص", "Install/upgrade diagnostics agents")}
            </button>

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
              <div><span>{pick("ایران", "Iran")}</span><b>{nodeMap.get(selected.iran_node_id)?.name || `#${selected.iran_node_id}`}</b></div>
              <div><span>{pick("خارج", "Exit")}</span><b>{nodeMap.get(selected.exit_node_id)?.name || `#${selected.exit_node_id}`}</b></div>
              <div><span>{pick("وضعیت", "Status")}</span><Badge tone={statusTone(selected.status)}>{String(selected.status || "—")}</Badge></div>
            </div>
          ) : null}
        </Card>

        {diagnosis ? (
          <Card>
            <div className="card-head">
              <div>
                <b>{pick("Agentهای تشخیص", "Diagnostics agents")}</b>
                <small>{diagnosis.source || "node_agents"}</small>
              </div>
              <Badge tone={agentsReady ? "ok" : "warn"}>{agentsReady ? "Ready" : "Partial"}</Badge>
            </div>
            <div className="runtime-info-list">
              <div><span>{pick("سرور ایران", "Iran node")}</span><b dir="ltr">{agentText(diagnosis.agents?.iran)}</b></div>
              <div><span>{pick("سرور خارج", "Exit node")}</span><b dir="ltr">{agentText(diagnosis.agents?.exit)}</b></div>
            </div>
            {!agentsReady ? (
              <div className="runtime-warning">{pick(
                "گزارش تازه از هر دو Node موجود نیست. دکمه «نصب/ارتقای Agent تشخیص» را بزن؛ این کار فقط برای Bootstrap از SSH ذخیره‌شده استفاده می‌کند.",
                "Fresh reports are not available from both nodes. Use Install/upgrade diagnostics agents; saved SSH is used only for bootstrap.",
              )}</div>
            ) : null}
          </Card>
        ) : null}

        {repairResult ? (
          <Card>
            <div className="card-head">
              <div><b>{pick("نتیجه تعمیر عمیق", "Deep repair result")}</b><small>V34</small></div>
              <Badge tone={repairResult.ok ? "ok" : "warn"}>{repairResult.ok ? "OK" : pick("نیازمند بررسی", "Needs review")}</Badge>
            </div>
            {repairResult.managed_error ? <div className="runtime-error" dir="ltr">{repairResult.managed_error}</div> : null}
            {repairResult.modern_errors && Object.keys(repairResult.modern_errors).length ? (
              <pre className="runtime-log" dir="ltr">{JSON.stringify(repairResult.modern_errors, null, 2)}</pre>
            ) : null}
            <div className="runtime-success">{pick(
              "تشخیص عمیق Port/Key/MTU، Route یا وزن Auto را تغییر نمی‌دهد؛ Repair به‌صورت Job اجرا می‌شود.",
              "Deep diagnostics do not change ports, keys, MTU, routes or Auto weights; repair runs as a job.",
            )}</div>
          </Card>
        ) : null}

        {diagnosis ? (
          <>
            <Card>
              <div className="card-head">
                <div><b>{pick("خلاصه تشخیص", "Diagnosis summary")}</b><small>Agent-first · Read-only</small></div>
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
