"use client";

import {useMemo, useState} from "react";

import {adminApi, type AdminNode, type XrayDomainState} from "../lib/admin-api";
import {legacyAdminApi} from "../lib/legacy-admin-api";
import {useI18n} from "../lib/i18n";
import {Badge} from "./ui";
import styles from "./modern-protocols-admin-v2.module.css";


type LegacyProtocolKey = "cisco" | "openvpn" | "wireguard" | "l2tp" | "v2ray";

type LegacyRuntime = {
  protocol?: string;
  name?: string;
  installed?: boolean;
  ok?: boolean;
  service?: string;
  listeners?: Record<string, boolean>;
  port?: number | null;
  port_text?: string;
  transport?: string;
  error?: string | null;
  modern_ready?: boolean;
  modern_health?: {
    ok?: boolean;
    tls_enabled?: boolean;
    tls_domain_configured?: boolean;
    error?: string | null;
  };
};

type NodeRuntime = Record<string, LegacyRuntime>;

type ProtocolDefinition = {
  key: LegacyProtocolKey;
  label: string;
  core: string;
  transport: string;
  enabled: (node: AdminNode) => boolean;
};

const LEGACY_PROTOCOLS: ProtocolDefinition[] = [
  {
    key: "cisco",
    label: "Cisco / OpenConnect",
    core: "ocserv",
    transport: "TCP + DTLS",
    enabled: node => Boolean(node.enable_cisco),
  },
  {
    key: "openvpn",
    label: "OpenVPN",
    core: "OpenVPN",
    transport: "TCP / UDP",
    enabled: node => Boolean(node.enable_openvpn),
  },
  {
    key: "wireguard",
    label: "WireGuard",
    core: "Kernel WG",
    transport: "UDP",
    enabled: node => Boolean(node.enable_wireguard),
  },
  {
    key: "l2tp",
    label: "L2TP / IPsec",
    core: "strongSwan + xl2tpd",
    transport: "UDP / IPsec",
    enabled: node => Boolean(node.enable_l2tp),
  },
  {
    key: "v2ray",
    label: "V2Ray / Xray",
    core: "Xray",
    transport: "TCP / TLS / REALITY",
    enabled: node => Boolean(node.enable_v2ray),
  },
];

function statusTone(value: unknown): "ok" | "warn" | "bad" | "violet" {
  const status = String(value || "").toLowerCase();
  if (["online", "active", "ok", "healthy"].includes(status)) return "ok";
  if (["offline", "failed", "error"].includes(status)) return "bad";
  return "violet";
}

function runtimeBadge(row: LegacyRuntime | undefined, checked: boolean, pick: (fa: string, en: string) => string) {
  if (!checked) return <Badge tone="violet">{pick("فعال", "Enabled")}</Badge>;
  if (row?.ok) return <Badge tone="ok">ONLINE</Badge>;
  return <Badge tone="warn">CHECK</Badge>;
}

