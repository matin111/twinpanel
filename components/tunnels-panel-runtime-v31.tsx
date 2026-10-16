"use client";

import {
  type FormEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useState,
} from "react";

import {Badge, Card, Shell, Stat} from "./ui";
import type {AdminNode, AdminTunnel} from "../lib/admin-api";
import {legacyControlApi} from "../lib/legacy-control-api";
import {
  type TunnelTransportName,
  type TunnelTransportRow,
  type TunnelTransportState,
  tunnelTransportApi,
} from "../lib/tunnel-transport-api";
import {useI18n} from "../lib/i18n";


type Draft = {
  iran_node_id: number;
  exit_node_id: number;
  priority: number;
};


type DiagnosisTransport = {
  transport?: string;
  priority?: number | null;
  enabled?: boolean;
  status?: string;
  latency_ms?: number | null;
  last_error?: string | null;
  issue_code?: string | null;
  dependency?: string | null;
};


type ManagedDiagnosis = {
  ok?: boolean;
  tunnel_id?: number;
  mode?: string;
  status?: string;
  active_transport?: string | null;
  preferred_transport?: string | null;
  selectable_online?: string[];
  repair_needed?: string[];
  operational?: boolean;
  healthy?: boolean;
  complete?: boolean;
  transports?: DiagnosisTransport[];
};


type TunnelsPanelRuntimeV31Props = {
  onDeepDiagnostics?: (tunnelId: number) => void;
};


const emptyDraft: Draft = {
  iran_node_id: 0,
  exit_node_id: 0,
  priority: 100,
};


const transportLabels: Record<string, string> = {
  quic_2027: "QUIC 2027",
  arq_2027: "ARQ 2027",
  kcp_2027: "KCP 2027",
  tcp_2027: "TCP 2027",
  kernel_gre: "Kernel GRE",
  backhaul: "Backhaul",
  mtunnel: "MTunnel",
  gost_tun: "GOST TUN",
  ssh_tun: "SSH TUN",
  ssh_relay: "SSH Relay",
};


const manualChoices: TunnelTransportName[] = [
  "quic_2027",
  "arq_2027",
  "kcp_2027",
  "tcp_2027",
  "backhaul",
  "mtunnel",
  "ssh_tun",
];


function normalized(value: unknown) {
  return String(value ?? "").trim().toLowerCase();
}


function labelForTransport(value: unknown) {
  const name = String(value ?? "").trim();
  return transportLabels[name] || name || "—";
}


function tone(value: unknown): "ok" | "warn" | "bad" | "violet" {
  const status = normalized(value);

  if (["online", "active", "healthy", "ok", "ready"].includes(status)) {
    return "ok";
  }

  if (["offline", "failed", "error", "down", "stopped"].includes(status)) {
    return "bad";
  }

  if (status === "manual") {
    return "violet";
  }

  return "warn";
}


function Modal({
  title,
  sub,
  onClose,
  children,
}: {
  title: string;
  sub?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="runtime-modal" role="dialog" aria-modal="true">
      <button
        type="button"
        className="runtime-modal-bg"
        aria-label="close"
        onClick={onClose}
      />
      <div className="runtime-modal-card">
        <div className="card-head">
          <div>
            <b>{title}</b>
            {sub ? <small>{sub}</small> : null}
          </div>
          <button type="button" className="icon-button" onClick={onClose}>×</button>
        </div>
        {children}
      </div>
    </div>
  );
}


