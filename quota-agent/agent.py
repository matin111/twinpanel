#!/usr/bin/env python3

import hashlib
import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import uuid

from datetime import datetime, timezone
from pathlib import Path


CONFIG_FILE = Path(
    "/etc/twinpanel-quota-agent/config.json"
)

STATE_DIR = Path(
    "/var/lib/twinpanel-quota-agent"
)

STATE_FILE = (
    STATE_DIR / "state.json"
)

POLL_SECONDS = 5

# Xray stats do not directly tell us whether a
# tunnel is still connected. We treat continued
# traffic as an active quota session.
SESSION_IDLE_SECONDS = 60


def log(message):

    now = datetime.now(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    )

    print(
        f"{now} {message}",
        flush=True,
    )


def load_json(
    path,
    default,
):

    try:

        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception:

        return default


def atomic_json(
    path,
    value,
):

    tmp = Path(
        str(path) + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    os.replace(
        tmp,
        path,
    )


def load_config():

    cfg = load_json(
        CONFIG_FILE,
        None,
    )

    if not isinstance(
        cfg,
        dict,
    ):
        raise RuntimeError(
            "invalid agent config"
        )

    return cfg


def normalize_devices(
    cfg,
):

    result = []

    for d in cfg.get(
        "devices",
        [],
    ):

        if not isinstance(
            d,
            dict,
        ):
            continue

        if (
            d.get("protocol")
            != "xray"
        ):
            continue

        subscription_id = int(
            d["subscription_id"]
        )

        email = d.get(
            "identity"
        )

        if not email:

            email = (
                f"mv-{subscription_id}"
                "@moviline"
            )

        result.append({
            "device_id":
                int(
                    d["device_id"]
                ),

            "subscription_id":
                subscription_id,

            "protocol":
                "xray",

            "email":
                str(email),
        })

    return result


def xray_query():

    p = subprocess.run(
        [
            "/usr/local/bin/xray",
            "api",
            "statsquery",
            "--server=127.0.0.1:10085",
            "-pattern",
            "user>>>",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )

    if p.returncode != 0:

        raise RuntimeError(
            "xray statsquery failed: "
            + p.stderr.strip()
        )

    raw = p.stdout.strip()

    if not raw:
        return {}

    data = json.loads(
        raw
    )

    result = {}

    for item in data.get(
        "stat",
        [],
    ):

        name = str(
            item.get(
                "name",
                "",
            )
        )

        value = int(
            item.get(
                "value",
                0,
            )
        )

        parts = name.split(
            ">>>"
        )

        if len(parts) != 4:
            continue

        if parts[0] != "user":
            continue

        if parts[2] != "traffic":
            continue

        email = parts[1]
        direction = parts[3]

        row = result.setdefault(
            email,
            {
                "uplink": 0,
                "downlink": 0,
            },
        )

        if direction == "uplink":

            row["uplink"] = value

        elif direction == "downlink":

            row["downlink"] = value

    return result


def api_request(
    cfg,
    method,
    path,
    payload=None,
):

    url = (
        cfg["api_base"]
        .rstrip("/")
        + path
    )

    headers = {
        "Accept":
            "application/json",
    }

    body = None

    if payload is not None:

        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode(
            "utf-8"
        )

        headers[
            "Content-Type"
        ] = "application/json"


    request = (
        urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )
    )


    context = (
        ssl.create_default_context()
    )

    context.load_cert_chain(
        certfile=cfg[
            "client_cert"
        ],
        keyfile=cfg[
            "client_key"
        ],
    )


    try:

        with urllib.request.urlopen(
            request,
            context=context,
            timeout=15,
        ) as response:

            raw = (
                response.read()
                .decode(
                    "utf-8",
                    errors="replace",
                )
            )

            if not raw:
                return None

            return json.loads(
                raw
            )


    except urllib.error.HTTPError as exc:

        raw = (
            exc.read()
            .decode(
                "utf-8",
                errors="replace",
            )
        )

        raise RuntimeError(
            f"HTTP {exc.code}: {raw}"
        ) from exc


def make_event_id(
    node_id,
    source_key,
    epoch,
    sequence,
):

    raw = (
        f"{node_id}|"
        f"{source_key}|"
        f"{epoch}|"
        f"{sequence}"
    )

    digest = (
        hashlib.sha256(
            raw.encode(
                "utf-8"
            )
        ).hexdigest()
    )

    return (
        "mvq-" + digest
    )


def make_session_key(
    node_id,
    email,
):

    token = (
        uuid.uuid4()
        .hex[:20]
    )

    safe_email = (
        email.replace(
            "@",
            "_",
        )
        .replace(
            ">",
            "_",
        )
    )

    return (
        f"xray:{node_id}:"
        f"{safe_email}:"
        f"{token}"
    )[:160]


def initial_state():

    return {
        "version": 2,
        "sources": {},
        "pending": {},
        "sessions": {},
    }


def save_state(
    state,
):

    state["version"] = 2

    atomic_json(
        STATE_FILE,
        state,
    )


def open_quota_session(
    cfg,
    state,
    node_id,
    device,
    source_key,
):

    sessions = state[
        "sessions"
    ]

    current = sessions.get(
        source_key
    )

    if (
        isinstance(
            current,
            dict,
        )
        and
        current.get(
            "status"
        ) == "active"
    ):

        return current.get(
            "session_key"
        )


    session_key = (
        make_session_key(
            node_id,
            device["email"],
        )
    )


    payload = {
        "session_key":
            session_key,

        "subscription_id":
            device[
                "subscription_id"
            ],

        "device_id":
            device[
                "device_id"
            ],

        "protocol":
            "xray",

        "client_ip":
            None,
    }


    try:

        result = api_request(
            cfg,
            "POST",
            (
                f"/v1/nodes/"
                f"{node_id}"
                "/quota/sessions/open"
            ),
            payload,
        )

    except Exception as exc:

        # Usage accounting must continue even
        # when session tracking temporarily fails.
        log(
            "session open failed "
            f"{source_key} "
            f"{exc!r}"
        )

        return None


    sessions[
        source_key
    ] = {
        "session_key":
            session_key,

        "status":
            "active",

        "last_activity":
            time.time(),

        "subscription_id":
            device[
                "subscription_id"
            ],

        "device_id":
            device[
                "device_id"
            ],

        "protocol":
            "xray",
    }

    save_state(
        state
    )


    log(
        "session opened "
        f"{session_key} "
        f"sub="
        f"{device['subscription_id']} "
        f"device="
        f"{device['device_id']} "
        f"api_status="
        f"{result.get('status') if isinstance(result, dict) else '?'}"
    )


    return session_key


def mark_activity(
    state,
    source_key,
):

    session = (
        state["sessions"]
        .get(
            source_key
        )
    )

    if not isinstance(
        session,
        dict,
    ):
        return

    if (
        session.get(
            "status"
        )
        != "active"
    ):
        return

    session[
        "last_activity"
    ] = time.time()


def close_idle_sessions(
    cfg,
    state,
    node_id,
):

    now = time.time()

    changed = False


    for (
        source_key,
        session,
    ) in list(
        state[
            "sessions"
        ].items()
    ):

        if not isinstance(
            session,
            dict,
        ):
            continue

        if (
            session.get(
                "status"
            )
            != "active"
        ):
            continue

        last_activity = float(
            session.get(
                "last_activity",
                0,
            )
        )

        if (
            now - last_activity
            < SESSION_IDLE_SECONDS
        ):
            continue


        session_key = (
            session.get(
                "session_key"
            )
        )

        if not session_key:
            continue


        try:

            result = api_request(
                cfg,
                "POST",
                (
                    f"/v1/nodes/"
                    f"{node_id}"
                    "/quota/sessions/close"
                ),
                {
                    "session_key":
                        session_key,

                    "reason":
                        "idle_timeout",
                },
            )

        except Exception as exc:

            log(
                "session close failed "
                f"{session_key} "
                f"{exc!r}"
            )

            continue


        session[
            "status"
        ] = "closed"

        session[
            "closed_at"
        ] = now

        changed = True


        log(
            "session closed "
            f"{session_key} "
            f"reason=idle_timeout "
            f"api_status="
            f"{result.get('status') if isinstance(result, dict) else '?'}"
        )


    if changed:

        save_state(
            state
        )


def replay_pending(
    cfg,
    state,
    node_id,
):

    pending_ids = list(
        state[
            "pending"
        ].keys()
    )


    for eid in pending_ids:

        pending = (
            state[
                "pending"
            ][eid]
        )

        result = api_request(
            cfg,
            "POST",
            (
                f"/v1/nodes/"
                f"{node_id}"
                "/quota/usage-events"
            ),
            pending[
                "payload"
            ],
        )


        source_key = pending[
            "source_key"
        ]

        source = (
            state[
                "sources"
            ][source_key]
        )


        source[
            "last_uplink"
        ] = int(
            pending[
                "commit_uplink"
            ]
        )

        source[
            "last_downlink"
        ] = int(
            pending[
                "commit_downlink"
            ]
        )

        source[
            "sequence"
        ] = int(
            pending[
                "payload"
            ][
                "source_sequence"
            ]
        )


        del state[
            "pending"
        ][eid]


        save_state(
            state
        )


        log(
            "pending usage accepted "
            f"event="
            f"{eid[:20]} "
            f"billable="
            f"{result.get('billable_bytes') if isinstance(result, dict) else '?'}"
        )


def main():

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    os.chmod(
        STATE_DIR,
        0o700,
    )


    cfg = load_config()

    node_id = int(
        cfg["node_id"]
    )

    devices = (
        normalize_devices(
            cfg
        )
    )


    state = load_json(
        STATE_FILE,
        initial_state(),
    )


    if not isinstance(
        state,
        dict,
    ):
        state = (
            initial_state()
        )


    if not isinstance(
        state.get(
            "sources"
        ),
        dict,
    ):
        state[
            "sources"
        ] = {}


    if not isinstance(
        state.get(
            "pending"
        ),
        dict,
    ):
        state[
            "pending"
        ] = {}


    # Migration from Agent v1.
    if not isinstance(
        state.get(
            "sessions"
        ),
        dict,
    ):
        state[
            "sessions"
        ] = {}


    save_state(
        state
    )


    log(
        "TwinPanel Quota Agent v2 "
        f"started node={node_id} "
        f"xray_devices="
        f"{len(devices)} "
        f"idle="
        f"{SESSION_IDLE_SECONDS}s"
    )


    while True:

        try:

            # First resend anything that may
            # have been accepted before a crash.
            replay_pending(
                cfg,
                state,
                node_id,
            )


            counters = (
                xray_query()
            )


            for device in devices:

                email = (
                    device[
                        "email"
                    ]
                )

                current = (
                    counters.get(
                        email
                    )
                )

                if current is None:
                    continue


                source_key = (
                    "xray:user:"
                    + email
                )


                source = (
                    state[
                        "sources"
                    ].get(
                        source_key
                    )
                )


                new_up = int(
                    current[
                        "uplink"
                    ]
                )

                new_down = int(
                    current[
                        "downlink"
                    ]
                )


                # First ever observation:
                # baseline only, no billing.
                if source is None:

                    state[
                        "sources"
                    ][source_key] = {
                        "epoch":
                            uuid.uuid4()
                            .hex,

                        "sequence":
                            0,

                        "last_uplink":
                            new_up,

                        "last_downlink":
                            new_down,
                    }


                    save_state(
                        state
                    )


                    log(
                        "baseline created "
                        f"{source_key} "
                        f"up={new_up} "
                        f"down={new_down}"
                    )

                    continue


                old_up = int(
                    source[
                        "last_uplink"
                    ]
                )

                old_down = int(
                    source[
                        "last_downlink"
                    ]
                )


                # Xray process/config reset:
                # establish another safe baseline.
                if (
                    new_up < old_up
                    or
                    new_down < old_down
                ):

                    old_session = (
                        state[
                            "sessions"
                        ].get(
                            source_key
                        )
                    )

                    if (
                        isinstance(
                            old_session,
                            dict,
                        )
                        and
                        old_session.get(
                            "status"
                        ) == "active"
                    ):

                        try:

                            api_request(
                                cfg,
                                "POST",
                                (
                                    f"/v1/nodes/"
                                    f"{node_id}"
                                    "/quota/sessions/close"
                                ),
                                {
                                    "session_key":
                                        old_session[
                                            "session_key"
                                        ],

                                    "reason":
                                        "counter_reset",
                                },
                            )

                            old_session[
                                "status"
                            ] = "closed"

                        except Exception as exc:

                            log(
                                "session reset close failed "
                                f"{exc!r}"
                            )


                    source[
                        "epoch"
                    ] = (
                        uuid.uuid4()
                        .hex
                    )

                    source[
                        "sequence"
                    ] = 0

                    source[
                        "last_uplink"
                    ] = new_up

                    source[
                        "last_downlink"
                    ] = new_down


                    save_state(
                        state
                    )


                    log(
                        "counter reset -> "
                        "new safe baseline "
                        f"{source_key}"
                    )

                    continue


                up_delta = (
                    new_up - old_up
                )

                down_delta = (
                    new_down - old_down
                )


                if (
                    up_delta == 0
                    and
                    down_delta == 0
                ):
                    continue


                # Traffic means this quota
                # session is active.
                session_key = (
                    open_quota_session(
                        cfg,
                        state,
                        node_id,
                        device,
                        source_key,
                    )
                )


                if session_key:

                    mark_activity(
                        state,
                        source_key,
                    )


                sequence = (
                    int(
                        source[
                            "sequence"
                        ]
                    )
                    + 1
                )


                eid = (
                    make_event_id(
                        node_id,
                        source_key,
                        source[
                            "epoch"
                        ],
                        sequence,
                    )
                )


                payload = {
                    "event_id":
                        eid,

                    "subscription_id":
                        device[
                            "subscription_id"
                        ],

                    "device_id":
                        device[
                            "device_id"
                        ],

                    "session_key":
                        session_key,

                    "protocol":
                        "xray",

                    "source_key":
                        source_key,

                    "counter_mode":
                        "delta",

                    "counter_epoch":
                        source[
                            "epoch"
                        ],

                    "source_sequence":
                        sequence,

                    "uplink_value":
                        up_delta,

                    "downlink_value":
                        down_delta,

                    "reported_at":
                        datetime.now(
                            timezone.utc
                        ).isoformat(),
                }


                # Persist before send for
                # at-least-once delivery.
                state[
                    "pending"
                ][eid] = {
                    "source_key":
                        source_key,

                    "commit_uplink":
                        new_up,

                    "commit_downlink":
                        new_down,

                    "payload":
                        payload,
                }


                save_state(
                    state
                )


                result = api_request(
                    cfg,
                    "POST",
                    (
                        f"/v1/nodes/"
                        f"{node_id}"
                        "/quota/usage-events"
                    ),
                    payload,
                )


                source[
                    "last_uplink"
                ] = new_up

                source[
                    "last_downlink"
                ] = new_down

                source[
                    "sequence"
                ] = sequence


                del state[
                    "pending"
                ][eid]


                save_state(
                    state
                )


                log(
                    f"xray {email} "
                    f"session="
                    f"{session_key or '-'} "
                    f"up_delta="
                    f"{up_delta} "
                    f"down_delta="
                    f"{down_delta} "
                    f"billable="
                    f"{result.get('billable_bytes') if isinstance(result, dict) else '?'}"
                )


            close_idle_sessions(
                cfg,
                state,
                node_id,
            )


        except Exception as exc:

            log(
                "ERROR "
                + repr(exc)
            )


        time.sleep(
            POLL_SECONDS
        )


if __name__ == "__main__":
    main()
