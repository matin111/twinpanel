"use client";

import {
  FormEvent,
  ReactNode,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  Badge,
  Card,
  Shell,
  Stat,
} from "./ui";
import type {
  AdminNode,
  AdminTunnel,
} from "../lib/admin-api";
import {
  legacyControlApi,
} from "../lib/legacy-control-api";
import {
  TunnelTransportName,
  TunnelTransportRow,
  TunnelTransportState,
  tunnelTransportApi,
} from "../lib/tunnel-transport-api";
import {
  useI18n,
} from "../lib/i18n";


type Draft = {
  iran_node_id: number;
  exit_node_id: number;
  priority: number;
};


type JsonRow = Record<string, unknown>;


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


function enumText(value: unknown) {
  return String(value ?? "")
    .trim()
    .toLowerCase();
}


function valueText(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  return String(value);
}


function statusTone(
  value: unknown,
): "ok" | "warn" | "bad" | "violet" {
  const status = enumText(value);

  if (["online", "active", "healthy", "ok", "ready", "standby"].includes(status)) {
    return status === "standby" ? "warn" : "ok";
  }

  if (["offline", "failed", "error", "down", "stopped"].includes(status)) {
    return "bad";
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
    <div
      className="runtime-modal"
      role="dialog"
      aria-modal="true"
    >
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
            {sub && <small>{sub}</small>}
          </div>

          <button
            type="button"
            className="icon-button"
            onClick={onClose}
          >
            ×
          </button>
        </div>

        {children}
      </div>
    </div>
  );
}