export function TunnelsPanelRuntimeV31({
  onDeepDiagnostics,
}: TunnelsPanelRuntimeV31Props = {}) {
  const {pick} = useI18n();

  const [tunnels, setTunnels] = useState<AdminTunnel[]>([]);
  const [nodes, setNodes] = useState<AdminNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [search, setSearch] = useState("");

  const [createOpen, setCreateOpen] = useState(false);
  const [draft, setDraft] = useState<Draft>(emptyDraft);

  const [manageOpen, setManageOpen] = useState(false);
  const [selected, setSelected] = useState<AdminTunnel | null>(null);
  const [transportState, setTransportState] = useState<TunnelTransportState | null>(null);
  const [diagnosis, setDiagnosis] = useState<ManagedDiagnosis | null>(null);
  const [health, setHealth] = useState<unknown>(null);
  const [transportLoading, setTransportLoading] = useState(false);
  const [manualTransport, setManualTransport] = useState<TunnelTransportName>("quic_2027");


  const nodeMap = useMemo(
    () => new Map(nodes.map(node => [node.id, node])),
    [nodes],
  );

  const iranNodes = useMemo(
    () => nodes.filter(node => normalized(node.node_type) === "iran"),
    [nodes],
  );

  const exitNodes = useMemo(
    () => nodes.filter(node => normalized(node.node_type) === "exit"),
    [nodes],
  );

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return tunnels;

    return tunnels.filter(tunnel => {
      const iran = nodeMap.get(tunnel.iran_node_id);
      const exitNode = nodeMap.get(tunnel.exit_node_id);
      const haystack = [
        tunnel.id,
        tunnel.status,
        iran?.name,
        iran?.public_ip,
        exitNode?.name,
        exitNode?.public_ip,
      ].join(" ").toLowerCase();
      return haystack.includes(query);
    });
  }, [tunnels, search, nodeMap]);

  const onlineCount = tunnels.filter(t => normalized(t.status) === "online").length;
  const degradedCount = tunnels.filter(t => normalized(t.status) === "degraded").length;
  const offlineCount = Math.max(0, tunnels.length - onlineCount - degradedCount);

  const transportRows: TunnelTransportRow[] = Array.isArray(transportState?.transports)
    ? transportState.transports
    : [];

  const diagnosisByName = useMemo(() => {
    const map = new Map<string, DiagnosisTransport>();
    for (const row of diagnosis?.transports || []) {
      const name = String(row.transport || "");
      if (name) map.set(name, row);
    }
    return map;
  }, [diagnosis]);


  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    setError("");

    try {
      const [tunnelRows, nodeRows] = await Promise.all([
        legacyControlApi.tunnels(),
        legacyControlApi.nodes(),
      ]);
      setTunnels(tunnelRows);
      setNodes(nodeRows);
      setSelected(current => current
        ? tunnelRows.find(row => row.id === current.id) || null
        : null);
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      if (!silent) setLoading(false);
    }
  };


  const loadDetails = async (tunnelId: number) => {
    setTransportLoading(true);
    setError("");

    try {
      const [stateResult, diagnoseResult] = await Promise.all([
        tunnelTransportApi.transports(tunnelId),
        tunnelTransportApi.managedDiagnose(tunnelId),
      ]);

      setTransportState(stateResult);
      setDiagnosis(diagnoseResult as ManagedDiagnosis);

      const preferred = String(
        stateResult.preferred_transport || stateResult.active_transport || "",
      ) as TunnelTransportName;
      if (manualChoices.includes(preferred)) setManualTransport(preferred);
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setTransportLoading(false);
    }
  };


  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(true), 15000);
    return () => window.clearInterval(timer);
  }, []);


  const openCreate = () => {
    setDraft({
      iran_node_id: iranNodes[0]?.id || 0,
      exit_node_id: exitNodes[0]?.id || 0,
      priority: 100,
    });
    setError("");
    setSuccess("");
    setCreateOpen(true);
  };


  const openManage = (tunnel: AdminTunnel) => {
    setSelected(tunnel);
    setTransportState(null);
    setDiagnosis(null);
    setHealth(null);
    setError("");
    setSuccess("");
    setManageOpen(true);
    void loadDetails(tunnel.id);
  };


  const createTunnel = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;

    if (!draft.iran_node_id || !draft.exit_node_id) {
      setError(pick("نود ایران و خارج را انتخاب کنید.", "Select Iran and Exit nodes."));
      return;
    }

    setBusy("create");
    setError("");
    setSuccess("");

    try {
      const result = await legacyControlApi.createManagedTunnel({
        iran_node_id: draft.iran_node_id,
        exit_node_id: draft.exit_node_id,
        transport: "auto",
        priority: draft.priority,
        is_active: true,
      });
      if (!result?.tunnel?.id) throw new Error("INVALID_MANAGED_TUNNEL_RESPONSE");
      setCreateOpen(false);
      setSuccess(pick("تانل از طریق پنل ساخته شد.", "Tunnel created by the panel."));
      await load(true);
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };


  const run = async (
    key: string,
    message: string,
    action: () => Promise<unknown>,
    refreshDetails = true,
  ) => {
    if (busy) return null;
    setBusy(key);
    setError("");
    setSuccess("");

    try {
      const result = await action();
      setSuccess(message);
      await load(true);
      if (selected && refreshDetails) await loadDetails(selected.id);
      return result;
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      return null;
    }
    finally {
      setBusy("");
    }
  };


  const diagnose = async () => {
    if (!selected) return;
    const result = await run(
      `diagnose-${selected.id}`,
      pick("عیب‌یابی پنل انجام شد.", "Panel diagnostics completed."),
      () => tunnelTransportApi.managedDiagnose(selected.id),
      false,
    );
    if (result) setDiagnosis(result as ManagedDiagnosis);
  };


  const checkHealth = async () => {
    if (!selected) return;
    const result = await run(
      `health-${selected.id}`,
      pick("Health دریافت شد.", "Health loaded."),
      () => tunnelTransportApi.health(selected.id),
      false,
    );
    if (result) setHealth(result);
  };


  const repair = async () => {
    if (!selected) return;
    if (!window.confirm(pick(
      `تعمیر خودکار تانل #${selected.id} اجرا شود؟`,
      `Run automatic repair for tunnel #${selected.id}?`,
    ))) return;

    await run(
      `repair-${selected.id}`,
      pick("تعمیر خودکار انجام شد.", "Automatic repair completed."),
      () => tunnelTransportApi.managedRepair(selected.id),
    );
  };


  const setAuto = async () => {
    if (!selected) return;
    await run(
      `auto-${selected.id}`,
      pick("حالت Auto فعال شد.", "Auto mode enabled."),
      () => tunnelTransportApi.setMode(selected.id, {mode: "auto"}),
    );
  };


  const setManual = async () => {
    if (!selected) return;
    if (!window.confirm(pick(
      `مسیر ${labelForTransport(manualTransport)} به‌صورت Manual اعمال شود؟`,
      `Apply ${labelForTransport(manualTransport)} in Manual mode?`,
    ))) return;

    await run(
      `manual-${selected.id}`,
      pick("مسیر Manual اعمال شد.", "Manual path applied."),
      () => tunnelTransportApi.setMode(selected.id, {
        mode: "manual",
        transport: manualTransport,
      }),
    );
  };


  const rebuild = async (name: "backhaul" | "mtunnel" | "ssh_tun") => {
    if (!selected) return;
    const label = labelForTransport(name);
    if (!window.confirm(pick(
      `${label} از داخل پنل بازسازی شود؟`,
      `Rebuild ${label} from the panel?`,
    ))) return;

    const action = name === "backhaul"
      ? () => tunnelTransportApi.installBackhaul(selected.id)
      : name === "mtunnel"
        ? () => tunnelTransportApi.installMtunnel(selected.id)
        : () => tunnelTransportApi.installSsh(selected.id);

    await run(
      `rebuild-${name}-${selected.id}`,
      pick(`${label} بازسازی شد.`, `${label} rebuilt.`),
      action,
    );
  };


  const toggleSelected = async () => {
    if (!selected) return;
    if (!window.confirm(pick(
      `وضعیت تانل #${selected.id} تغییر کند؟`,
      `Change tunnel #${selected.id} state?`,
    ))) return;

    await run(
      `toggle-${selected.id}`,
      pick("وضعیت تانل تغییر کرد.", "Tunnel state updated."),
      () => legacyControlApi.toggleTunnel(selected.id),
      false,
    );
  };


  const deleteSelected = async () => {
    if (!selected) return;
    if (!window.confirm(pick(
      `تانل #${selected.id} حذف شود؟`,
      `Delete tunnel #${selected.id}?`,
    ))) return;

    const id = selected.id;
    const result = await run(
      `delete-${id}`,
      pick("تانل حذف شد.", "Tunnel deleted."),
      () => legacyControlApi.deleteTunnel(id),
      false,
    );
    if (result !== null) {
      setManageOpen(false);
      setSelected(null);
      setTransportState(null);
    }
  };


  return (
    <Shell active="/admin/tunnels">
      <div className="page legacy-control-page">
        <div className="page-head">
          <div>
            <h1>{pick("تانل‌ها", "Tunnels")}</h1>
            <small>{pick(
              "ساخت، انتخاب مسیر، عیب‌یابی و تعمیر از پنل اصلی انجام می‌شود؛ SSH دستی لازم نیست.",
              "Creation, path selection, diagnostics and repair are handled by the main panel; manual SSH is not required.",
            )}</small>
          </div>
          <div className="action-row">
            <button className="ghost" disabled={loading || Boolean(busy)} onClick={() => void load()}>
              {loading ? "…" : pick("بروزرسانی", "Refresh")}
            </button>
            <button className="primary" disabled={Boolean(busy)} onClick={openCreate}>
              ＋ {pick("تانل جدید", "New tunnel")}
            </button>
          </div>
        </div>

        {error ? <div className="runtime-error">{error}</div> : null}
        {success ? <div className="runtime-success">{success}</div> : null}
        <div className="runtime-success">
          {pick(
            "کنترل متمرکز فعال است؛ پنل با دسترسی ذخیره‌شده نودها عملیات را اجرا می‌کند.",
            "Central control is active; the panel executes operations using saved node access.",
          )}
        </div>

        <div className="stats dashboard-stats">
          <Stat label={pick("کل تانل‌ها", "Total tunnels")} value={String(tunnels.length)} icon="⤨" />
          <Stat label={pick("آنلاین", "Online")} value={String(onlineCount)} icon="✓" />
          <Stat label="Degraded" value={String(degradedCount)} icon="◌" />
          <Stat label={pick("آفلاین", "Offline")} value={String(offlineCount)} icon="×" />
        </div>

        <Card>
          <div className="runtime-toolbar">
            <label>
              ⌕{" "}
              <input
                value={search}
                onChange={event => setSearch(event.target.value)}
                placeholder={pick("نام، IP یا شناسه...", "Name, IP or ID...")}
              />
            </label>
          </div>

          <div className="table">
            <table>
              <thead>
                <tr>
                  <th>{pick("مسیر", "Route")}</th>
                  <th>Ping</th>
                  <th>{pick("وضعیت", "Status")}</th>
                  <th>{pick("اجرا", "Enabled")}</th>
                  <th>{pick("عملیات", "Actions")}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(tunnel => {
                  const iran = nodeMap.get(tunnel.iran_node_id);
                  const exitNode = nodeMap.get(tunnel.exit_node_id);
                  return (
                    <tr key={tunnel.id}>
                      <td>
                        <div className="user-cell">
                          <b>{iran?.name || `#${tunnel.iran_node_id}`} → {exitNode?.name || `#${tunnel.exit_node_id}`}</b>
                          <small dir="ltr">{iran?.public_ip || "—"} → {exitNode?.public_ip || "—"}</small>
                        </div>
                      </td>
                      <td dir="ltr">{tunnel.latency_ms == null ? "—" : `${tunnel.latency_ms} ms`}</td>
                      <td><Badge tone={tone(tunnel.status)}>{String(tunnel.status || "—")}</Badge></td>
                      <td><Badge tone={tunnel.is_active ? "ok" : "warn"}>{tunnel.is_active ? pick("فعال", "Active") : pick("خاموش", "Disabled")}</Badge></td>
                      <td>
                        <div className="action-row">
                          <button className="primary-soft" disabled={Boolean(busy)} onClick={() => openManage(tunnel)}>
                            {pick("مدیریت کامل", "Full control")}
                          </button>
                          {onDeepDiagnostics ? (
                            <button
                              type="button"
                              className="ghost"
                              disabled={Boolean(busy)}
                              onClick={() => onDeepDiagnostics(tunnel.id)}
                            >
                              {pick("تشخیص عمیق", "Deep diagnostics")}
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {!filtered.length && !loading ? <div className="runtime-empty">{pick("تانلی پیدا نشد.", "No tunnels found.")}</div> : null}
          </div>
        </Card>

        {createOpen ? (
          <Modal
            title={pick("ساخت تانل", "Create tunnel")}
            sub={pick("نودها را انتخاب کنید؛ بقیه کارها با پنل است.", "Select the nodes; the panel handles the rest.")}
            onClose={() => !busy && setCreateOpen(false)}
          >
            <form onSubmit={createTunnel}>
              <div className="setting-grid">
                <label className="field">
                  <span>{pick("نود ایران", "Iran node")}</span>
                  <select value={draft.iran_node_id} onChange={event => setDraft(current => ({...current, iran_node_id: Number(event.target.value)}))}>
                    <option value={0}>{pick("انتخاب", "Select")}</option>
                    {iranNodes.map(node => <option key={node.id} value={node.id}>{node.name} · {node.public_ip}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>{pick("نود خارج", "Exit node")}</span>
                  <select value={draft.exit_node_id} onChange={event => setDraft(current => ({...current, exit_node_id: Number(event.target.value)}))}>
                    <option value={0}>{pick("انتخاب", "Select")}</option>
                    {exitNodes.map(node => <option key={node.id} value={node.id}>{node.name} · {node.public_ip}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span>{pick("اولویت", "Priority")}</span>
                  <input type="number" min={1} value={draft.priority} onChange={event => setDraft(current => ({...current, priority: Math.max(1, Number(event.target.value) || 1)}))} />
                </label>
              </div>
              <div className="runtime-warning">{pick("Provision، Health و Failover توسط خود پنل مدیریت می‌شود.", "Provisioning, health and failover are panel-managed.")}</div>
              <div className="modalActions">
                <button type="button" className="ghost" disabled={Boolean(busy)} onClick={() => setCreateOpen(false)}>{pick("انصراف", "Cancel")}</button>
                <button className="primary" disabled={busy === "create" || !draft.iran_node_id || !draft.exit_node_id}>{busy === "create" ? "…" : pick("ساخت", "Create")}</button>
              </div>
            </form>
          </Modal>
        ) : null}

        {manageOpen && selected ? (
          <Modal
            title={pick("مرکز کنترل تانل", "Tunnel control center")}
            sub={`#${selected.id} · ${nodeMap.get(selected.iran_node_id)?.name || selected.iran_node_id} → ${nodeMap.get(selected.exit_node_id)?.name || selected.exit_node_id}`}
            onClose={() => !busy && setManageOpen(false)}
          >
            <div className="runtime-success">{pick(
              "تمام عملیات این بخش از طریق پنل اجرا می‌شود؛ ورود SSH دستی به نودها لازم نیست.",
              "All operations here are panel-executed; manual SSH login to nodes is not required.",
            )}</div>

            <div className="runtime-info-list">
              <div><span>{pick("وضعیت", "Status")}</span><Badge tone={tone(selected.status)}>{String(selected.status || "—")}</Badge></div>
              <div><span>{pick("حالت", "Mode")}</span><Badge tone={tone(transportState?.mode)}>{String(transportState?.mode || "—")}</Badge></div>
              <div><span>{pick("فعال", "Active")}</span><b>{labelForTransport(transportState?.active_transport)}</b></div>
              <div><span>{pick("پیشنهادی", "Preferred")}</span><b>{labelForTransport(transportState?.preferred_transport)}</b></div>
              <div><span>{pick("آخرین سوییچ", "Last switch")}</span><b>{transportState?.last_switch_at ? new Date(String(transportState.last_switch_at)).toLocaleString("fa-IR") : "—"}</b></div>
            </div>

            <Card>
              <div className="card-head">
                <div><b>{pick("انتخاب مسیر", "Path selection")}</b><small>{pick("Auto برای Production پیشنهاد می‌شود.", "Auto is recommended for production.")}</small></div>
              </div>
              <div className="action-row">
                <button className={transportState?.mode === "auto" ? "primary" : "ghost"} disabled={Boolean(busy) || transportLoading} onClick={() => void setAuto()}>{busy === `auto-${selected.id}` ? "…" : "Auto"}</button>
                <select value={manualTransport} disabled={Boolean(busy) || transportLoading} onChange={event => setManualTransport(event.target.value as TunnelTransportName)}>
                  {manualChoices.map(name => <option key={name} value={name}>{labelForTransport(name)}</option>)}
                </select>
                <button className="ghost" disabled={Boolean(busy) || transportLoading} onClick={() => void setManual()}>{busy === `manual-${selected.id}` ? "…" : "Manual"}</button>
              </div>
            </Card>

            <Card>
              <div className="card-head">
                <div><b>{pick("وضعیت ترانسپورت‌ها", "Transport status")}</b><small>{pick("وضعیت، Ping، آخرین Health و خطای هر مسیر", "Status, latency, last health and error for each path")}</small></div>
                <button className="mini-btn" disabled={transportLoading || Boolean(busy)} onClick={() => void loadDetails(selected.id)}>{transportLoading ? "…" : "↻"}</button>
              </div>

              {transportLoading && !transportRows.length ? (
                <div className="runtime-loading">{pick("در حال دریافت…", "Loading…")}</div>
              ) : (
                <div className="module-grid three">
                  {transportRows.map((row, index) => {
                    const name = String(row.transport || `transport-${index}`);
                    const issueCode = String(diagnosisByName.get(name)?.issue_code || "");
                    return (
                      <div className="card transport-runtime-card" key={String(row.id || name)}>
                        <div className="card-head">
                          <div><b>{labelForTransport(name)}</b><small>Priority {String(row.priority ?? "—")}{name === String(transportState?.active_transport || "") ? ` · ${pick("فعال فعلی", "Active now")}` : ""}</small></div>
                          <Badge tone={tone(row.status)}>{String(row.status || "—")}</Badge>
                        </div>
                        <div className="runtime-info-list">
                          <div><span>{pick("فعال", "Enabled")}</span><b>{row.enabled ? pick("بله", "Yes") : pick("خیر", "No")}</b></div>
                          <div><span>Latency</span><b>{row.latency_ms == null ? "—" : `${row.latency_ms} ms`}</b></div>
                          <div><span>{pick("آخرین سلامت", "Last healthy")}</span><b>{row.last_healthy_at ? new Date(String(row.last_healthy_at)).toLocaleString("fa-IR") : "—"}</b></div>
                          {issueCode ? <div><span>{pick("تشخیص", "Issue")}</span><b>{issueCode}</b></div> : null}
                        </div>
                        {row.last_error ? <div className="runtime-error compact" dir="ltr">{String(row.last_error)}</div> : null}
                      </div>
                    );
                  })}
                </div>
              )}
            </Card>

            {diagnosis ? (
              <Card>
                <div className="card-head">
                  <div><b>{pick("نتیجه عیب‌یابی", "Diagnostics result")}</b><small>Read-only</small></div>
                  <Badge tone={diagnosis.operational ? "ok" : "bad"}>{diagnosis.operational ? pick("عملیاتی", "Operational") : pick("نیازمند بررسی", "Needs attention")}</Badge>
                </div>
                <div className="runtime-info-list">
                  <div><span>{pick("کامل", "Complete")}</span><b>{diagnosis.complete ? pick("بله", "Yes") : pick("خیر", "No")}</b></div>
                  <div><span>{pick("مسیرهای سالم", "Online paths")}</span><b dir="ltr">{diagnosis.selectable_online?.join(", ") || "—"}</b></div>
                  <div><span>{pick("نیازمند تعمیر", "Repair needed")}</span><b dir="ltr">{diagnosis.repair_needed?.join(", ") || "—"}</b></div>
                </div>
              </Card>
            ) : null}

            <Card>
              <div className="card-head"><div><b>{pick("عملیات پنل", "Panel operations")}</b><small>{pick("همه عملیات از کنترلر اجرا می‌شود.", "All operations are initiated by the controller.")}</small></div></div>
              <div className="action-grid">
                <button className="primary-soft" disabled={Boolean(busy)} onClick={() => void diagnose()}>{busy === `diagnose-${selected.id}` ? "…" : pick("عیب‌یابی", "Diagnose")}</button>
                <button className="ghost" disabled={Boolean(busy)} onClick={() => void checkHealth()}>{busy === `health-${selected.id}` ? "…" : pick("تست سلامت", "Health check")}</button>
                <button className="primary" disabled={Boolean(busy)} onClick={() => void repair()}>{busy === `repair-${selected.id}` ? "…" : pick("تعمیر خودکار", "Automatic repair")}</button>
                <button className="ghost" disabled={Boolean(busy)} onClick={() => void rebuild("backhaul")}>Rebuild Backhaul</button>
                <button className="ghost" disabled={Boolean(busy)} onClick={() => void rebuild("mtunnel")}>Rebuild MTunnel</button>
                <button className="ghost" disabled={Boolean(busy)} onClick={() => void rebuild("ssh_tun")}>Rebuild SSH TUN</button>
              </div>
            </Card>

            {health !== null ? (
              <Card>
                <div className="card-head"><b>{pick("خروجی Health", "Health output")}</b><button className="mini-btn" onClick={() => setHealth(null)}>×</button></div>
                <pre className="runtime-log" dir="ltr">{JSON.stringify(health, null, 2)}</pre>
              </Card>
            ) : null}

            <div className="modalActions">
              <button className="ghost" disabled={Boolean(busy)} onClick={() => void toggleSelected()}>{selected.is_active ? pick("غیرفعال کردن", "Disable") : pick("فعال کردن", "Enable")}</button>
              <button className="danger" disabled={Boolean(busy)} onClick={() => void deleteSelected()}>{pick("حذف تانل", "Delete tunnel")}</button>
            </div>
          </Modal>
        ) : null}
      </div>
    </Shell>
  );
}
