"use client";

import {useEffect, useMemo, useState} from "react";

import {API_BASE} from "../lib/api";
import {getCustomerToken} from "../lib/customer-api";
import {useI18n} from "../lib/i18n";
import {Badge, Card, PageHead, Shell} from "./ui";


type ProtocolRow = {
  protocol: string;
  name: string;
  core: string;
  port: number;
  transport: string;
  service: string;
  status: string;
  last_error?: string | null;
  checked_at?: string | null;
};

type NodeRow = {
  id: number;
  name: string;
  public_ip: string;
  public_domain?: string | null;
  status: string;
  protocols: ProtocolRow[];
};

type Inventory = {
  ok: boolean;
  core: string;
  nodes: NodeRow[];
};


async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getCustomerToken();
  if (!token) {
    throw new Error("AUTH_REQUIRED");
  }

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    }
    catch {
      payload = text;
    }
  }

  if (!response.ok) {
    if (payload && typeof payload === "object" && "detail" in payload) {
      const detail = (payload as {detail?: unknown}).detail;
      if (typeof detail === "string") {
        throw new Error(detail);
      }
      if (detail && typeof detail === "object" && "message" in detail) {
        throw new Error(String((detail as {message?: unknown}).message || `API error ${response.status}`));
      }
    }
    throw new Error(`API error ${response.status}`);
  }

  return payload as T;
}


function statusTone(value: string): "ok" | "warn" | "bad" | "violet" {
  const status = String(value || "").toLowerCase();
  if (status === "online") return "ok";
  if (status === "error" || status === "failed") return "bad";
  if (status === "disabled" || status === "not_installed") return "warn";
  return "violet";
}


