"use client";

import {useEffect, useState} from "react";

import {TunnelsPanelRuntimeV31} from "./tunnels-panel-runtime-v31";
import {
  TunnelsSimpleRuntimePage as TunnelsServiceConnectionsRuntime,
} from "./tunnels-service-connections-runtime";


type TunnelPanelView = "control" | "service-connections";


export function TunnelsSimpleRuntimePage() {
  const [view, setView] = useState<TunnelPanelView>("control");

  useEffect(() => {
    const syncFromHash = () => {
      setView(
        window.location.hash === "#service-connections"
          ? "service-connections"
          : "control",
      );
    };

    syncFromHash();
    window.addEventListener("hashchange", syncFromHash);

    return () => {
      window.removeEventListener("hashchange", syncFromHash);
    };
  }, []);

  const choose = (next: TunnelPanelView) => {
    if (next === "service-connections") {
      window.location.hash = "service-connections";
    }
    else {
      window.history.replaceState(
        null,
        "",
        `${window.location.pathname}${window.location.search}`,
      );
      setView("control");
    }
  };

  return (
    <>
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

      {view === "service-connections"
        ? <TunnelsServiceConnectionsRuntime />
        : <TunnelsPanelRuntimeV31 />}
    </>
  );
}
