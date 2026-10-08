from __future__ import annotations

# TWINPANEL_AUTO_BACKUP_WORKER_V1

import json

from .backup_service import (
    run_auto_backup_if_due,
)


def main() -> None:

    result = (
        run_auto_backup_if_due()
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            default=str,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