export function ModernProtocolsAdminPage() {
  const {pick} = useI18n();
  const [nodes, setNodes] = useState<NodeRow[]>([]);
  const [ports, setPorts] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = async () => {
    setError("");
    try {
      const payload = await request<Inventory>("/v1/settings/vpn/modern-protocols");
      setNodes(payload.nodes || []);
      setPorts(current => {
        const next = {...current};
        for (const node of payload.nodes || []) {
          for (const protocol of node.protocols || []) {
            const key = `${node.id}:${protocol.protocol}`;
            if (!(key in next)) next[key] = protocol.port;
          }
        }
        return next;
      });
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const installedCount = useMemo(
    () => nodes.reduce(
      (total, node) => total + node.protocols.filter(row => row.status === "online").length,
      0,
    ),
    [nodes],
  );

  const install = async (node: NodeRow, protocol: ProtocolRow) => {
    if (busy) return;
    const key = `${node.id}:${protocol.protocol}`;
    const port = Number(ports[key] || protocol.port);
    setBusy(`install:${key}`);
    setError("");
    setNotice("");
    try {
      await request(`/v1/settings/vpn/modern-protocols/${node.id}/install`, {
        method: "POST",
        body: JSON.stringify({
          protocols: [protocol.protocol],
          ports: {[protocol.protocol]: port},
        }),
      });
      setNotice(pick(`${protocol.name} روی ${node.name} آماده شد.`, `${protocol.name} is ready on ${node.name}.`));
      await load();
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };

  const health = async (node: NodeRow) => {
    if (busy) return;
    setBusy(`health:${node.id}`);
    setError("");
    setNotice("");
    try {
      await request(`/v1/settings/vpn/modern-protocols/${node.id}/health`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setNotice(pick(`Health Check نود ${node.name} انجام شد.`, `Health check completed for ${node.name}.`));
      await load();
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };

  const remove = async (node: NodeRow, protocol: ProtocolRow) => {
    if (busy) return;
    if (!window.confirm(pick(`${protocol.name} از ${node.name} حذف شود؟`, `Remove ${protocol.name} from ${node.name}?`))) {
      return;
    }
    const key = `${node.id}:${protocol.protocol}`;
    setBusy(`remove:${key}`);
    setError("");
    setNotice("");
    try {
      await request(`/v1/settings/vpn/modern-protocols/${node.id}/${protocol.protocol}`, {
        method: "DELETE",
      });
      setNotice(pick(`${protocol.name} حذف شد.`, `${protocol.name} was removed.`));
      await load();
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };

  return (
    <Shell active="/admin/modern-protocols">
      <div className="page legacy-control-page">
        <PageHead
          title={pick("پروتکل‌های جدید", "Modern protocols")}
          sub={pick(
            "مدیریت Hysteria2، TUIC v5 و AnyTLS روی Core مستقل sing-box",
            "Manage Hysteria2, TUIC v5 and AnyTLS on an isolated sing-box core",
          )}
        />

        {error && <div className="runtime-error">{error}</div>}
        {notice && <div className="runtime-success">{notice}</div>}

        <div className="stat-grid">
          <Card>
            <small>{pick("Core", "Core")}</small>
            <b>sing-box</b>
          </Card>
          <Card>
            <small>{pick("نودهای خروجی", "Exit nodes")}</small>
            <b>{nodes.length.toLocaleString("fa-IR")}</b>
          </Card>
          <Card>
            <small>{pick("Listener سالم", "Healthy listeners")}</small>
            <b>{installedCount.toLocaleString("fa-IR")}</b>
          </Card>
        </div>

        {nodes.length === 0 && (
          <Card>
            <p>{pick("هیچ نود خروجی فعالی وجود ندارد.", "No active Exit node is available.")}</p>
          </Card>
        )}

        {nodes.map(node => (
          <Card key={node.id}>
            <div className="card-head">
              <div>
                <b>{node.name}</b>
                <small>{node.public_domain || node.public_ip}</small>
              </div>
              <div className="row-actions">
                <Badge tone={statusTone(node.status)}>{node.status}</Badge>
                <button
                  className="ghost"
                  disabled={!!busy}
                  onClick={() => void health(node)}
                >
                  {busy === `health:${node.id}` ? "…" : pick("بررسی سلامت", "Health check")}
                </button>
              </div>
            </div>

            <div className="table">
              <table>
                <thead>
                  <tr>
                    <th>{pick("پروتکل", "Protocol")}</th>
                    <th>{pick("انتقال", "Transport")}</th>
                    <th>{pick("پورت", "Port")}</th>
                    <th>{pick("وضعیت", "Status")}</th>
                    <th>{pick("عملیات", "Actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {node.protocols.map(protocol => {
                    const rowKey = `${node.id}:${protocol.protocol}`;
                    const isInstalled = protocol.status === "online" || protocol.status === "error";
                    return (
                      <tr key={protocol.protocol}>
                        <td>
                          <b>{protocol.name}</b>
                          <small>{protocol.core}</small>
                        </td>
                        <td>{protocol.transport.toUpperCase()}</td>
                        <td>
                          <input
                            type="number"
                            min={1}
                            max={65535}
                            value={ports[rowKey] ?? protocol.port}
                            onChange={event => setPorts(current => ({
                              ...current,
                              [rowKey]: Number(event.target.value),
                            }))}
                            style={{width: 110}}
                          />
                        </td>
                        <td>
                          <Badge tone={statusTone(protocol.status)}>{protocol.status}</Badge>
                          {protocol.last_error && <small>{protocol.last_error}</small>}
                        </td>
                        <td>
                          <div className="row-actions">
                            <button
                              className="primary"
                              disabled={!!busy}
                              onClick={() => void install(node, protocol)}
                            >
                              {busy === `install:${rowKey}`
                                ? "…"
                                : isInstalled
                                  ? pick("تعمیر / بروزرسانی", "Repair / update")
                                  : pick("نصب", "Install")}
                            </button>
                            {isInstalled && (
                              <button
                                className="danger"
                                disabled={!!busy}
                                onClick={() => void remove(node, protocol)}
                              >
                                {busy === `remove:${rowKey}` ? "…" : pick("حذف", "Remove")}
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        ))}
      </div>
    </Shell>
  );
}
