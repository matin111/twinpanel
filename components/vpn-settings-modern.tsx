"use client";

import {
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  Badge,
  Card,
  PageHead,
  Shell,
} from "./ui";
import {
  API_BASE,
} from "../lib/api";
import {
  getCustomerToken,
} from "../lib/customer-api";
import {
  useI18n,
} from "../lib/i18n";


type ProfileRow = {
  id: string;
  title: string;
  security: string;
  transport: string;
  recommended: boolean;
  requires_tls_domain: boolean;
  target_port: number;
  tunnel_public_port: number;
};


type NodeRow = {
  id: number;
  name: string;
  public_ip: string;
  public_domain?: string | null;
  enabled: boolean;
  status: string;
  base_port: number;
  profiles: ProfileRow[];
};


type RuntimeState = {
  service_active?: boolean;
  tls_enabled?: boolean;
  tls_domain?: string | null;
  profiles?: Record<string, boolean>;
};


type NodeStatusResponse = {
  ok: boolean;
  node: NodeRow;
  runtime: RuntimeState;
};


type NodesResponse = {
  ok: boolean;
  nodes: NodeRow[];
};


type PrepareResponse = {
  ok: boolean;
  node: NodeRow;
  runtime: RuntimeState;
  available_profiles?: string[];
  message?: string;
};


function errorText(
  payload: unknown,
  status: number,
) {
  if (
    payload
    && typeof payload === "object"
  ) {
    const row = payload as {
      detail?: unknown;
      message?: unknown;
    };

    if (typeof row.detail === "string") {
      return row.detail;
    }

    if (typeof row.message === "string") {
      return row.message;
    }

    if (
      row.detail
      && typeof row.detail === "object"
    ) {
      const detail = row.detail as {
        message?: unknown;
        expected_ip?: unknown;
        resolved_ips?: unknown;
        listener?: unknown;
      };

      const pieces = [
        typeof detail.message === "string"
          ? detail.message
          : "",

        detail.expected_ip
          ? `IP: ${String(detail.expected_ip)}`
          : "",

        Array.isArray(detail.resolved_ips)
          ? `DNS: ${detail.resolved_ips.join(", ")}`
          : "",

        detail.listener
          ? `Listener: ${String(detail.listener)}`
          : "",
      ].filter(Boolean);

      if (pieces.length) {
        return pieces.join(" — ");
      }
    }
  }

  return `API error ${status}`;
}


async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = getCustomerToken();

  if (!token) {
    throw new Error("AUTH_REQUIRED");
  }

  const headers = new Headers(
    init.headers,
  );

  headers.set(
    "Authorization",
    `Bearer ${token}`,
  );

  if (
    init.body
    && !headers.has("Content-Type")
  ) {
    headers.set(
      "Content-Type",
      "application/json",
    );
  }

  const response = await fetch(
    `${API_BASE}${path}`,
    {
      ...init,
      headers,
      cache: "no-store",
    },
  );

  const raw = await response.text();
  let payload: unknown = null;

  if (raw) {
    try {
      payload = JSON.parse(raw);
    }
    catch {
      payload = raw;
    }
  }

  if (!response.ok) {
    throw new Error(
      errorText(
        payload,
        response.status,
      ),
    );
  }

  return payload as T;
}


function profileTitle(
  id: string,
  pick: (fa: string, en: string) => string,
) {
  switch (id) {
    case "websocket_tls":
      return pick(
        "WebSocket + TLS",
        "WebSocket + TLS",
      );

    case "xhttp_reality":
      return pick(
        "XHTTP + REALITY",
        "XHTTP + REALITY",
      );

    case "httpupgrade_tls":
      return pick(
        "HTTP Upgrade + TLS",
        "HTTP Upgrade + TLS",
      );

    case "grpc_reality":
      return pick(
        "gRPC + REALITY",
        "gRPC + REALITY",
      );

    default:
      return id;
  }
}


