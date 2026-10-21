"use client";

import {useEffect, useMemo, useState} from "react";

import {adminApi, type AdminNode} from "../lib/admin-api";
import {legacyAdminApi} from "../lib/legacy-admin-api";
import {useI18n} from "../lib/i18n";
import {Badge} from "./ui";
import styles from "./modern-protocols-admin-v2.module.css";

const CLASSIC_PROTOCOLS = [
  {key: "cisco", name: "Cisco / OpenConnect", core: "ocserv", transport: "TCP + UDP", port: "443"},
  {key: "openvpn", name: "OpenVPN", core: "OpenVPN", transport: "UDP / TCP", port: "1194"},
  {key: "wireguard", name: "WireGuard", core: "WireGuard", transport: "UDP", port: "51820"},
  {key: "l2tp", name: "L2TP / IPsec", core: "strongSwan + xl2tpd", transport: "UDP", port: "500 / 4500 / 1701"},
  {key: "v2ray", name: "V2Ray / Xray", core: "Xray", transport: "TCP", port: "8443"},
] as const;

type ClassicKey = (typeof CLASSIC_PROTOCOLS)[number]["key"];
type ClassicRuntime = {
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

type HealthResponse = {
  ok?: boolean;
  protocols?: Record<string, ClassicRuntime>;
};

type RestartResponse = {
  ok?: boolean;
  protocol?: ClassicRuntime;
};

function isExit(node: AdminNode) {
  return String(node.node_type || "").toLowerCase() === "exit";
}

function isEnabled(node: AdminNode, protocol: ClassicKey) {
  return Boolean(node[`enable_${protocol}` as keyof AdminNode]);
}

function statusTone(enabled: boolean, runtime?: ClassicRuntime): "ok" | "warn" | "bad" | "violet" {
  if (!enabled) return "warn";
  if (!runtime) return "violet";
  return runtime.ok ? "ok" : "bad";
}

export function ClassicProtocolsStudioSection({nodeId}: {nodeId: number}) {
  const {pick} = useI18n();
  const [node, setNode] = useState<AdminNode | null>(null);
  const [runtime, setRuntime] = useState<Record<string, ClassicRuntime>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    adminApi.nodes()
      .then(nodes => {
        if (!active) return;
        const found = nodes.find(item => item.id === nodeId && isExit(item)) || null;
        setNode(found);
      })
      .catch(reason => {
        if (active) setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [nodeId]);

  const enabledCount = useMemo(
    () => node ? CLASSIC_PROTOCOLS.filter(item => isEnabled(node, item.key)).length : 0,
    [node],
  );

  const checkHealth = async () => {
    if (!node || busy) return;
    setBusy("health");
    setError("");
    setNotice("");
    try {
      const result = await legacyAdminApi.protocolHealth(node.id) as HealthResponse;
      setRuntime(result.protocols || {});
      setNotice(Boolean(result.ok)
        ? pick("سلامت پروتکل‌های اصلی تایید شد.", "Classic protocol health verified.")
        : pick("برخی پروتکل‌های اصلی نیاز به بررسی دارند.", "Some classic protocols need attention."));
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };

  const restart = async (protocol: ClassicKey) => {
    if (!node || busy || !isEnabled(node, protocol)) return;
    setBusy(`restart:${protocol}`);
    setError("");
    setNotice("");
    try {
      const result = await legacyAdminApi.restartProtocol(node.id, protocol) as RestartResponse;
      if (result.protocol) {
        setRuntime(current => ({...current, [protocol]: result.protocol || {}}));
      }
      const label = CLASSIC_PROTOCOLS.find(item => item.key === protocol)?.name || protocol;
      setNotice(pick(`${label} ریستارت شد.`, `${label} restarted.`));
    }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
    finally {
      setBusy("");
    }
  };

  if (loading) {
    return (
      <div className={styles.category}>
        <div className={styles.categoryHead}>
          <h3>{pick("پروتکل‌های اصلی", "Classic VPN protocols")}</h3>
          <span>{pick("در حال بارگذاری…", "Loading…")}</span>
        </div>
      </div>
    );
  }

  if (!node) return null;

  return (
    <div className={styles.category}>
      <div className={styles.categoryHead}>
        <div>
          <h3>{pick("پروتکل‌های اصلی", "Classic VPN protocols")}</h3>
          <span>{enabledCount.toLocaleString("fa-IR")} / {CLASSIC_PROTOCOLS.length.toLocaleString("fa-IR")} {pick("فعال", "enabled")}</span>
        </div>
        <button className={styles.secondary} disabled={!!busy} onClick={() => void checkHealth()}>
          {busy === "health" ? "…" : pick("بررسی سلامت اصلی‌ها", "Check classic health")}
        </button>
      </div>

      {error && <div className={styles.errorBox}>{error}</div>}
      {notice && <div className={styles.successBox}>{notice}</div>}

      <div className={styles.protocolGrid}>
        {CLASSIC_PROTOCOLS.map(item => {
          const enabled = isEnabled(node, item.key);
          const live = runtime[item.key];
          const port = live?.port_text || (live?.port ? String(live.port) : item.port);
          const status = !enabled
            ? pick("غیرفعال", "Disabled")
            : !live
              ? pick("فعال", "Enabled")
              : live.ok
                ? "ONLINE"
                : "CHECK";
          return (
            <article className={styles.protocolCard} key={item.key}>
              <div className={styles.protocolTop}>
                <div className={styles.protocolName}>
                  <strong>{item.name}</strong>
                  <small>{item.core} · {live?.transport || item.transport}</small>
                </div>
                <Badge tone={statusTone(enabled, live)}>{status}</Badge>
              </div>

              <div className={styles.chips}>
                <span className={`${styles.chip} ${enabled ? styles.chipReady : styles.chipPending}`}>
                  {enabled ? pick("روی نود فعال", "Enabled on node") : pick("نصب نشده", "Not installed")}
                </span>
                <span className={styles.chip}>{pick("داخلی TwinPanel", "TwinPanel built-in")}</span>
                <span className={styles.chip}>{item.transport}</span>
              </div>

              <div className={styles.portRow}>
                <label>{pick("پورت سرویس", "Service port")}</label>
                <input value={port} readOnly aria-label={pick("پورت سرویس", "Service port")}/>
              </div>

              {live?.error && <div className={styles.errorBox}>{live.error}</div>}
              {item.key === "v2ray" && live?.modern_health && (
                <div className={styles.chips}>
                  <span className={`${styles.chip} ${live.modern_health.tls_enabled ? styles.chipReady : styles.chipPending}`}>TLS {live.modern_health.tls_enabled ? "ON" : "OFF"}</span>
                  <span className={`${styles.chip} ${live.modern_health.tls_domain_configured ? styles.chipReady : styles.chipPending}`}>Domain {live.modern_health.tls_domain_configured ? "OK" : "—"}</span>
                </div>
              )}

              <div className={styles.cardActions}>
                {enabled ? (
                  <button className={styles.secondary} disabled={!!busy} onClick={() => void restart(item.key)}>
                    {busy === `restart:${item.key}` ? "…" : pick("ریستارت سرویس", "Restart service")}
                  </button>
                ) : (
                  <span className={styles.chip}>{pick("فعلاً از راه‌اندازی نود فعال می‌شود", "Currently enabled from node provisioning")}</span>
                )}
                {item.key === "v2ray" && enabled && (
                  <a className={styles.secondary} href="/admin/vpn-settings">{pick("تنظیمات Xray", "Xray settings")}</a>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
