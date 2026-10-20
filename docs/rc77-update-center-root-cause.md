# TwinPanel rc.77 — System Update Center root cause

Real-server evidence from `217.179.6.142` on rc.76 exposed two defects in the rc.76 correction itself.

## 1. Card top could still become unreachable

The legacy release card already has padding and a border. rc.76 set `max-height` on the card without `box-sizing:border-box`, so the rendered border-box could exceed the live viewport even though the CSS content box appeared bounded. At the same time the modal shell was made scrollable while the card remained vertically centered. On a short viewport this combination can place the card's top edge above the reachable scroll origin.

rc.77 keeps the modal shell fixed/non-scrollable, bounds the complete card border-box using `100dvh`/`100vh`, and makes the card itself the only vertical scroll container.

## 2. Post-update modal could reopen after refresh

rc.76's pre-hydration cleanup removed the recovery marker only when it already contained `reload_from`. `RuntimeVersionConvergence` can refresh the document as soon as the server version changes, before `SystemReleaseFooter` gets a chance to write `reload_from`. The next document then sees the stale marker and opens the update dialog again even though the new release is already active.

rc.77 treats a full document load as a lifecycle boundary and clears the session recovery marker before hydration. The backend release-status endpoint remains authoritative: if the update is still actually active, `SystemReleaseFooter` will reopen progress from the backend state; if the update already completed, no stale client marker can reopen the dialog.

No backend, API, auth, provisioning, tunnel, updater service, or Nginx behavior is changed by this correction.
