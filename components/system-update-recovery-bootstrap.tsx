const UPDATE_RELOAD_KEY="twinpanel-update-reload-pending-v4";

/*
 * Runs before React hydration.
 *
 * SystemReleaseFooter marks a completed update with `reload_from` immediately
 * before forcing the one intentional page reload. On the next document the
 * marker is no longer a recovery-in-progress marker; keeping it would make
 * the client footer auto-open the update dialog again and leave it open until
 * the operator closes it manually.
 *
 * Clear only that post-completion marker here. Markers without `reload_from`
 * are preserved so a genuine in-progress update still restores its progress UI
 * after an operator-initiated refresh.
 */
const BOOTSTRAP_SOURCE=`(()=>{try{const key=${JSON.stringify(UPDATE_RELOAD_KEY)};const raw=sessionStorage.getItem(key);if(!raw)return;const marker=JSON.parse(raw);if(marker&&typeof marker.reload_from==="string"&&marker.reload_from.trim())sessionStorage.removeItem(key);}catch{}})();`;

export function SystemUpdateRecoveryBootstrap(){
  return <script id="twinpanel-system-update-recovery-bootstrap" dangerouslySetInnerHTML={{__html:BOOTSTRAP_SOURCE}}/>;
}
