"use client";

import {useEffect, useState} from "react";

import {TunnelsPanelRuntimeV31} from "./tunnels-panel-runtime-v31";
import {TunnelsDeepDiagnosticsV32} from "./tunnels-deep-diagnostics-v32";
import {
  TunnelsSimpleRuntimePage as TunnelsServiceConnectionsRuntime,
} from "./tunnels-service-connections-runtime";


type TunnelPanelView = "control" | "deep-diagnostics" | "service-connections";


function deepTunnelFromHash(hash: string) {
  const match = hash.match(/^#deep-diagnostics=(\d+)$/);
  return match ? Number(match[1]) : 0;
}


export function TunnelsSimpleRuntimePage() {
  const [view, setView] = useState<TunnelPanelView>("control");
  const [deepTunnelId, setDeepTunnelId] = useState(0);

  useEffect(() => {
    const syncFromHash = () => {
      if (window.location.hash === "#service-connections") {
        setDeepTunnelId(0);
        setView("service-connections");
        return;
      }

      const requestedTunnel = deepTunnelFromHash(window.location.hash);
      if (requestedTunnel > 0 || window.location.hash === "#deep-diagnostics") {
        setDeepTunnelId(requestedTunnel);
        setView("deep-diagnostics");
        return;
      }

      setDeepTunnelId(0);
      setView("control");
    };

    syncFromHash();
    window.addEventListener("hashchange", syncFromHash);

    return () => {
      window.removeEventListener("hashchange", syncFromHash);
    };
  }, []);

  const choose = (next: Exclude<TunnelPanelView, "deep-diagnostics">) => {
    if (next === "service-connections") {
      window.location.hash = "service-connections";
      return;
    }

    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${window.location.search}`,
    );
    setDeepTunnelId(0);
    setView("control");
  };

  const openDeepDiagnostics = (tunnelId: number) => {
    const id = Number(tunnelId);
    if (!Number.isFinite(id) || id <= 0) return;
    window.location.hash = `deep-diagnostics=${id}`;
  };

  return (
    <>
      {view !== "deep-diagnostics" ? (
        <div
          className="action-row"
          style={{
            position: "fixed",
            top: 76,
            insetInlineEnd: 24,
            zIndex: 1400,
          }}
        >
          <button
            type="button"
            className={view === "control" ? "primary-soft" : "ghost"}
            onClick={() => choose("control")}
          >
            کنترل کامل تانل
          </button>

          <button
            type="button"
            className={view === "service-connections" ? "primary-soft" : "ghost"}
            onClick={() => choose("service-connections")}
          >
            اتصال‌های سرویس
          </button>
        </div>
      ) : null}

      {view === "service-connections"
        ? <TunnelsServiceConnectionsRuntime />
        : view === "deep-diagnostics"
          ? (
            <TunnelsDeepDiagnosticsV32
              initialTunnelId={deepTunnelId}
              onBack={() => choose("control")}
            />
          )
          : <TunnelsPanelRuntimeV31 onDeepDiagnostics={openDeepDiagnostics} />}
    </>
  );
}