export function LegacyProtocolsStudio() {
  const {pick} = useI18n();
  const [nodes, setNodes] = useState<AdminNode[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [runtime, setRuntime] = useState<Record<number, NodeRuntime>>({});
  const [checkedNodes, setCheckedNodes] = useState<Record<number, boolean>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [domainNodeId, setDomainNodeId] = useState(0);
  const [domainDraft, setDomainDraft] = useState("");
  const [domainMeta, setDomainMeta] = useState<XrayDomainState | null>(null);

  const load = async () => {
    setError("");
    const rows = await adminApi.nodes();
    setNodes(rows.filter(node => String(node.node_type || "").toLowerCase() === "exit"));
    setLoaded(true);
  };

  useState(() => {
    void load().catch(reason => setError(reason instanceof Error ? reason.message : String(reason)));
  });

  const enabledCount = useMemo(
    () => nodes.reduce((total, node) => total + LEGACY_PROTOCOLS.filter(protocol => protocol.enabled(node)).length, 0),
    [nodes],
  );

  const healthyCount = useMemo(
    () => Object.values(runtime).reduce(
      (total, rows) => total + Object.values(rows).filter(row => row?.ok).length,
      0,
    ),
    [runtime],
  );

  const health = async (node: AdminNode) => {
    if (busy) return;
    setBusy(`health:${node.id}`);
    setError("");
    setNotice("");
    try {
      const result = await legacyAdminApi.protocolHealth(node.id);
      const rows = result && typeof result.protocols === "object" && result.protocols
        ? result.protocols as NodeRuntime
        : {};
      setRuntime(current => ({...current, [node.id]: rows}));
      setCheckedNodes(current => ({...current, [node.id]: true}));
      setNotice(Boolean(result.ok)
        ? pick(`سلامت پروتکل‌های ${node.name} تأیید شد.`, `${node.name} protocol health verified.`)
        : pick(`برخی پروتکل‌های ${node.name} نیاز به بررسی دارند.`, `Some ${node.name} protocols need attention.`));
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };

  const repair = async (node: AdminNode) => {
    if (busy) return;
    if (!window.confirm(pick(
      `فقط پروتکل‌های ذخیره‌شده و فعال روی ${node.name} Repair شوند؟`,
      `Repair only saved and enabled protocols on ${node.name}?`,
    ))) return;
    setBusy(`repair:${node.id}`);
    setError("");
    setNotice("");
    try {
      await legacyAdminApi.repairProtocolsSaved(node.id);
      const result = await legacyAdminApi.protocolHealth(node.id);
      const rows = result && typeof result.protocols === "object" && result.protocols
        ? result.protocols as NodeRuntime
        : {};
      setRuntime(current => ({...current, [node.id]: rows}));
      setCheckedNodes(current => ({...current, [node.id]: true}));
      setNotice(pick(
        `پروتکل‌های فعال ${node.name} Repair و دوباره Health Check شدند.`,
        `${node.name} enabled protocols were repaired and health-checked again.`,
      ));
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };

  const restart = async (node: AdminNode, protocol: LegacyProtocolKey) => {
    if (busy) return;
    setBusy(`restart:${node.id}:${protocol}`);
    setError("");
    setNotice("");
    try {
      const result = await legacyAdminApi.restartProtocol(node.id, protocol);
      const row = result && typeof result.protocol === "object" && result.protocol
        ? result.protocol as LegacyRuntime
        : {};
      setRuntime(current => ({
        ...current,
        [node.id]: {
          ...(current[node.id] || {}),
          [protocol]: row,
        },
      }));
      setCheckedNodes(current => ({...current, [node.id]: true}));
      setNotice(pick("سرویس ریستارت شد.", "Service restarted."));
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };

  const openXrayDomain = async (node: AdminNode) => {
    if (busy) return;
    setBusy(`domain-load:${node.id}`);
    setError("");
    try {
      const result = await adminApi.xrayDomain(node.id);
      setDomainNodeId(node.id);
      setDomainMeta(result);
      setDomainDraft(String(result.xray_domain || ""));
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };

  const saveXrayDomain = async (prepare: boolean) => {
    if (!domainNodeId || busy) return;
    const node = nodes.find(row => row.id === domainNodeId);
    setBusy(prepare ? `domain-prepare:${domainNodeId}` : `domain-save:${domainNodeId}`);
    setError("");
    setNotice("");
    try {
      const saved = await adminApi.saveXrayDomain(domainNodeId, domainDraft.trim());
      setDomainMeta(saved);
      if (prepare && domainDraft.trim()) {
        const prepared = await adminApi.prepareXrayDomain(domainNodeId, true);
        setDomainMeta(current => ({...current, ...prepared}));
        setNotice(pick(
          `دامنه Xray ${node?.name || ""} ذخیره شد و TLS آماده‌سازی شد.`,
          `${node?.name || "Xray"} domain saved and TLS prepared.`,
        ));
      }
      else {
        setNotice(pick("دامنه Xray ذخیره شد.", "Xray domain saved."));
      }
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };

  if (!loaded && !error) {
    return <div className={styles.warningBox}>{pick("در حال دریافت پروتکل‌های کلاسیک…", "Loading classic protocols…")}</div>;
  }

  return (
    <>
      {error && <div className={styles.errorBox}>{error}</div>}
      {notice && <div className={styles.successBox}>{notice}</div>}

      <div className={styles.categoryHead}>
        <h3>{pick("VPN و پروتکل‌های کلاسیک", "Classic VPN protocols")}</h3>
        <span>{pick("Runtime واقعی نودها؛ بدون داده نمایشی", "Real node runtimes; no demo data")}</span>
      </div>

      <div className={styles.summaryGrid}>
        <div className={styles.summaryCard}><small>{pick("نود خروجی", "Exit nodes")}</small><strong>{nodes.length.toLocaleString("fa-IR")}</strong></div>
        <div className={styles.summaryCard}><small>{pick("پروتکل فعال", "Enabled protocols")}</small><strong>{enabledCount.toLocaleString("fa-IR")}</strong></div>
        <div className={styles.summaryCard}><small>{pick("سالم پس از Health", "Healthy after check")}</small><strong>{healthyCount.toLocaleString("fa-IR")}</strong></div>
        <div className={styles.summaryCard}><small>{pick("مدیریت", "Management")}</small><strong>{pick("یکپارچه", "Unified")}</strong></div>
      </div>

      {nodes.map(node => {
        const enabled = LEGACY_PROTOCOLS.filter(protocol => protocol.enabled(node));
        const nodeRuntime = runtime[node.id] || {};
        const checked = Boolean(checkedNodes[node.id]);
        return (
          <section className={styles.nodeCard} key={`legacy:${node.id}`}>
            <div className={styles.nodeHead}>
              <div className={styles.nodeTitle}>
                <strong>{node.name}</strong>
                <span>{node.public_ip || "—"}</span>
              </div>
              <div className={styles.nodeActions}>
                <Badge tone={statusTone(node.status)}>{node.status || "—"}</Badge>
                <button className={styles.secondary} disabled={!!busy} onClick={() => void health(node)}>
                  {busy === `health:${node.id}` ? "…" : pick("Health کلاسیک", "Classic health")}
                </button>
                <button className={styles.primary} disabled={!!busy || !enabled.length} onClick={() => void repair(node)}>
                  {busy === `repair:${node.id}` ? "…" : pick("Repair فعال‌ها", "Repair enabled")}
                </button>
              </div>
            </div>

            <div className={styles.category}>
              <div className={styles.categoryHead}>
                <h3>{pick("پروتکل‌های فعال این نود", "Enabled on this node")}</h3>
                <span>{enabled.length.toLocaleString("fa-IR")} {pick("پروتکل", "protocols")}</span>
              </div>

              {enabled.length ? (
                <div className={styles.protocolGrid}>
                  {enabled.map(protocol => {
                    const row = nodeRuntime[protocol.key];
                    const listener = row?.port_text || (row?.port ? String(row.port) : "—");
                    return (
                      <article className={styles.protocolCard} key={`${node.id}:${protocol.key}`}>
                        <div className={styles.protocolTop}>
                          <div className={styles.protocolName}>
                            <strong>{protocol.label}</strong>
                            <small>{protocol.core} · {row?.transport || protocol.transport}</small>
                          </div>
                          {runtimeBadge(row, checked, pick)}
                        </div>

                        <div className={styles.chips}>
                          <span className={`${styles.chip} ${styles.chipReady}`}>{pick("Production", "Production")}</span>
                          {row?.service && <span className={styles.chip}>{row.service}</span>}
                          <span className={styles.chip}>{pick("پورت", "Port")} {listener}</span>
                          {protocol.key === "v2ray" && row?.modern_health?.tls_enabled && <span className={styles.chip}>TLS</span>}
                        </div>

                        {row?.error && <div className={styles.errorBox}>{row.error}</div>}

                        <div className={styles.cardActions}>
                          {protocol.key === "v2ray" && (
                            <button className={styles.secondary} disabled={!!busy} onClick={() => void openXrayDomain(node)}>
                              {busy === `domain-load:${node.id}` ? "…" : pick("دامنه و TLS", "Domain & TLS")}
                            </button>
                          )}
                          {checked && !row?.ok && (
                            <button className={styles.primary} disabled={!!busy} onClick={() => void restart(node, protocol.key)}>
                              {busy === `restart:${node.id}:${protocol.key}` ? "…" : pick("ریستارت سرویس", "Restart service")}
                            </button>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <div className={styles.warningBox}>{pick("برای این نود پروتکل کلاسیک فعالی ثبت نشده است.", "No classic protocol is enabled for this node.")}</div>
              )}
            </div>

            {domainNodeId === node.id && node.enable_v2ray && (
              <div className={styles.category}>
                <div className={styles.categoryHead}>
                  <h3>{pick("دامنه اختصاصی V2Ray / Xray", "Dedicated V2Ray / Xray domain")}</h3>
                  <span>{domainMeta?.tls_enabled ? "TLS READY" : pick("TLS نیازمند بررسی", "TLS needs review")}</span>
                </div>
                <div className={styles.fields}>
                  <div className={`${styles.field} ${styles.fieldWide}`}>
                    <label>{pick("دامنه Xray", "Xray domain")}</label>
                    <input dir="ltr" value={domainDraft} onChange={event => setDomainDraft(event.target.value)} placeholder="xray.example.com"/>
                    <small>{pick("DNS باید مستقیم به IP همین نود خروجی اشاره کند. دامنه عمومی نود تغییر نمی‌کند.", "DNS must resolve directly to this Exit node. The Node public domain is not changed.")}</small>
                  </div>
                </div>
                <div className={styles.chips}>
                  <span className={styles.chip}>{pick("دامنه موثر", "Effective")}: {domainMeta?.effective_xray_domain || "—"}</span>
                  {domainMeta?.legacy_public_domain_fallback && <span className={`${styles.chip} ${styles.chipPending}`}>{pick("Fallback قدیمی", "Legacy fallback")}</span>}
                  {domainMeta?.tls_enabled && <span className={`${styles.chip} ${styles.chipReady}`}>TLS READY</span>}
                </div>
                <div className={styles.cardActions}>
                  <button className={styles.secondary} disabled={!!busy} onClick={() => void saveXrayDomain(false)}>
                    {busy === `domain-save:${node.id}` ? "…" : pick("ذخیره دامنه", "Save domain")}
                  </button>
                  <button className={styles.primary} disabled={!!busy || !domainDraft.trim()} onClick={() => void saveXrayDomain(true)}>
                    {busy === `domain-prepare:${node.id}` ? "…" : pick("ذخیره و آماده‌سازی TLS", "Save & prepare TLS")}
                  </button>
                  <button className={styles.secondary} disabled={!!busy} onClick={() => { setDomainNodeId(0); setDomainMeta(null); setDomainDraft(""); }}>
                    {pick("بستن", "Close")}
                  </button>
                </div>
              </div>
            )}
          </section>
        );
      })}

      {!nodes.length && !error && (
        <div className={styles.warningBox}>{pick("هنوز نود خروجی ثبت نشده است.", "No Exit node is registered yet.")}</div>
      )}
    </>
  );
}
