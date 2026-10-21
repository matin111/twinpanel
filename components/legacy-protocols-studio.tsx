"use client";

import {useEffect, useMemo, useState} from "react";

import {adminApi, type XrayDomainState} from "../lib/admin-api";
import {
  legacyAdminApi,
  type ClassicProtocolInventoryNode,
  type ClassicProtocolInventoryRow,
  type ClassicProtocolKey,
} from "../lib/legacy-admin-api";
import {useI18n} from "../lib/i18n";
import {Badge} from "./ui";
import styles from "./modern-protocols-admin-v2.module.css";


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

type Draft = {
  port: number;
  transport: "udp" | "tcp";
};

type ProtocolDefinition = {
  key: ClassicProtocolKey;
  label: string;
  core: string;
  transport: string;
  defaultPort: number | null;
};

const CLASSIC_PROTOCOLS: ProtocolDefinition[] = [
  {key: "cisco", label: "Cisco / OpenConnect", core: "ocserv", transport: "TCP + DTLS", defaultPort: 443},
  {key: "openvpn", label: "OpenVPN", core: "OpenVPN", transport: "TCP / UDP", defaultPort: 1194},
  {key: "wireguard", label: "WireGuard", core: "Kernel WG", transport: "UDP", defaultPort: 51820},
  {key: "l2tp", label: "L2TP / IPsec", core: "strongSwan + xl2tpd", transport: "UDP / IPsec", defaultPort: null},
  {key: "v2ray", label: "V2Ray / Xray", core: "Xray", transport: "TCP / TLS / REALITY", defaultPort: 8443},
];

const DEF_MAP = new Map(CLASSIC_PROTOCOLS.map(row => [row.key, row]));

function keyOf(nodeId: number, protocol: ClassicProtocolKey) {
  return `${nodeId}:${protocol}`;
}

function statusTone(value: unknown): "ok" | "warn" | "bad" | "violet" {
  const status = String(value || "").toLowerCase();
  if (["online", "active", "ok", "healthy", "enabled"].includes(status)) return "ok";
  if (["offline", "failed", "error"].includes(status)) return "bad";
  if (["not_installed", "disabled"].includes(status)) return "warn";
  return "violet";
}

function protocolBadge(
  row: ClassicProtocolInventoryRow,
  runtime: LegacyRuntime | undefined,
  checked: boolean,
  pick: (fa: string, en: string) => string,
) {
  if (!row.enabled) return <Badge tone="warn">{pick("نصب نشده", "Not installed")}</Badge>;
  if (checked) return runtime?.ok ? <Badge tone="ok">ONLINE</Badge> : <Badge tone="warn">CHECK</Badge>;
  return <Badge tone={statusTone(row.status)}>{row.status === "online" ? "ONLINE" : pick("فعال", "Enabled")}</Badge>;
}

function rowFor(node: ClassicProtocolInventoryNode, protocol: ClassicProtocolKey) {
  return node.protocols.find(row => row.protocol === protocol);
}

