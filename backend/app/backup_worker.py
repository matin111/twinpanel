from __future__ import annotations

# TWINPANEL_AUTO_BACKUP_WORKER_V1

import json

from .backup_service import (
    run_auto_backup_if_due,
)


def main() -> None:
    # The scheduled worker and the on-demand systemd worker share one lock.
    # Protects memory/disk and avoids duplicating Telegram backup uploads.
    import fcntl
    from pathlib import Path
    with Path("/run/twinpanel-backup.lock").open("a+") as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            result={"ok":True,"ran":False,"reason":"backup_job_already_running"}
        else:
            result=run_auto_backup_if_due()
    print(json.dumps(result,ensure_ascii=False,default=str),flush=True)


if __name__ == "__main__":
    main()