export function TunnelsPanelRuntimeV31() {
  const {pick} = useI18n();

  const [tunnels, setTunnels] = useState<AdminTunnel[]>([]);
  const [nodes, setNodes] = useState<AdminNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const [selected, setSelected] = useState<AdminTunnel | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);

  const [transportState, setTransportState] = useState<TunnelTransportState | null>(null);
  const [transportLoading, setTransportLoading] = useState(false);
  const [diagnosis, setDiagnosis] = useState<JsonRow | null>(null);
  const [health, setHealth] = useState<JsonRow | null>(null);
  const [manualTransport, setManualTransport] = useState<TunnelTransportName>("quic_2027");


  const load = async (silent = false) => {
    if (!silent) {
      setLoading(true);
    }

    setError("");

    try {
      const [tunnelRows, nodeRows] = await Promise.all([
        legacyControlApi.tunnels(),
        legacyControlApi.nodes(),
      ]);

      setTunnels(tunnelRows);
      setNodes(nodeRows);

      setSelected(current => {
        if (!current) {
          return null;
        }

        return tunnelRows.find(row => row.id === current.id) || null;
      });
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      if (!silent) {
        setLoading(false);
      }
    }
  };


  const loadTransportDetails = async (
    tunnelId: number,
    includeDiagnosis = true,
  ) => {
    setTransportLoading(true);
    setError("");

    try {
      const statePromise = tunnelTransportApi.transports(tunnelId);
      const diagnosisPromise = includeDiagnosis
        ? tunnelTransportApi.managedDiagnose(tunnelId)
        : Promise.resolve(null);

      const [stateResult, diagnosisResult] = await Promise.all([
        statePromise,
        diagnosisPromise,
      ]);

      setTransportState(stateResult);

      if (diagnosisResult) {
        setDiagnosis(diagnosisResult);
      }

      const preferred = String(
        stateResult.preferred_transport
        || stateResult.active_transport
        || "",
      ) as TunnelTransportName;

      if (manualChoices.includes(preferred)) {
        setManualTransport(preferred);
      }
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

    const timer = window.setInterval(
      () => void load(true),
      15000,
    );

    return () => window.clearInterval(timer);
  }, []);


  const nodeMap = useMemo(
    () => new Map(nodes.map(row => [row.id, row])),
    [nodes],
  );


  const iranNodes = nodes.filter(
    row => enumText(row.node_type) === "iran",
  );

  const exitNodes = nodes.filter(
    row => enumText(row.node_type) === "exit",
  );


  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query) {
      return tunnels;
    }

    return tunnels.filter(row => {
      const iran = nodeMap.get(row.iran_node_id);
      const exitNode = nodeMap.get(row.exit_node_id);

      return (
        `${row.id} ${row.status || ""} `
        + `${iran?.name || ""} ${iran?.public_ip || ""} `
        + `${exitNode?.name || ""} ${exitNode?.public_ip || ""}`
      )
        .toLowerCase()
        .includes(query);
    });
  }, [tunnels, search, nodeMap]);


  const onlineCount = tunnels.filter(
    row => enumText(row.status) === "online",
  ).length;

  const degradedCount = tunnels.filter(
    row => enumText(row.status) === "degraded",
  ).length;

  const offlineCount = Math.max(
    0,
    tunnels.length - onlineCount - degradedCount,
  );


  const transports: TunnelTransportRow[] = (
    transportState && Array.isArray(transportState.transports)
      ? transportState.transports
      : []
  );


  const diagnosisTransports = (
    diagnosis && Array.isArray(diagnosis.transports)
      ? diagnosis.transports as JsonRow[]
      : []
  );


  const diagnosisByName = useMemo(
    () => new Map(
      diagnosisTransports.map(row => [
        String(row.transport || ""),
        row,
      ]),
    ),
    [diagnosisTransports],
  );


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


  const openManage = async (tunnel: AdminTunnel) => {
    setSelected(tunnel);
    setTransportState(null);
    setDiagnosis(null);
    setHealth(null);
    setError("");
    setSuccess("");
    setManageOpen(true);
    await loadTransportDetails(tunnel.id, true);
  };


  const createTunnel = async (event: FormEvent) => {
    event.preventDefault();

    if (busy) {
      return;
    }

    if (!draft.iran_node_id || !draft.exit_node_id) {
      setError(pick(
        "نود ایران و نود خارج را انتخاب کنید.",
        "Select Iran and Exit nodes.",
      ));
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

      if (!result?.tunnel?.id) {
        throw new Error(pick(
          "پاسخ ساخت تانل معتبر نبود.",
          "Tunnel creation returned an invalid response.",
        ));
      }

      setCreateOpen(false);
      setSuccess(pick(
        "تانل ساخته شد و تمام مدیریت مسیر به پنل سپرده شد.",
        "Tunnel created and path management is now controlled by the panel.",
      ));
      await load(true);
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };


  const runAction = async (
    key: string,
    successMessage: string,
    action: () => Promise<unknown>,
    options: {
      refreshTransport?: boolean;
      resultTarget?: "diagnosis" | "health";
    } = {},
  ) => {
    if (busy) {
      return;
    }

    setBusy(key);
    setError("");
    setSuccess("");

    try {
      const result = await action();

      if (options.resultTarget === "diagnosis") {
        setDiagnosis(result as JsonRow);
      }

      if (options.resultTarget === "health") {
        setHealth(result as JsonRow);
      }

      setSuccess(successMessage);
      await load(true);

      if (selected && options.refreshTransport !== false) {
        await loadTransportDetails(selected.id, true);
      }
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };


  const repair = async (tunnel: AdminTunnel) => {
    if (!window.confirm(pick(
      `تعمیر خودکار تانل #${tunnel.id} از طریق پنل اجرا شود؟`,
      `Run panel-managed repair for tunnel #${tunnel.id}?`,
    ))) {
      return;
    }

    await runAction(
      `repair-${tunnel.id}`,
      pick("تعمیر خودکار پنل انجام شد.", "Panel-managed repair completed."),
      () => tunnelTransportApi.managedRepair(tunnel.id),
    );
  };


  const rebuild = async (
    tunnel: AdminTunnel,
    transport: "backhaul" | "mtunnel" | "ssh_tun",
  ) => {
    const label = transportLabels[transport] || transport;

    if (!window.confirm(pick(
      `${label} برای تانل #${tunnel.id} از داخل پنل بازسازی شود؟`,
      `Rebuild ${label} for tunnel #${tunnel.id} from the panel?`,
    ))) {
      return;
    }

    const action = transport === "backhaul"
      ? () => tunnelTransportApi.installBackhaul(tunnel.id)
      : transport === "mtunnel"
        ? () => tunnelTransportApi.installMtunnel(tunnel.id)
        : () => tunnelTransportApi.installSsh(tunnel.id);

    await runAction(
      `rebuild-${transport}-${tunnel.id}`,
      pick(`${label} بازسازی شد.`, `${label} rebuild completed.`),
      action,
    );
  };


  const setAuto = async (tunnel: AdminTunnel) => {
    await runAction(
      `auto-${tunnel.id}`,
      pick("انتخاب مسیر روی Auto قرار گرفت.", "Path selection set to Auto."),
      () => tunnelTransportApi.setMode(tunnel.id, {mode: "auto"}),
    );
  };


  const setManual = async (tunnel: AdminTunnel) => {
    if (!window.confirm(pick(
      `مسیر ${transportLabels[manualTransport] || manualTransport} به‌صورت دستی فعال شود؟`,
      `Switch to ${transportLabels[manualTransport] || manualTransport} in Manual mode?`,
    ))) {
      return;
    }

    await runAction(
      `manual-${tunnel.id}`,
      pick("مسیر دستی ذخیره شد.", "Manual path saved."),
      () => tunnelTransportApi.setMode(tunnel.id, {
        mode: "manual",
        transport: manualTransport,
      }),
    );
  };


  const diagnose = async (tunnel: AdminTunnel) => {
    await runAction(
      `diagnose-${tunnel.id}`,
      pick("عیب‌یابی از پنل انجام شد.", "Panel diagnostics completed."),
      () => tunnelTransportApi.managedDiagnose(tunnel.id),
      {
        refreshTransport: false,
        resultTarget: "diagnosis",
      },
    );
  };


  const checkHealth = async (tunnel: AdminTunnel) => {
    await runAction(
      `health-${tunnel.id}`,
      pick("وضعیت سلامت دریافت شد.", "Tunnel health loaded."),
      () => tunnelTransportApi.health(tunnel.id),
      {
        refreshTransport: false,
        resultTarget: "health",
      },
    );
  };


  const toggle = async (tunnel: AdminTunnel) => {
    const enable = !tunnel.is_active;

    if (!window.confirm(
      enable
        ? pick(`تانل #${tunnel.id} فعال شود؟`, `Enable tunnel #${tunnel.id}?`)
        : pick(`تانل #${tunnel.id} غیرفعال شود؟`, `Disable tunnel #${tunnel.id}?`),
    )) {
      return;
    }

    await runAction(
      `toggle-${tunnel.id}`,
      pick("وضعیت تانل تغییر کرد.", "Tunnel state updated."),
      () => legacyControlApi.toggleTunnel(tunnel.id),
    );
  };


  const remove = async (tunnel: AdminTunnel) => {
    if (!window.confirm(pick(
      `تانل #${tunnel.id} حذف شود؟`,
      `Delete tunnel #${tunnel.id}?`,
    ))) {
      return;
    }

    await runAction(
      `delete-${tunnel.id}`,
      pick("تانل حذف شد.", "Tunnel deleted."),
      () => legacyControlApi.deleteTunnel(tunnel.id),
      {refreshTransport: false},
    );

    setManageOpen(false);
    setSelected(null);
    setTransportState(null);
  };


  return (
    <Shell active="/admin/tunnels">
      <div className="page legacy-control-page">
        <div className="page-head">
          <div>
            <h1>{pick("تانل‌ها", "Tunnels")}</h1>
            <small>
              {pick(
                "ساخت، انتخاب مسیر، عیب‌یابی و تعمیر از همین پنل انجام می‌شود؛ برای مدیریت تانل نیازی به SSH دستی به نودها نیست.",
                "Creation, path selection, diagnostics and repair are handled here; tunnel management requires no manual SSH to nodes.",
              )}
            </small>
          </div>

          <div className="action-row">
            <button
              type="button"
              className="ghost"
              disabled={loading || Boolean(busy)}
              onClick={() => void load()}
            >
              {loading ? "…" : pick("بروزرسانی", "Refresh")}
            </button>

            <button
              type="button"
              className="primary"
              disabled={Boolean(busy)}
              onClick={openCreate}
            >
              ＋ {pick("تانل جدید", "New tunnel")}
            </button>
          </div>
        </div>

        {error && <div className="runtime-error">{error}</div>}
        {success && <div className="runtime-success">{success}</div>}

        <div className="runtime-success">
          {pick(
            "کنترل متمرکز فعال است: پنل از دسترسی ذخیره‌شده نودها استفاده می‌کند و عملیات مدیریتی را خودش اجرا می‌کند.",
            "Central control is active: the panel uses saved node access and executes management operations itself.",
          )}
        </div>

        <div className="stats dashboard-stats">
          <Stat
            label={pick("کل تانل‌ها", "Total tunnels")}
            value={tunnels.length.toLocaleString("fa-IR")}
            icon="⤨"
          />
          <Stat
            label={pick("آنلاین", "Online")}
            value={onlineCount.toLocaleString("fa-IR")}
            icon="✓"
          />
          <Stat
            label="Degraded"
            value={degradedCount.toLocaleString("fa-IR")}
            icon="◌"
          />
          <Stat
            label={pick("آفلاین", "Offline")}
            value={offlineCount.toLocaleString("fa-IR")}
            icon="×"
          />
        </div>

        <Card>
          <div className="runtime-toolbar">
            <label>
              ⌕{" "}
              <input
                value={search}
                onChange={event => setSearch(event.target.value)}
                placeholder={pick(
                  "نام سرور، IP یا شناسه...",
                  "Server, IP or ID...",
                )}
              />
            </label>
          </div>

          <div className="table">
            <table>
              <thead>
                <tr>
                  <th>{pick("مسیر", "Route")}</th>
                  <th>Ping</th>
                  <th>{pick("اولویت", "Priority")}</th>
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
                          <b>
                            {iran?.name || `#${tunnel.iran_node_id}`}
                            {" → "}
                            {exitNode?.name || `#${tunnel.exit_node_id}`}
                          </b>
                          <small dir="ltr">
                            {iran?.public_ip || "—"}
                            {" → "}
                            {exitNode?.public_ip || "—"}
                          </small>
                        </div>
                      </td>

                      <td dir="ltr">
                        {tunnel.latency_ms == null ? "—" : `${tunnel.latency_ms} ms`}
                      </td>

                      <td>{Number(tunnel.priority || 0).toLocaleString("fa-IR")}</td>

                      <td>
                        <Badge tone={statusTone(tunnel.status)}>
                          {String(tunnel.status || "—")}
                        </Badge>
                      </td>

                      <td>
                        <Badge tone={tunnel.is_active ? "ok" : "warn"}>
                          {tunnel.is_active
                            ? pick("فعال", "Active")
                            : pick("خاموش", "Disabled")}
                        </Badge>
                      </td>

                      <td>
                        <div className="row-actions">
                          <button
                            type="button"
                            className="primary-soft"
                            disabled={Boolean(busy)}
                            onClick={() => void openManage(tunnel)}
                          >
                            {pick("مدیریت کامل", "Full control")}
                          </button>

                          <button
                            type="button"
                            disabled={Boolean(busy)}
                            onClick={() => void diagnose(tunnel)}
                          >
                            {busy === `diagnose-${tunnel.id}`
                              ? "…"
                              : pick("عیب‌یابی", "Diagnose")}
                          </button>

                          <button
                            type="button"
                            disabled={Boolean(busy)}
                            onClick={() => void repair(tunnel)}
                          >
                            {busy === `repair-${tunnel.id}`
                              ? "…"
                              : pick("تعمیر", "Repair")}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {!filtered.length && !loading && (
              <div className="runtime-empty">
                {pick("تانلی پیدا نشد.", "No tunnels found.")}
              </div>
            )}
          </div>
        </Card>

        {createOpen && (
          <Modal
            title={pick("ساخت تانل", "Create tunnel")}
            sub={pick(
              "فقط نود ایران و نود خارج را انتخاب کنید؛ نصب و انتخاب مسیر توسط پنل انجام می‌شود.",
              "Select Iran and Exit nodes only; installation and path selection are panel-managed.",
            )}
            onClose={() => {
              if (!busy) {
                setCreateOpen(false);
              }
            }}
          >
            <form onSubmit={createTunnel}>
              {(!iranNodes.length || !exitNodes.length) && (
                <div className="runtime-warning">
                  {pick(
                    "حداقل یک نود ایران و یک نود خارج لازم است.",
                    "At least one Iran and one Exit node are required.",
                  )}
                </div>
              )}

              <div className="setting-grid">
                <label className="field">
                  <span>{pick("نود ایران", "Iran node")}</span>
                  <select
                    value={draft.iran_node_id}
                    onChange={event => setDraft(current => ({
                      ...current,
                      iran_node_id: Number(event.target.value),
                    }))}
                  >
                    <option value={0}>{pick("انتخاب", "Select")}</option>
                    {iranNodes.map(node => (
                      <option key={node.id} value={node.id}>
                        {node.name} · {node.public_ip}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field">
                  <span>{pick("نود خارج", "Exit node")}</span>
                  <select
                    value={draft.exit_node_id}
                    onChange={event => setDraft(current => ({
                      ...current,
                      exit_node_id: Number(event.target.value),
                    }))}
                  >
                    <option value={0}>{pick("انتخاب", "Select")}</option>
                    {exitNodes.map(node => (
                      <option key={node.id} value={node.id}>
                        {node.name} · {node.public_ip}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field">
                  <span>{pick("اولویت", "Priority")}</span>
                  <input
                    type="number"
                    min={1}
                    value={draft.priority}
                    onChange={event => setDraft(current => ({
                      ...current,
                      priority: Math.max(1, Number(event.target.value) || 1),
                    }))}
                  />
                </label>
              </div>

              <div className="runtime-warning">
                {pick(
                  "پنل مسیرهای داخلی، Failover، Health و Repair را مدیریت می‌کند؛ SSH دستی جزو روند کار نیست.",
                  "The panel owns internal paths, failover, health and repair; manual SSH is not part of the workflow.",
                )}
              </div>

              <div className="modalActions">
                <button
                  type="button"
                  className="ghost"
                  disabled={Boolean(busy)}
                  onClick={() => setCreateOpen(false)}
                >
                  {pick("انصراف", "Cancel")}
                </button>

                <button
                  className="primary"
                  disabled={
                    busy === "create"
                    || !draft.iran_node_id
                    || !draft.exit_node_id
                  }
                >
                  {busy === "create"
                    ? pick("در حال ساخت...", "Creating...")
                    : pick("ساخت تانل", "Create tunnel")}
                </button>
              </div>
            </form>
          </Modal>
        )}

        {manageOpen && selected && (
          <Modal
            title={pick("مرکز کنترل تانل", "Tunnel control center")}
            sub={`#${selected.id} · ${nodeMap.get(selected.iran_node_id)?.name || selected.iran_node_id} → ${nodeMap.get(selected.exit_node_id)?.name || selected.exit_node_id}`}
            onClose={() => {
              if (!busy) {
                setManageOpen(false);
              }
            }}
          >
            <div className="runtime-success">
              {pick(
                "تمام عملیات این بخش توسط پنل روی نودهای مربوط اجرا می‌شود. نیازی به ورود SSH دستی به ایران یا خارج نیست.",
                "All operations here are executed by the panel on the related nodes. No manual SSH login to Iran or Exit is required.",
              )}
            </div>

            <div className="runtime-info-list">
              <div>
                <span>{pick("وضعیت تانل", "Tunnel status")}</span>
                <Badge tone={statusTone(selected.status)}>
                  {String(selected.status || "—")}
                </Badge>
              </div>
              <div>
                <span>{pick("حالت", "Mode")}</span>
                <b>{valueText(transportState?.mode)}</b>
              </div>
              <div>
                <span>{pick("مسیر فعال", "Active path")}</span>
                <b>{transportLabels[String(transportState?.active_transport || "")] || valueText(transportState?.active_transport)}</b>
              </div>
              <div>
                <span>{pick("مسیر پیشنهادی", "Preferred path")}</span>
                <b>{transportLabels[String(transportState?.preferred_transport || "")] || valueText(transportState?.preferred_transport)}</b>
              </div>
              <div>
                <span>{pick("آخرین سوییچ", "Last switch")}</span>
                <b>
                  {transportState?.last_switch_at
                    ? new Date(String(transportState.last_switch_at)).toLocaleString("fa-IR")
                    : "—"}
                </b>
              </div>
              <div>
                <span>Ping</span>
                <b dir="ltr">
                  {selected.latency_ms == null ? "—" : `${selected.latency_ms} ms`}
                </b>
              </div>
            </div>

            <Card>
              <div className="card-head">
                <div>
                  <b>{pick("انتخاب مسیر", "Path selection")}</b>
                  <small>{pick("Auto حالت پیشنهادی Production است.", "Auto is the recommended production mode.")}</small>
                </div>
                <Badge tone={transportState?.mode === "manual" ? "violet" : "ok"}>
                  {String(transportState?.mode || "—")}
                </Badge>
              </div>

              <div className="action-row">
                <button
                  type="button"
                  className={transportState?.mode === "auto" ? "primary" : "ghost"}
                  disabled={Boolean(busy) || transportLoading}
                  onClick={() => void setAuto(selected)}
                >
                  {busy === `auto-${selected.id}` ? "…" : "Auto"}
                </button>

                <select
                  value={manualTransport}
                  disabled={Boolean(busy) || transportLoading}
                  onChange={event => setManualTransport(event.target.value as TunnelTransportName)}
                >
                  {manualChoices.map(name => (
                    <option key={name} value={name}>
                      {transportLabels[name]}
                    </option>
                  ))}
                </select>

                <button
                  type="button"
                  className="ghost"
                  disabled={Boolean(busy) || transportLoading}
                  onClick={() => void setManual(selected)}
                >
                  {busy === `manual-${selected.id}`
                    ? "…"
                    : pick("اعمال Manual", "Apply Manual")}
                </button>
              </div>
            </Card>

            <Card>
              <div className="card-head">
                <div>
                  <b>{pick("ترانسپورت‌ها", "Transports")}</b>
                  <small>{pick("وضعیت هر مسیر، Ping و خطای آخر مستقیماً از پنل نمایش داده می‌شود.", "Each path status, latency and last error are shown directly in the panel.")}</small>
                </div>
                <button
                  type="button"
                  className="mini-btn"
                  disabled={transportLoading || Boolean(busy)}
                  onClick={() => void loadTransportDetails(selected.id, true)}
                >
                  {transportLoading ? "…" : "↻"}
                </button>
              </div>

              {transportLoading && !transports.length ? (
                <div className="runtime-loading">
                  {pick("در حال دریافت وضعیت مسیرها…", "Loading transport state…")}
                </div>
              ) : transports.length ? (
                <div className="module-grid three">
                  {transports.map((row, index) => {
                    const name = String(row.transport || `transport-${index}`);
                    const diagnoseRow = diagnosisByName.get(name);
                    const issueCode = diagnoseRow?.issue_code;

                    return (
                      <div className="card transport-runtime-card" key={String(row.id || name)}>
                        <div className="card-head">
                          <div>
                            <b>{transportLabels[name] || name}</b>
                            <small>
                              Priority {valueText(row.priority)}
                              {name === String(transportState?.active_transport || "")
                                ? ` · ${pick("فعال فعلی", "Active now")}`
                                : ""}
                            </small>
                          </div>
                          <Badge tone={statusTone(row.status)}>
                            {valueText(row.status)}
                          </Badge>
                        </div>

                        <div className="runtime-info-list">
                          <div>
                            <span>{pick("فعال", "Enabled")}</span>
                            <b>{row.enabled ? pick("بله", "Yes") : pick("خیر", "No")}</b>
                          </div>
                          <div>
                            <span>Latency</span>
                            <b>{row.latency_ms == null ? "—" : `${row.latency_ms} ms`}</b>
                          </div>
                          <div>
                            <span>{pick("آخرین سلامت", "Last healthy")}</span>
                            <b>
                              {row.last_healthy_at
                                ? new Date(String(row.last_healthy_at)).toLocaleString("fa-IR")
                                : "—"}
                            </b>
                          </div>
                          {issueCode && (
                            <div>
                              <span>{pick("تشخیص", "Issue")}</span>
                              <b>{String(issueCode)}</b>
                            </div>
                          )}
                        </div>

                        {row.last_error && (
                          <div className="runtime-error compact" dir="ltr">
                            {String(row.last_error)}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="runtime-empty">
                  {pick("برای این تانل ترانسپورتی ثبت نشده است.", "No transports are registered for this tunnel.")}
                </div>
              )}
            </Card>

            {diagnosis && (
              <Card>
                <div className="card-head">
                  <div>
                    <b>{pick("نتیجه عیب‌یابی", "Diagnostics result")}</b>
                    <small>
                      {pick(
                        "Read-only: این بخش چیزی را تغییر نمی‌دهد.",
                        "Read-only: this section does not change runtime state.",
                      )}
                    </small>
                  </div>
                  <Badge tone={diagnosis.operational ? "ok" : "bad"}>
                    {diagnosis.operational
                      ? pick("عملیاتی", "Operational")
                      : pick("نیازمند بررسی", "Needs attention")}
                  </Badge>
                </div>

                <div className="runtime-info-list">
                  <div>
                    <span>{pick("کامل", "Complete")}</span>
                    <b>{diagnosis.complete ? pick("بله", "Yes") : pick("خیر", "No")}</b>
                  </div>
                  <div>
                    <span>{pick("مسیرهای سالم", "Selectable online")}</span>
                    <b dir="ltr">
                      {Array.isArray(diagnosis.selectable_online)
                        ? diagnosis.selectable_online.join(", ") || "—"
                        : "—"}
                    </b>
                  </div>
                  <div>
                    <span>{pick("نیازمند تعمیر", "Repair needed")}</span>
                    <b dir="ltr">
                      {Array.isArray(diagnosis.repair_needed)
                        ? diagnosis.repair_needed.join(", ") || "—"
                        : "—"}
                    </b>
                  </div>
                </div>
              </Card>
            )}

            <Card>
              <div className="card-head">
                <div>
                  <b>{pick("عملیات پنل", "Panel operations")}</b>
                  <small>{pick("همه عملیات از کنترلر و با دسترسی ذخیره‌شده نودها انجام می‌شود.", "All operations are initiated by the controller using saved node access.")}</small>
                </div>
              </div>

              <div className="action-grid">
                <button
                  type="button"
                  className="primary-soft"
                  disabled={Boolean(busy)}
                  onClick={() => void diagnose(selected)}
                >
                  {busy === `diagnose-${selected.id}`
                    ? "…"
                    : pick("عیب‌یابی", "Diagnose")}
                </button>

                <button
                  type="button"
                  className="ghost"
                  disabled={Boolean(busy)}
                  onClick={() => void checkHealth(selected)}
                >
                  {busy === `health-${selected.id}`
                    ? "…"
                    : pick("تست سلامت", "Health check")}
                </button>

                <button
                  type="button"
                  className="primary"
                  disabled={Boolean(busy)}
                  onClick={() => void repair(selected)}
                >
                  {busy === `repair-${selected.id}`
                    ? "…"
                    : pick("تعمیر خودکار", "Automatic repair")}
                </button>

                <button
                  type="button"
                  className="ghost"
                  disabled={Boolean(busy)}
                  onClick={() => void rebuild(selected, "backhaul")}
                >
                  {busy === `rebuild-backhaul-${selected.id}` ? "…" : "Rebuild Backhaul"}
                </button>

                <button
                  type="button"
                  className="ghost"
                  disabled={Boolean(busy)}
                  onClick={() => void rebuild(selected, "mtunnel")}
                >
                  {busy === `rebuild-mtunnel-${selected.id}` ? "…" : "Rebuild MTunnel"}
                </button>

                <button
                  type="button"
                  className="ghost"
                  disabled={Boolean(busy)}
                  onClick={() => void rebuild(selected, "ssh_tun")}
                >
                  {busy === `rebuild-ssh_tun-${selected.id}` ? "…" : "Rebuild SSH TUN"}
                </button>
              </div>
            </Card>

            {health && (
              <Card>
                <div className="card-head">
                  <b>{pick("خروجی Health", "Health output")}</b>
                  <button type="button" className="mini-btn" onClick={() => setHealth(null)}>×</button>
                </div>
                <pre className="runtime-log" dir="ltr">
                  {JSON.stringify(health, null, 2)}
                </pre>
              </Card>
            )}

            <div className="modalActions">
              <button
                type="button"
                className="ghost"
                disabled={Boolean(busy)}
                onClick={() => void toggle(selected)}
              >
                {selected.is_active
                  ? pick("غیرفعال کردن", "Disable")
                  : pick("فعال کردن", "Enable")}
              </button>

              <button
                type="button"
                className="danger"
                disabled={Boolean(busy)}
                onClick={() => void remove(selected)}
              >
                {pick("حذف تانل", "Delete tunnel")}
              </button>
            </div>
          </Modal>
        )}
      </div>
    </Shell>
  );
}