export function LegacyProtocolsStudio() {
  const {pick} = useI18n();
  const [nodes, setNodes] = useState<ClassicProtocolInventoryNode[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [runtime, setRuntime] = useState<Record<string, LegacyRuntime>>({});
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [focusNodeId, setFocusNodeId] = useState(0);
  const [focusProtocol, setFocusProtocol] = useState<ClassicProtocolKey | "">("");
  const [domainNodeId, setDomainNodeId] = useState(0);
  const [domainDraft, setDomainDraft] = useState("");
  const [domainMeta, setDomainMeta] = useState<XrayDomainState | null>(null);

  const load = async () => {
    setError("");
    const payload = await legacyAdminApi.classicProtocols();
    setNodes(payload.nodes || []);
    setDrafts(current => {
      const next = {...current};
      for (const node of payload.nodes || []) {
        for (const row of node.protocols || []) {
          const def = DEF_MAP.get(row.protocol);
          const key = keyOf(node.id, row.protocol);
          if (!(key in next)) {
            next[key] = {
              port: Number(row.port || def?.defaultPort || 0),
              transport: row.protocol === "openvpn" && row.transport === "tcp" ? "tcp" : "udp",
            };
          }
        }
      }
      return next;
    });
    setLoaded(true);
  };

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const nodeId = Number(params.get("node") || 0);
      const classic = String(params.get("classic") || "").toLowerCase();
      if (Number.isFinite(nodeId) && nodeId > 0) setFocusNodeId(nodeId);
      if (CLASSIC_PROTOCOLS.some(row => row.key === classic)) setFocusProtocol(classic as ClassicProtocolKey);
    }
    void load().catch(reason => {
      setLoaded(true);
      setError(reason instanceof Error ? reason.message : String(reason));
    });
  }, []);

  const visibleNodes = useMemo(
    () => focusNodeId ? nodes.filter(node => node.id === focusNodeId) : nodes,
    [nodes, focusNodeId],
  );

  const enabledCount = useMemo(
    () => nodes.reduce((total, node) => total + node.protocols.filter(row => row.enabled).length, 0),
    [nodes],
  );

  const healthyCount = useMemo(
    () => Object.values(runtime).filter(row => row?.ok).length,
    [runtime],
  );

  const health = async (node: ClassicProtocolInventoryNode, protocol: ClassicProtocolKey) => {
    if (busy) return;
    const key = keyOf(node.id, protocol);
    setBusy(`health:${key}`);
    setError("");
    setNotice("");
    try {
      const result = await legacyAdminApi.protocolHealth(node.id, protocol);
      const rows = result && typeof result.protocols === "object" && result.protocols
        ? result.protocols as Record<string, LegacyRuntime>
        : {};
      const row = rows[protocol] || {};
      setRuntime(current => ({...current, [key]: row}));
      setChecked(current => ({...current, [key]: true}));
      await load();
      setNotice(row.ok
        ? pick(`${DEF_MAP.get(protocol)?.label || protocol} روی ${node.name} سالم است.`, `${DEF_MAP.get(protocol)?.label || protocol} is healthy on ${node.name}.`)
        : pick(`${DEF_MAP.get(protocol)?.label || protocol} روی ${node.name} نیاز به بررسی دارد.`, `${DEF_MAP.get(protocol)?.label || protocol} needs attention on ${node.name}.`));
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally { setBusy(""); }
  };

  const ensure = async (node: ClassicProtocolInventoryNode, row: ClassicProtocolInventoryRow) => {
    if (busy) return;
    const def = DEF_MAP.get(row.protocol);
    if (!def) return;
    const key = keyOf(node.id, row.protocol);
    const draft = drafts[key] || {port: Number(row.port || def.defaultPort || 0), transport: "udp" as const};
    const action = row.enabled ? pick("اعمال / Repair", "Apply / repair") : pick("نصب / فعال‌سازی", "Install / enable");
    if (!window.confirm(pick(
      `${action} ${def.label} روی ${node.name} انجام شود؟`,
      `${action} ${def.label} on ${node.name}?`,
    ))) return;

    setBusy(`ensure:${key}`);
    setError("");
    setNotice("");
    try {
      const result = await legacyAdminApi.ensureClassicProtocol({
        node_id: node.id,
        protocol: row.protocol,
        ...(row.protocol === "l2tp" ? {} : {port: draft.port}),
        ...(row.protocol === "openvpn" ? {transport: draft.transport} : {}),
      });
      const runtimeRow = result && typeof result.runtime === "object" && result.runtime
        ? result.runtime as LegacyRuntime
        : {};
      setRuntime(current => ({...current, [key]: runtimeRow}));
      setChecked(current => ({...current, [key]: true}));
      await load();
      setNotice(pick(
        `${def.label} روی ${node.name} نصب/Repair و Health Check شد.`,
        `${def.label} was installed/repaired and health-checked on ${node.name}.`,
      ));
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      await load().catch(() => undefined);
    }
    finally { setBusy(""); }
  };

  const restart = async (node: ClassicProtocolInventoryNode, protocol: ClassicProtocolKey) => {
    if (busy) return;
    const key = keyOf(node.id, protocol);
    setBusy(`restart:${key}`);
    setError("");
    setNotice("");
    try {
      const result = await legacyAdminApi.restartProtocol(node.id, protocol);
      const row = result && typeof result.protocol === "object" && result.protocol
        ? result.protocol as LegacyRuntime
        : {};
      setRuntime(current => ({...current, [key]: row}));
      setChecked(current => ({...current, [key]: true}));
      setNotice(pick("سرویس ریستارت شد.", "Service restarted."));
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(""); }
  };

  const openXrayDomain = async (node: ClassicProtocolInventoryNode) => {
    if (busy) return;
    setBusy(`domain-load:${node.id}`);
    setError("");
    try {
      const result = await adminApi.xrayDomain(node.id);
      setDomainNodeId(node.id);
      setDomainMeta(result);
      setDomainDraft(String(result.xray_domain || ""));
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(""); }
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
        setNotice(pick(`دامنه Xray ${node?.name || ""} ذخیره شد و TLS آماده شد.`, `${node?.name || "Xray"} domain saved and TLS prepared.`));
      }
      else setNotice(pick("دامنه Xray ذخیره شد.", "Xray domain saved."));
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(""); }
  };

  const orderedProtocols = focusProtocol
    ? [...CLASSIC_PROTOCOLS].sort((a, b) => Number(b.key === focusProtocol) - Number(a.key === focusProtocol))
    : CLASSIC_PROTOCOLS;

  if (!loaded && !error) return <div className={styles.warningBox}>{pick("در حال دریافت پروتکل‌های کلاسیک…", "Loading classic protocols…")}</div>;

  return (
    <>
      {error && <div className={styles.errorBox}>{error}</div>}
      {notice && <div className={styles.successBox}>{notice}</div>}

      <div className={styles.categoryHead}>
        <h3>{pick("VPN و پروتکل‌های کلاسیک", "Classic VPN protocols")}</h3>
        <span>{pick("نصب، Health، Repair و تنظیمات واقعی در یک صفحه", "Real install, health, repair and settings in one page")}</span>
      </div>

      <div className={styles.summaryGrid}>
        <div className={styles.summaryCard}><small>{pick("نود خروجی", "Exit nodes")}</small><strong>{nodes.length.toLocaleString("fa-IR")}</strong></div>
        <div className={styles.summaryCard}><small>{pick("پروتکل فعال", "Enabled protocols")}</small><strong>{enabledCount.toLocaleString("fa-IR")}</strong></div>
        <div className={styles.summaryCard}><small>{pick("سالم پس از Health", "Healthy after check")}</small><strong>{healthyCount.toLocaleString("fa-IR")}</strong></div>
        <div className={styles.summaryCard}><small>{pick("مدیریت", "Management")}</small><strong>{pick("یکپارچه", "Unified")}</strong></div>
      </div>

      {focusNodeId > 0 && (
        <div className={styles.warningBox}>
          {pick("نمایش روی نود انتخاب‌شده متمرکز شده است.", "The studio is focused on the selected node.")} {" "}
          <button className={styles.secondary} onClick={() => setFocusNodeId(0)}>{pick("نمایش همه نودها", "Show all nodes")}</button>
        </div>
      )}

      {visibleNodes.map(node => (
        <section className={styles.nodeCard} key={`legacy:${node.id}`}>
          <div className={styles.nodeHead}>
            <div className={styles.nodeTitle}>
              <strong>{node.name}</strong>
              <span>{node.public_domain || node.public_ip || "—"}</span>
            </div>
            <div className={styles.nodeActions}>
              <Badge tone={statusTone(node.status)}>{node.status || "—"}</Badge>
            </div>
          </div>

          <div className={styles.category}>
            <div className={styles.categoryHead}>
              <h3>{pick("پروتکل‌های این نود", "Protocols on this node")}</h3>
              <span>{node.protocols.filter(row => row.enabled).length.toLocaleString("fa-IR")} / {CLASSIC_PROTOCOLS.length.toLocaleString("fa-IR")} {pick("فعال", "enabled")}</span>
            </div>

            <div className={styles.protocolGrid}>
              {orderedProtocols.map(def => {
                const row = rowFor(node, def.key) || {
                  protocol: def.key,
                  enabled: false,
                  port: def.defaultPort,
                  port_text: def.key === "l2tp" ? "500/4500/1701" : String(def.defaultPort || ""),
                  transport: def.key === "openvpn" ? "udp" : def.transport,
                  status: "not_installed",
                } satisfies ClassicProtocolInventoryRow;
                const itemKey = keyOf(node.id, def.key);
                const run = runtime[itemKey];
                const wasChecked = Boolean(checked[itemKey]);
                const draft = drafts[itemKey] || {port: Number(row.port || def.defaultPort || 0), transport: row.transport === "tcp" ? "tcp" : "udp"};
                return (
                  <article className={styles.protocolCard} key={itemKey} data-classic-protocol={def.key}>
                    <div className={styles.protocolTop}>
                      <div className={styles.protocolName}>
                        <strong>{def.label}</strong>
                        <small>{def.core} · {row.transport || def.transport}</small>
                      </div>
                      {protocolBadge(row, run, wasChecked, pick)}
                    </div>

                    <div className={styles.chips}>
                      <span className={`${styles.chip} ${row.enabled ? styles.chipReady : styles.chipPending}`}>
                        {row.enabled ? pick("Production / فعال", "Production / enabled") : pick("آماده نصب", "Ready to install")}
                      </span>
                      {row.service && <span className={styles.chip}>{row.service}</span>}
                      <span className={styles.chip}>{pick("پورت", "Port")} {row.port_text || "—"}</span>
                    </div>

                    {def.key === "l2tp" ? (
                      <div className={styles.portRow}><label>{pick("پورت‌های ثابت", "Fixed ports")}</label><strong dir="ltr">500 / 4500 / 1701 UDP</strong></div>
                    ) : (
                      <div className={styles.portRow}>
                        <label>{pick("پورت Listener", "Listener port")}</label>
                        <input type="number" min={1} max={65535} value={draft.port} onChange={event => setDrafts(current => ({...current, [itemKey]: {...draft, port: Number(event.target.value)}}))}/>
                      </div>
                    )}

                    {def.key === "openvpn" && (
                      <div className={styles.portRow}>
                        <label>{pick("Transport", "Transport")}</label>
                        <select value={draft.transport} onChange={event => setDrafts(current => ({...current, [itemKey]: {...draft, transport: event.target.value as "udp" | "tcp"}}))}>
                          <option value="udp">UDP</option>
                          <option value="tcp">TCP</option>
                        </select>
                      </div>
                    )}

                    {(run?.error || row.last_error) && <div className={styles.errorBox}>{run?.error || row.last_error}</div>}

                    <div className={styles.cardActions}>
                      <button className={styles.primary} disabled={!!busy} onClick={() => void ensure(node, row)}>
                        {busy === `ensure:${itemKey}` ? "…" : row.enabled ? pick("اعمال / Repair", "Apply / repair") : pick("نصب / فعال‌سازی", "Install / enable")}
                      </button>
                      {row.enabled && (
                        <button className={styles.secondary} disabled={!!busy} onClick={() => void health(node, def.key)}>
                          {busy === `health:${itemKey}` ? "…" : "Health"}
                        </button>
                      )}
                      {row.enabled && wasChecked && !run?.ok && (
                        <button className={styles.secondary} disabled={!!busy} onClick={() => void restart(node, def.key)}>
                          {busy === `restart:${itemKey}` ? "…" : pick("ریستارت", "Restart")}
                        </button>
                      )}
                      {def.key === "v2ray" && row.enabled && (
                        <button className={styles.secondary} disabled={!!busy} onClick={() => void openXrayDomain(node)}>
                          {busy === `domain-load:${node.id}` ? "…" : pick("دامنه و TLS", "Domain & TLS")}
                        </button>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          </div>

          {domainNodeId === node.id && rowFor(node, "v2ray")?.enabled && (
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
                <button className={styles.secondary} disabled={!!busy} onClick={() => void saveXrayDomain(false)}>{busy === `domain-save:${node.id}` ? "…" : pick("ذخیره دامنه", "Save domain")}</button>
                <button className={styles.primary} disabled={!!busy || !domainDraft.trim()} onClick={() => void saveXrayDomain(true)}>{busy === `domain-prepare:${node.id}` ? "…" : pick("ذخیره و آماده‌سازی TLS", "Save & prepare TLS")}</button>
                <button className={styles.secondary} disabled={!!busy} onClick={() => {setDomainNodeId(0); setDomainMeta(null); setDomainDraft("");}}>{pick("بستن", "Close")}</button>
              </div>
            </div>
          )}
        </section>
      ))}

      {!visibleNodes.length && !error && <div className={styles.warningBox}>{pick("نود خروجی موردنظر پیدا نشد.", "No matching Exit node was found.")}</div>}
    </>
  );
}
