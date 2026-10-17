"use client";

// TWINPANEL_TUNNEL_MANAGE_MODAL_POLISH_V45
// Visual-only production polish for the unified tunnel management dialog.
// The style tag is intentionally colocated with the tunnel runtime so it can
// refine the existing modal without touching shared/global CSS or other pages.

export function TunnelManageModalPolishV45(){
  return <style>{`
    .runtime-modal-card:has(.tunnel-service-connections-compact){
      width:min(1080px,calc(100vw - 40px));
      max-width:1080px;
      max-height:min(88vh,900px);
      overflow-y:auto;
      overflow-x:hidden;
      padding:14px;
      border-radius:20px;
      scrollbar-gutter:stable;
    }

    .runtime-modal-card:has(.tunnel-service-connections-compact) > .card-head{
      position:sticky;
      top:-14px;
      z-index:8;
      margin:-14px -14px 10px;
      padding:12px 14px;
      background:color-mix(in srgb,var(--panel,#0d1320) 94%,transparent);
      backdrop-filter:blur(14px);
      border-bottom:1px solid var(--line,#263247);
    }

    .runtime-modal-card:has(.tunnel-service-connections-compact) > .runtime-info-list{
      display:grid;
      grid-template-columns:repeat(4,minmax(0,1fr));
      gap:7px;
      margin-bottom:8px;
    }

    .runtime-modal-card:has(.tunnel-service-connections-compact) > .runtime-info-list > div{
      min-height:54px;
      padding:9px 11px;
      border-radius:12px;
    }

    .runtime-modal-card:has(.tunnel-service-connections-compact) > .card,
    .runtime-modal-card:has(.tunnel-service-connections-compact) .manage-card-section{
      padding:11px;
      margin-block:8px;
      border-radius:15px;
    }

    .runtime-modal-card:has(.tunnel-service-connections-compact) .card-head{
      gap:8px;
      margin-bottom:8px;
    }

    .runtime-modal-card:has(.tunnel-service-connections-compact) .card-head small{
      line-height:1.45;
    }

    .runtime-modal-card:has(.tunnel-service-connections-compact) .action-row{
      gap:7px;
    }

    .runtime-modal-card:has(.tunnel-service-connections-compact) .tunnel-service-compact-head{
      gap:10px;
      align-items:center;
    }

    .runtime-modal-card:has(.tunnel-service-connections-compact) .tunnel-service-compact-actions{
      gap:6px;
      flex-wrap:wrap;
    }

    .runtime-modal-card:has(.tunnel-service-connections-compact) .tunnel-service-compact-grid{
      display:grid;
      grid-template-columns:repeat(3,minmax(0,1fr));
      gap:8px;
    }

    .runtime-modal-card:has(.tunnel-service-connections-compact) .tunnel-service-compact-item{
      min-height:92px;
      padding:10px;
      border-radius:13px;
    }

    .runtime-modal-card:has(.tunnel-service-connections-compact) .runtime-error,
    .runtime-modal-card:has(.tunnel-service-connections-compact) .runtime-warning,
    .runtime-modal-card:has(.tunnel-service-connections-compact) .runtime-success{
      margin-block:7px;
      padding:9px 11px;
      font-size:12px;
      line-height:1.55;
      max-height:110px;
      overflow:auto;
    }

    @media (min-width:1280px){
      .runtime-modal-card:has(.tunnel-service-connections-compact){
        width:min(1160px,calc(100vw - 56px));
        max-width:1160px;
      }
      .runtime-modal-card:has(.tunnel-service-connections-compact) .tunnel-service-compact-grid{
        grid-template-columns:repeat(4,minmax(0,1fr));
      }
    }

    @media (max-width:900px){
      .runtime-modal-card:has(.tunnel-service-connections-compact){
        width:calc(100vw - 20px);
        max-height:92vh;
        padding:10px;
      }
      .runtime-modal-card:has(.tunnel-service-connections-compact) > .runtime-info-list{
        grid-template-columns:repeat(2,minmax(0,1fr));
      }
      .runtime-modal-card:has(.tunnel-service-connections-compact) .tunnel-service-compact-grid{
        grid-template-columns:repeat(2,minmax(0,1fr));
      }
    }

    @media (max-width:620px){
      .runtime-modal-card:has(.tunnel-service-connections-compact) > .runtime-info-list,
      .runtime-modal-card:has(.tunnel-service-connections-compact) .tunnel-service-compact-grid{
        grid-template-columns:1fr;
      }
    }
  `}</style>;
}
