const UPDATE_RELOAD_KEY="twinpanel-update-reload-pending-v4";

/*
 * Runs before React hydration.
 *
 * A full document load is a hard lifecycle boundary. The authoritative update
 * state is the release status endpoint, not a stale sessionStorage marker. In
 * rc.76 we only removed markers carrying `reload_from`, which left a race with
 * RuntimeVersionConvergence: that runtime can refresh the page before the
 * footer writes `reload_from`, so the next mount sees the stale marker and
 * reopens the update dialog even though the new version is already active.
 *
 * Clear the recovery marker on every full document load. If an update is still
 * active, SystemReleaseFooter will reopen the progress UI from the backend's
 * queued/downloading/restarting state as soon as status is reachable. This
 * removes the stale-marker race without hiding genuine in-progress updates.
 */
const BOOTSTRAP_SOURCE=`(()=>{try{sessionStorage.removeItem(${JSON.stringify(UPDATE_RELOAD_KEY)});}catch{}})();`;

export function SystemUpdateRecoveryBootstrap(){
  return <script id="twinpanel-system-update-recovery-bootstrap" dangerouslySetInnerHTML={{__html:BOOTSTRAP_SOURCE}}/>;
}