function profileDescription(
  id: string,
  pick: (fa: string, en: string) => string,
) {
  switch (id) {
    case "websocket_tls":
      return pick(
        "مسیر سازگار HTTP/1.1 برای شبکه‌هایی که WebSocket بهتر عبور می‌کند.",
        "HTTP/1.1-compatible path for networks where WebSocket passes more reliably.",
      );

    case "xhttp_reality":
      return pick(
        "مسیر مدرن اصلی بدون نیاز به دامنه؛ با REALITY.",
        "Primary modern no-domain profile protected by REALITY.",
      );

    case "httpupgrade_tls":
      return pick(
        "جایگزین سبک HTTP Upgrade با TLS برای کلاینت‌های سازگار.",
        "Lightweight HTTP Upgrade over TLS for compatible clients.",
      );

    case "grpc_reality":
      return pick(
        "فقط مسیر پشتیبان برای سازگاری؛ XHTTP در اولویت بالاتر است.",
        "Compatibility fallback only; XHTTP has higher priority.",
      );

    default:
      return "";
  }
}


export function VpnSettingsModernPage() {
  const {pick} = useI18n();

  const [rows, setRows] = useState<NodeRow[]>([]);
  const [domains, setDomains] = useState<Record<number, string>>({});
  const [runtime, setRuntime] = useState<Record<number, RuntimeState>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");


  const load = async () => {
    setLoading(true);
    setError("");

    try {
      const payload = await request<NodesResponse>(
        "/v1/xray-modern-admin/nodes",
      );

      setRows(payload.nodes || []);

      setDomains(
        Object.fromEntries(
          (payload.nodes || []).map(
            row => [
              row.id,
              row.public_domain || "",
            ],
          ),
        ),
      );
    }
    catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : String(reason),
      );
    }
    finally {
      setLoading(false);
    }
  };


  useEffect(() => {
    void load();
  }, []);


  const enabledCount = useMemo(
    () => rows.filter(row => row.enabled).length,
    [rows],
  );


  const tlsCount = useMemo(
    () => Object.values(runtime).filter(
      value => value.tls_enabled,
    ).length,
    [runtime],
  );


  const saveDomain = async (
    node: NodeRow,
  ) => {
    const key = `domain-${node.id}`;

    if (busy) {
      return;
    }

    setBusy(key);
    setError("");
    setNotice("");

    try {
      const payload = await request<{
        ok: boolean;
        node: NodeRow;
      }>(
        `/v1/xray-modern-admin/nodes/${node.id}/domain`,
        {
          method: "PUT",
          body: JSON.stringify({
            domain: domains[node.id] || null,
          }),
        },
      );

      setRows(current => current.map(
        row => row.id === node.id
          ? payload.node
          : row,
      ));

      setNotice(
        pick(
          "دامنه نود ذخیره شد.",
          "Node domain was saved.",
        ),
      );
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


  const refreshStatus = async (
    node: NodeRow,
  ) => {
    const key = `status-${node.id}`;

    if (busy) {
      return;
    }

    setBusy(key);
    setError("");

    try {
      const payload = await request<NodeStatusResponse>(
        `/v1/xray-modern-admin/nodes/${node.id}/status`,
      );

      setRows(current => current.map(
        row => row.id === node.id
          ? payload.node
          : row,
      ));

      setRuntime(current => ({
        ...current,
        [node.id]: payload.runtime,
      }));
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


  const prepare = async (
    node: NodeRow,
  ) => {
    const key = `prepare-${node.id}`;

    if (busy) {
      return;
    }

    const domain = (
      domains[node.id]
      || ""
    ).trim();

    const confirmed = window.confirm(
      domain
        ? pick(
            `اتصال‌های امن Xray روی ${node.name} آماده شوند و برای ${domain} در صورت نیاز SSL صادر شود؟`,
            `Prepare secure Xray profiles on ${node.name} and issue SSL for ${domain} if needed?`,
          )
        : pick(
            `اتصال‌های REALITY روی ${node.name} آماده شوند؟ WebSocket تا زمان تنظیم دامنه فعال نمی‌شود.`,
            `Prepare REALITY profiles on ${node.name}? WebSocket stays unavailable until a domain is configured.`,
          ),
    );

    if (!confirmed) {
      return;
    }

    setBusy(key);
    setError("");
    setNotice("");

    try {
      const payload = await request<PrepareResponse>(
        `/v1/xray-modern-admin/nodes/${node.id}/prepare`,
        {
          method: "POST",
          body: JSON.stringify({
            domain: domain || null,
            issue_certificate: Boolean(domain),
          }),
        },
      );

      setRows(current => current.map(
        row => row.id === node.id
          ? payload.node
          : row,
      ));

      setRuntime(current => ({
        ...current,
        [node.id]: payload.runtime,
      }));

      setDomains(current => ({
        ...current,
        [node.id]: payload.node.public_domain || "",
      }));

      setNotice(
        payload.message
        || pick(
          "اتصال‌های امن آماده شدند.",
          "Secure connections are ready.",
        ),
      );
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


  return (
    <Shell active="/admin/vpn-settings">
      <div className="page legacy-control-page">
        <PageHead
          title={pick(
            "تنظیمات VPN",
            "VPN Settings",
          )}
          sub={pick(
            "مدیریت ساده اتصال‌های کاربر؛ جزئیات Transport داخلی تانل‌ها مخفی و خودکار هستند.",
            "Simple customer connection management; internal tunnel transports stay hidden and automatic.",
          )}
        />


        {error && (
          <div className="runtime-error">
            {error}
          </div>
        )}


        {notice && (
          <div className="runtime-success">
            {notice}
          </div>
        )}


        <div className="stats dashboard-stats">
          <Card className="stat">
            <span className="stat-icon">◈</span>
            <div>
              <small>{pick("نود Xray", "Xray nodes")}</small>
              <b>{enabledCount.toLocaleString("fa-IR")}</b>
            </div>
          </Card>

          <Card className="stat">
            <span className="stat-icon">⌁</span>
            <div>
              <small>{pick("TLS تأییدشده", "TLS ready")}</small>
              <b>{tlsCount.toLocaleString("fa-IR")}</b>
            </div>
          </Card>

          <Card className="stat">
            <span className="stat-icon">◎</span>
            <div>
              <small>{pick("اتصال مدرن", "Modern profiles")}</small>
              <b>4</b>
            </div>
          </Card>
        </div>


        <Card>
          <div className="card-head">
            <div>
              <b>{pick("سیاست Xray جدید", "Modern Xray policy")}</b>
              <small>
                {pick(
                  "Plain VLESS فقط برای سازگاری لینک‌های قدیمی می‌ماند؛ اکانت جدید از اتصال‌های امن استفاده می‌کند.",
                  "Plain VLESS remains only for old-link compatibility; new credentials use secure profiles.",
                )}
              </small>
            </div>
          </div>

          <div className="runtime-info-list">
            <div>
              <span>{pick("اولویت ۱", "Priority 1")}</span>
              <b>WebSocket + TLS</b>
            </div>

            <div>
              <span>{pick("اولویت ۲", "Priority 2")}</span>
              <b>XHTTP + REALITY</b>
            </div>

            <div>
              <span>{pick("جایگزین TLS", "TLS fallback")}</span>
              <b>HTTP Upgrade + TLS</b>
            </div>

            <div>
              <span>{pick("سازگاری", "Compatibility")}</span>
              <b>gRPC + REALITY</b>
            </div>
          </div>
        </Card>


        {loading && (
          <div className="runtime-empty">
            {pick(
              "در حال دریافت نودها...",
              "Loading nodes...",
            )}
          </div>
        )}


        {!loading && !rows.length && (
          <Card>
            <div className="runtime-empty">
              {pick(
                "هنوز Xray روی هیچ نود خروجی فعال نشده است.",
                "Xray is not enabled on any Exit node yet.",
              )}
            </div>
          </Card>
        )}


        {!loading && rows.map(node => {
          const live = runtime[node.id];
          const domain = domains[node.id] || "";

          return (
            <Card key={node.id}>
              <div className="card-head">
                <div>
                  <b>{node.name}</b>
                  <small dir="ltr">
                    {node.public_ip}
                    {" · Xray :"}
                    {node.base_port}
                  </small>
                </div>

                <Badge
                  tone={
                    node.status === "online"
                      ? "ok"
                      : "warn"
                  }
                >
                  {node.status || "—"}
                </Badge>
              </div>


              <div className="setting-grid">
                <label className="field">
                  <span>
                    {pick(
                      "دامنه اختصاصی Xray",
                      "Xray domain",
                    )}
                  </span>

                  <input
                    dir="ltr"
                    value={domain}
                    placeholder="xray.example.com"
                    onChange={event => setDomains(current => ({
                      ...current,
                      [node.id]: event.target.value,
                    }))}
                  />

                  <small>
                    {pick(
                      "برای WebSocket + TLS باید A Record همین دامنه به IP نود خارج اشاره کند.",
                      "For WebSocket + TLS, this domain's A record must point to the Exit IP.",
                    )}
                  </small>
                </label>
              </div>


              <div className="action-row">
                <button
                  type="button"
                  className="ghost"
                  disabled={Boolean(busy)}
                  onClick={() => void saveDomain(node)}
                >
                  {busy === `domain-${node.id}`
                    ? "…"
                    : pick("ذخیره دامنه", "Save domain")}
                </button>

                <button
                  type="button"
                  className="ghost"
                  disabled={Boolean(busy)}
                  onClick={() => void refreshStatus(node)}
                >
                  {busy === `status-${node.id}`
                    ? "…"
                    : pick("بررسی وضعیت", "Check status")}
                </button>

                <button
                  type="button"
                  className="primary"
                  disabled={Boolean(busy) || node.status !== "online"}
                  onClick={() => void prepare(node)}
                >
                  {busy === `prepare-${node.id}`
                    ? pick("در حال آماده‌سازی...", "Preparing...")
                    : pick("آماده‌سازی Xray امن", "Prepare secure Xray")}
                </button>
              </div>


              {live && (
                <div className="runtime-info-list">
                  <div>
                    <span>Xray</span>
                    <Badge tone={live.service_active ? "ok" : "bad"}>
                      {live.service_active
                        ? pick("فعال", "Active")
                        : pick("آفلاین", "Offline")}
                    </Badge>
                  </div>

                  <div>
                    <span>TLS</span>
                    <Badge tone={live.tls_enabled ? "ok" : "warn"}>
                      {live.tls_enabled
                        ? pick("آماده", "Ready")
                        : pick("نیاز به دامنه", "Domain required")}
                    </Badge>
                  </div>

                  <div>
                    <span>{pick("دامنه TLS", "TLS domain")}</span>
                    <b dir="ltr">{live.tls_domain || "—"}</b>
                  </div>
                </div>
              )}


              <div className="module-grid two">
                {node.profiles.map(profile => {
                  const active = Boolean(
                    live?.profiles?.[profile.id],
                  );

                  return (
                    <div
                      key={profile.id}
                      className="module-row"
                    >
                      <span className="module-icon">⌁</span>

                      <div className="grow">
                        <b>
                          {profileTitle(profile.id, pick)}
                        </b>

                        <small>
                          {profileDescription(profile.id, pick)}
                        </small>

                        <small dir="ltr">
                          Exit:{profile.target_port}
                          {" · Iran:"}
                          {profile.tunnel_public_port}
                        </small>
                      </div>

                      {live
                        ? (
                            <Badge tone={active ? "ok" : "warn"}>
                              {active
                                ? pick("آماده", "Ready")
                                : profile.requires_tls_domain
                                  ? pick("نیاز به TLS", "Needs TLS")
                                  : pick("غیرفعال", "Inactive")}
                            </Badge>
                          )
                        : (
                            <Badge tone={profile.requires_tls_domain ? "warn" : "violet"}>
                              {profile.requires_tls_domain
                                ? pick("دامنه + SSL", "Domain + SSL")
                                : pick("REALITY", "REALITY")}
                            </Badge>
                          )}
                    </div>
                  );
                })}
              </div>
            </Card>
          );
        })}
      </div>
    </Shell>
  );
}
