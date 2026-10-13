"use client";

import {
  FormEvent,
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


const emptyDraft: Draft = {
  iran_node_id: 0,
  exit_node_id: 0,
  priority: 100,
};


function enumText(value: unknown) {
  return String(value ?? "")
    .trim()
    .toLowerCase();
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
  children: React.ReactNode;
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


export function TunnelsSimpleRuntimePage() {
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

        return (
          tunnelRows.find(row => row.id === current.id)
          || null
        );
      });
    }
    catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : String(reason),
      );
    }
    finally {
      if (!silent) {
        setLoading(false);
      }
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


  const tone = (
    status: unknown,
  ): "ok" | "warn" | "bad" => {
    const value = enumText(status);

    if (value === "online") {
      return "ok";
    }

    if (value === "degraded") {
      return "warn";
    }

    return "bad";
  };


  const runAction = async (
    key: string,
    successMessage: string,
    action: () => Promise<unknown>,
  ) => {
    if (busy) {
      return;
    }

    setBusy(key);
    setError("");
    setSuccess("");

    try {
      await action();
      setSuccess(successMessage);
      await load(true);
    }
    catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : String(reason),
      );
    }
    finally {
      setBusy("");
    }
  };


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


  const createTunnel = async (event: FormEvent) => {
    event.preventDefault();

    if (busy) {
      return;
    }

    if (!draft.iran_node_id || !draft.exit_node_id) {
      setError(
        pick(
          "نود ایران و نود خارج را انتخاب کنید.",
          "Select Iran and Exit nodes.",
        ),
      );
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
        throw new Error(
          pick(
            "پاسخ ساخت تانل معتبر نبود.",
            "Tunnel creation returned an invalid response.",
          ),
        );
      }

      setCreateOpen(false);
      setSuccess(
        pick(
          "تانل ساخته شد و مدیریت مسیر به سیستم سپرده شد.",
          "Tunnel created and route management is automatic.",
        ),
      );
      await load(true);
    }
    catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : String(reason),
      );
    }
    finally {
      setBusy("");
    }
  };


  const repair = async (tunnel: AdminTunnel) => {
    if (!window.confirm(
      pick(
        `تعمیر خودکار تانل #${tunnel.id} اجرا شود؟`,
        `Run automatic repair for tunnel #${tunnel.id}?`,
      ),
    )) {
      return;
    }

    await runAction(
      `repair-${tunnel.id}`,
      pick("تعمیر خودکار اجرا شد.", "Automatic repair completed."),
      () => tunnelTransportApi.managedRepair(tunnel.id),
    );
  };


  const toggle = async (tunnel: AdminTunnel) => {
    const enable = !tunnel.is_active;

    if (!window.confirm(
      enable
        ? pick(
            `تانل #${tunnel.id} فعال شود؟`,
            `Enable tunnel #${tunnel.id}?`,
          )
        : pick(
            `تانل #${tunnel.id} غیرفعال شود؟`,
            `Disable tunnel #${tunnel.id}?`,
          ),
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
    if (!window.confirm(
      pick(
        `تانل #${tunnel.id} حذف شود؟`,
        `Delete tunnel #${tunnel.id}?`,
      ),
    )) {
      return;
    }

    await runAction(
      `delete-${tunnel.id}`,
      pick("تانل حذف شد.", "Tunnel deleted."),
      () => legacyControlApi.deleteTunnel(tunnel.id),
    );

    setManageOpen(false);
    setSelected(null);
  };


  return (
    <Shell active="/admin/tunnels">
      <div className="page legacy-control-page">
        <div className="page-head">
          <div>
            <h1>{pick("تانل‌ها", "Tunnels")}</h1>
            <small>
              {pick(
                "هر ردیف یک مسیر منطقی ایران به خارج است. انتخاب مسیر داخلی، Failover و بازیابی به‌صورت خودکار انجام می‌شود.",
                "Each row is one logical Iran-to-Exit route. Internal path selection, failover and recovery are automatic.",
              )}
            </small>
          </div>

          <div className="action-row">
            <button
              type="button"
              className="ghost"
              disabled={loading}
              onClick={() => void load()}
            >
              {loading ? "…" : pick("بروزرسانی", "Refresh")}
            </button>

            <button
              type="button"
              className="primary"
              onClick={openCreate}
            >
              ＋ {pick("تانل جدید", "New tunnel")}
            </button>
          </div>
        </div>

        {error && <div className="runtime-error">{error}</div>}
        {success && <div className="runtime-success">{success}</div>}

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
                        {tunnel.latency_ms == null
                          ? "—"
                          : `${tunnel.latency_ms} ms`}
                      </td>

                      <td>
                        {Number(tunnel.priority || 0).toLocaleString("fa-IR")}
                      </td>

                      <td>
                        <Badge tone={tone(tunnel.status)}>
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
                            onClick={() => {
                              setSelected(tunnel);
                              setManageOpen(true);
                            }}
                          >
                            {pick("مدیریت", "Manage")}
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

                          <button
                            type="button"
                            disabled={Boolean(busy)}
                            onClick={() => void toggle(tunnel)}
                          >
                            {tunnel.is_active
                              ? pick("غیرفعال", "Disable")
                              : pick("فعال", "Enable")}
                          </button>

                          <button
                            type="button"
                            className="danger"
                            disabled={Boolean(busy)}
                            onClick={() => void remove(tunnel)}
                          >
                            {pick("حذف", "Delete")}
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
              "فقط نود ایران و نود خارج را انتخاب کنید؛ مسیر مناسب به‌صورت خودکار انتخاب می‌شود.",
              "Select Iran and Exit nodes only; the best route is selected automatically.",
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
                  "مسیرهای داخلی، سوییچ خودکار و Failover توسط سیستم مدیریت می‌شوند.",
                  "Internal routes, automatic switching and failover are managed by the system.",
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
            title={pick("مدیریت تانل", "Tunnel management")}
            sub={`#${selected.id}`}
            onClose={() => {
              if (!busy) {
                setManageOpen(false);
              }
            }}
          >
            <div className="runtime-info-list">
              <div>
                <span>{pick("مسیر", "Route")}</span>
                <b>
                  {nodeMap.get(selected.iran_node_id)?.name
                    || `#${selected.iran_node_id}`}
                  {" → "}
                  {nodeMap.get(selected.exit_node_id)?.name
                    || `#${selected.exit_node_id}`}
                </b>
              </div>

              <div>
                <span>{pick("وضعیت", "Status")}</span>
                <Badge tone={tone(selected.status)}>
                  {String(selected.status || "—")}
                </Badge>
              </div>

              <div>
                <span>Ping</span>
                <b dir="ltr">
                  {selected.latency_ms == null
                    ? "—"
                    : `${selected.latency_ms} ms`}
                </b>
              </div>

              <div>
                <span>{pick("مدیریت مسیر", "Route management")}</span>
                <b>{pick("خودکار", "Automatic")}</b>
              </div>
            </div>

            <div className="runtime-warning">
              {pick(
                "جزئیات مسیرهای داخلی عمداً مخفی شده‌اند. سیستم سلامت مسیرها را بررسی می‌کند و در صورت نیاز مسیر را تغییر می‌دهد.",
                "Internal path details are intentionally hidden. The system monitors path health and switches routes when needed.",
              )}
            </div>

            <div className="modalActions">
              <button
                type="button"
                className="primary-soft"
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
