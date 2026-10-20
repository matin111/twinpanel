from datetime import datetime
from ..quota_models import QuotaUsageEvent
from sqlalchemy import func
from fastapi import APIRouter, Depends, HTTPException
import os
import shutil
import socket
import time
import subprocess
from sqlalchemy.orm import Session
from sqlalchemy import text, case, or_

from ..database import get_db, SessionLocal
from ..deps import require_admin
from ..models import Node, NodeStatus, Plan, Subscription, SubscriptionStatus, User
from ..schemas import AdminPasswordResetIn, AdminStatsOut, UserOut, AdminUserCreateIn, AdminUserUpdateIn
from ..security import hash_password

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/stats", response_model=AdminStatsOut)
def stats(db: Session = Depends(get_db)):
    return AdminStatsOut(
        users=db.query(User).count(),
        active_subscriptions=db.query(Subscription).filter(
            Subscription.status == SubscriptionStatus.ACTIVE
        ).count(),
        online_nodes=db.query(Node).filter(Node.retired_at.is_(None)).filter(Node.status == NodeStatus.ONLINE).count(),
        active_plans=db.query(Plan).filter(Plan.is_active.is_(True)).count(),
    )


def _read_cpu_times() -> tuple[int, int]:
    try:
        with open("/proc/stat", "r", encoding="utf-8") as handle:
            parts = handle.readline().split()
        values = [int(value) for value in parts[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        return total, idle
    except Exception:
        return 0, 0


def _cpu_percent(sample_seconds: float = 0.12) -> float:
    total_a, idle_a = _read_cpu_times()
    if total_a <= 0:
        return 0.0
    time.sleep(sample_seconds)
    total_b, idle_b = _read_cpu_times()
    delta_total = total_b - total_a
    delta_idle = idle_b - idle_a
    if delta_total <= 0:
        return 0.0
    value = (1.0 - (delta_idle / delta_total)) * 100.0
    return round(max(0.0, min(100.0, value)), 1)


def _memory_stats() -> dict:
    data: dict[str, int] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, raw = line.split(":", 1)
                value = int(raw.strip().split()[0]) * 1024
                data[key] = value
    except Exception:
        pass

    total = data.get("MemTotal", 0)
    available = data.get("MemAvailable", data.get("MemFree", 0))
    used = max(total - available, 0)
    percent = round((used / total * 100.0), 1) if total else 0.0
    return {"total_bytes": total, "used_bytes": used, "available_bytes": available, "percent": percent}


def _network_totals() -> dict:
    rx = 0
    tx = 0
    try:
        with open("/proc/net/dev", "r", encoding="utf-8") as handle:
            for line in handle.readlines()[2:]:
                name, raw = line.split(":", 1)
                iface = name.strip()
                if iface == "lo":
                    continue
                fields = raw.split()
                rx += int(fields[0])
                tx += int(fields[8])
    except Exception:
        pass
    return {"rx_bytes": rx, "tx_bytes": tx}


def _uptime_seconds() -> int:
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as handle:
            return int(float(handle.read().split()[0]))
    except Exception:
        return 0



def _network_rate(sample_seconds: float = 0.18) -> dict:
    first = _network_totals()
    started = time.monotonic()
    time.sleep(sample_seconds)
    second = _network_totals()
    elapsed = max(time.monotonic() - started, 0.001)
    rx_bps = max(0.0, (second["rx_bytes"] - first["rx_bytes"]) / elapsed)
    tx_bps = max(0.0, (second["tx_bytes"] - first["tx_bytes"]) / elapsed)
    return {
        "rx_bps": round(rx_bps, 2),
        "tx_bps": round(tx_bps, 2),
        "rx_mbps": round((rx_bps * 8.0) / 1_000_000.0, 3),
        "tx_mbps": round((tx_bps * 8.0) / 1_000_000.0, 3),
    }


def _tcp_listening(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _unit_exists(unit: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "show", unit, "--property=LoadState", "--value"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() not in {"", "not-found"}
    except Exception:
        return False


def _unit_active(unit: str) -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        return result.stdout.strip() == "active"
    except Exception:
        return False


def _database_health() -> bool:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _connection_count() -> int:
    try:
        result = subprocess.run(
            ["ss", "-Htan", "state", "established"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        return sum(1 for line in result.stdout.splitlines() if line.strip()) if result.returncode == 0 else 0
    except Exception:
        return 0



CORE_PROTOCOLS = {
    "cisco": {
        "name": "Cisco / OpenConnect",
        "units": ["ocserv.service"],
        "ports": [{"port": 4443, "transport": "tcp"}, {"port": 4443, "transport": "udp"}],
    },
    "openvpn": {
        "name": "OpenVPN",
        "units": ["openvpn-server@twinpanel.service"],
        "ports": [{"port": 1194, "transport": "tcp"}],
    },
    "wireguard": {
        "name": "WireGuard",
        "units": ["wg-quick@wg-core0.service"],
        "ports": [{"port": 51820, "transport": "udp"}],
    },
    "l2tp": {
        "name": "L2TP / IPsec",
        "units": ["strongswan-starter.service", "xl2tpd.service"],
        "ports": [
            {"port": 500, "transport": "udp"},
            {"port": 4500, "transport": "udp"},
            {"port": 1701, "transport": "udp"},
        ],
    },
    "v2ray": {
        "name": "V2Ray / Xray",
        "units": ["xray.service"],
        "ports": [{"port": 8443, "transport": "tcp"}],
    },
}


def _listener_exists(port: int, transport: str) -> bool:
    try:
        args = ["ss", "-H", "-lnt"] if transport == "tcp" else ["ss", "-H", "-lnu"]
        result = subprocess.run(args, capture_output=True, text=True, timeout=2, check=False)
        token = f":{port}"
        return result.returncode == 0 and any(token in line for line in result.stdout.splitlines())
    except Exception:
        return False


def _core_protocol_status(key: str) -> dict:
    spec = CORE_PROTOCOLS[key]
    unit_states = {unit: _unit_active(unit) for unit in spec["units"]}
    installed = any(_unit_exists(unit) for unit in spec["units"])
    listeners = {
        f'{item["port"]}/{item["transport"]}': _listener_exists(item["port"], item["transport"])
        for item in spec["ports"]
    }
    units_ok = installed and all(unit_states.values())
    listeners_ok = all(listeners.values())
    return {
        "protocol": key,
        "name": spec["name"],
        "installed": installed,
        "ok": units_ok and listeners_ok,
        "service": "active" if units_ok else ("inactive" if installed else "not_installed"),
        "units": unit_states,
        "listeners": listeners,
        "port_text": "/".join(str(item["port"]) for item in spec["ports"]),
        "transport": "+".join(sorted(set(item["transport"] for item in spec["ports"]))),
    }


@router.get("/core-protocols")
def core_protocols():
    protocols = {key: _core_protocol_status(key) for key in CORE_PROTOCOLS}
    return {
        "ok": all(item["ok"] for item in protocols.values()),
        "protocols": protocols,
    }


@router.post("/core-protocols/{protocol}/restart")
def restart_core_protocol(protocol: str):
    key = protocol.lower().strip()
    if key not in CORE_PROTOCOLS:
        raise HTTPException(status_code=404, detail="Unknown protocol")
    before = _core_protocol_status(key)
    if not before["installed"]:
        raise HTTPException(status_code=409, detail=f'{before["name"]} is not installed on the controller')

    errors = []
    for unit in CORE_PROTOCOLS[key]["units"]:
        try:
            result = subprocess.run(
                ["systemctl", "restart", unit],
                capture_output=True, text=True, timeout=25, check=False,
            )
            if result.returncode != 0:
                errors.append(f"{unit}: {(result.stderr or result.stdout).strip()}")
        except Exception as exc:
            errors.append(f"{unit}: {exc}")

    time.sleep(0.7)
    status = _core_protocol_status(key)
    if errors or not status["ok"]:
        raise HTTPException(
            status_code=500,
            detail={"message": "Protocol restart did not become healthy", "errors": errors, "status": status},
        )
    return {"ok": True, "protocol": status, "message": f'{status["name"]} restarted successfully'}


@router.post("/core-protocols/restart-all")
def restart_all_core_protocols():
    results = {}
    for key in CORE_PROTOCOLS:
        status = _core_protocol_status(key)
        if not status["installed"]:
            results[key] = {"ok": False, "skipped": True, "reason": "not_installed", "status": status}
            continue
        errors = []
        for unit in CORE_PROTOCOLS[key]["units"]:
            try:
                result = subprocess.run(
                    ["systemctl", "restart", unit],
                    capture_output=True, text=True, timeout=25, check=False,
                )
                if result.returncode != 0:
                    errors.append(f"{unit}: {(result.stderr or result.stdout).strip()}")
            except Exception as exc:
                errors.append(f"{unit}: {exc}")
        time.sleep(0.7)
        current = _core_protocol_status(key)
        results[key] = {"ok": current["ok"] and not errors, "errors": errors, "status": current}
    return {"ok": all(value.get("ok", False) for value in results.values()), "results": results}


@router.get("/system-health")
def system_health():
    """Live resource usage of the TwinPanel control/API host."""
    cpu = _cpu_percent()
    memory = _memory_stats()
    disk_usage = shutil.disk_usage("/")
    disk_percent = round((disk_usage.used / disk_usage.total * 100.0), 1) if disk_usage.total else 0.0
    try:
        load_1, load_5, load_15 = os.getloadavg()
    except (AttributeError, OSError):
        load_1 = load_5 = load_15 = 0.0

    cpu_count = os.cpu_count() or 1
    network = _network_totals()
    network_rate = _network_rate()

    pressure = max(
        cpu,
        memory["percent"],
        disk_percent,
        min(100.0, (load_1 / cpu_count) * 100.0),
    )
    state = "healthy"
    if pressure >= 90:
        state = "critical"
    elif pressure >= 75:
        state = "warning"

    agent_units = ["twinpanel-agent.service", "twinpanel-agent.service"]
    agent_unit = next((unit for unit in agent_units if _unit_exists(unit)), None)
    services = {
        # Reaching this endpoint already proves the API process is serving requests.
        "api": {"state": "active", "detail": "FastAPI responding"},
        # Validate Nginx by the local listeners that actually front the service.
        "nginx": {
            "state": "active" if (_tcp_listening("127.0.0.1", 80) or _tcp_listening("127.0.0.1", 443)) else "down",
            "detail": "listener 80/443",
        },
        "database": {
            "state": "active" if _database_health() else "down",
            "detail": "SELECT 1",
        },
        "node_agent": {
            "state": ("active" if _unit_active(agent_unit) else "down") if agent_unit else "not_installed",
            "detail": agent_unit or "not installed on controller",
        },
    }
    active_connections = _connection_count()

    return {
        "ok": True,
        "hostname": socket.gethostname(),
        "state": state,
        "cpu": {
            "percent": cpu,
            "cores": cpu_count,
            "load_1": round(load_1, 2),
            "load_5": round(load_5, 2),
            "load_15": round(load_15, 2),
        },
        "memory": memory,
        "disk": {
            "total_bytes": disk_usage.total,
            "used_bytes": disk_usage.used,
            "free_bytes": disk_usage.free,
            "percent": disk_percent,
        },
        "network": {**network, **network_rate},
        "services": services,
        "active_connections": active_connections,
        "uptime_seconds": _uptime_seconds(),
        "timestamp": int(time.time()),
    }


@router.post("/users", response_model=UserOut)
def create_user(
    payload: AdminUserCreateIn,
    db: Session = Depends(get_db),
):
    email = str(payload.email).lower().strip() if payload.email else ""
    phone = (payload.phone or "").strip()

    # Normalize mobile number.
    phone = (
        phone.replace(" ", "")
             .replace("-", "")
             .replace("(", "")
             .replace(")", "")
    )

    if not email and not phone:
        raise HTTPException(
            status_code=422,
            detail="ایمیل یا شماره موبایل الزامی است",
        )

    if email:
        duplicate_email = (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

        if duplicate_email:
            raise HTTPException(
                status_code=409,
                detail="این ایمیل قبلاً ثبت شده است",
            )

    if phone:
        duplicate_phone = (
            db.query(User)
            .filter(User.phone == phone)
            .first()
        )

        if duplicate_phone:
            raise HTTPException(
                status_code=409,
                detail="این شماره موبایل قبلاً ثبت شده است",
            )

    # email is still NOT NULL in the old database.
    # Keep backward compatibility with a private internal address
    # for phone-only accounts.
    if not email:
        import secrets

        email = (
            "phone-"
            + secrets.token_hex(8)
            + "@internal.twinpanel.invalid"
        )

    user = User(
        email=email,
        phone=phone or None,
        full_name=(payload.full_name or "").strip() or None,
        password_hash=hash_password(payload.password),
        is_active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Hide internal generated email from the admin response.
    if user.email.endswith("@internal.twinpanel.invalid"):
        user.email = None

    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: AdminUserUpdateIn,
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="کاربر پیدا نشد",
        )

    if payload.email is not None:

        email = str(payload.email).lower().strip()

        duplicate = (
            db.query(User)
            .filter(
                User.email == email,
                User.id != user_id,
            )
            .first()
        )

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="این ایمیل متعلق به کاربر دیگری است",
            )

        user.email = email

    if payload.phone is not None:

        phone = (
            payload.phone.strip()
            .replace(" ", "")
            .replace("-", "")
            .replace("(", "")
            .replace(")", "")
        )

        duplicate = (
            db.query(User)
            .filter(
                User.phone == phone,
                User.id != user_id,
            )
            .first()
        )

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="این شماره موبایل متعلق به کاربر دیگری است",
            )

        user.phone = phone or None

    if payload.full_name is not None:
        user.full_name = (
            payload.full_name.strip()
            or None
        )

    db.commit()
    db.refresh(user)

    if (
        user.email
        and
        user.email.endswith(
            "@internal.twinpanel.invalid"
        )
    ):
        user.email = None

    return user


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)

    if not user:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")

    if getattr(user.role, "value", user.role) == "admin":
        raise HTTPException(
            status_code=409,
            detail="حساب مدیر از این بخش قابل حذف نیست",
        )

    email = user.email

    db.delete(user)
    db.commit()

    return {
        "ok": True,
        "user_id": user_id,
        "email": email,
    }



# TWINPANEL_USERS_SERVER_PAGINATION_V1
@router.get("/users-page")
def users_page(
    limit: int = 24,
    offset: int = 0,
    q: str = "",
    status: str = "all",
    db: Session = Depends(get_db),
):
    """
    Server-side paginated users list for admin panel.

    status:
      all
      active
      inactive
      subscribed
    """

    limit = max(1, min(int(limit or 24), 100))
    offset = max(0, int(offset or 0))
    q = (q or "").strip()

    if status not in {
        "all",
        "active",
        "inactive",
        "subscribed",
    }:
        raise HTTPException(
            status_code=400,
            detail="فیلتر کاربران نامعتبر است",
        )

    sub_stats = (
        db.query(
            Subscription.user_id.label("user_id"),

            func.count(
                Subscription.id
            ).label("subscription_count"),

            func.sum(
                case(
                    (
                        Subscription.status
                        == SubscriptionStatus.ACTIVE,
                        1,
                    ),
                    else_=0,
                )
            ).label("active_count"),

            func.sum(
                case(
                    (
                        Subscription.status
                        == SubscriptionStatus.SUSPENDED,
                        1,
                    ),
                    else_=0,
                )
            ).label("suspended_count"),

            func.sum(
                case(
                    (
                        Subscription.status
                        == SubscriptionStatus.EXPIRED,
                        1,
                    ),
                    else_=0,
                )
            ).label("expired_count"),

            func.coalesce(
                func.sum(
                    Subscription.traffic_used_bytes
                ),
                0,
            ).label("used_bytes"),

            func.coalesce(
                func.sum(
                    Subscription.traffic_limit_bytes
                ),
                0,
            ).label("limit_bytes"),
        )
        .group_by(
            Subscription.user_id
        )
        .subquery()
    )

    query = (
        db.query(
            User,
            sub_stats.c.subscription_count,
            sub_stats.c.active_count,
            sub_stats.c.suspended_count,
            sub_stats.c.expired_count,
            sub_stats.c.used_bytes,
            sub_stats.c.limit_bytes,
        )
        .outerjoin(
            sub_stats,
            sub_stats.c.user_id == User.id,
        )
    )

    # Database-side search
    if q:
        pattern = f"%{q}%"

        search_filters = [
            User.full_name.ilike(pattern),
            User.email.ilike(pattern),
            User.phone.ilike(pattern),
        ]

        if q.isdigit():
            search_filters.append(
                User.id == int(q)
            )

        query = query.filter(
            or_(*search_filters)
        )

    # Database-side status filter
    if status == "active":
        query = query.filter(
            User.is_active.is_(True)
        )

    elif status == "inactive":
        query = query.filter(
            User.is_active.is_(False)
        )

    elif status == "subscribed":
        query = query.filter(
            func.coalesce(
                sub_stats.c.subscription_count,
                0,
            ) > 0
        )

    # Count after search/filter, before limit/offset
    filtered_total = query.count()

    rows = (
        query
        .order_by(User.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = []

    for (
        user,
        subscription_count,
        active_count,
        suspended_count,
        expired_count,
        used_bytes,
        limit_bytes,
    ) in rows:

        subscription_count = int(
            subscription_count or 0
        )

        active_count = int(
            active_count or 0
        )

        suspended_count = int(
            suspended_count or 0
        )

        expired_count = int(
            expired_count or 0
        )

        used_bytes = int(
            used_bytes or 0
        )

        limit_bytes = int(
            limit_bytes or 0
        )

        items.append(
            {
                "id": user.id,

                "email": (
                    None
                    if (
                        user.email
                        and user.email.endswith(
                            "@internal.twinpanel.invalid"
                        )
                    )
                    else user.email
                ),

                "phone": user.phone,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at,

                "subscription_count":
                    subscription_count,

                "active_count":
                    active_count,

                "suspended_count":
                    suspended_count,

                "expired_count":
                    expired_count,

                "used_bytes":
                    used_bytes,

                "limit_bytes":
                    limit_bytes,

                "remaining_bytes":
                    max(
                        0,
                        limit_bytes-used_bytes,
                    ),
            }
        )

    # Global counters for the four cards.
    total_users = (
        db.query(
            func.count(User.id)
        ).scalar()
        or 0
    )

    active_users = (
        db.query(
            func.count(User.id)
        )
        .filter(
            User.is_active.is_(True)
        )
        .scalar()
        or 0
    )

    inactive_users = (
        db.query(
            func.count(User.id)
        )
        .filter(
            User.is_active.is_(False)
        )
        .scalar()
        or 0
    )

    subscribed_users = (
        db.query(
            func.count(
                func.distinct(
                    Subscription.user_id
                )
            )
        ).scalar()
        or 0
    )

    return {
        "items": items,
        "total": int(filtered_total),
        "limit": limit,
        "offset": offset,

        "summary": {
            "total_users":
                int(total_users),

            "active_users":
                int(active_users),

            "inactive_users":
                int(inactive_users),

            "subscribed_users":
                int(subscribed_users),
        },
    }


@router.get("/users", response_model=list[UserOut])
def users(db: Session = Depends(get_db)):
    rows = (
        db.query(User)
        .order_by(User.id.desc())
        .all()
    )

    result = []

    for user in rows:

        result.append(
            {
                "id": user.id,
                "email": (
                    None
                    if (
                        user.email
                        and
                        user.email.endswith(
                            "@internal.twinpanel.invalid"
                        )
                    )
                    else user.email
                ),
                "phone": user.phone,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at,
            }
        )

    return result


@router.post("/users/{user_id}/toggle-active")
def toggle_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")

    user.is_active = not user.is_active
    db.commit()
    return {"ok": True, "is_active": user.is_active}


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    payload: AdminPasswordResetIn,
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}


# ============================================================



# ============================================================



# ============================================================

# ============================================================
# VPNShop ADMIN DASHBOARD SUMMARY V2
# ============================================================

@router.get(
    "/dashboard-summary",
    dependencies=[Depends(require_admin)],
)
def dashboard_summary_v2(
    db: Session = Depends(get_db),
):
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo

    from ..models import (
        Node,
        NodeStatus,
        NodeType,
        Subscription,
        User,
        UserRole,
    )

    # ------------------------------
    # Time boundaries - Tehran
    # ------------------------------

    tehran = ZoneInfo("Asia/Tehran")

    now_local = datetime.now(tehran)

    today_local = now_local.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    # Saturday = start of Persian business week
    week_local = today_local - timedelta(
        days=(now_local.weekday() - 5) % 7
    )

    month_local = today_local.replace(day=1)

    def to_utc_naive(value):
        return (
            value
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )

    today_utc = to_utc_naive(today_local)
    week_utc = to_utc_naive(week_local)
    month_utc = to_utc_naive(month_local)


    # ------------------------------
    # Main counters
    # ------------------------------

    total_users = (
        db.query(User)
        .filter(User.role == UserRole.USER)
        .count()
    )

    total_accounts = (
        db.query(Subscription)
        .count()
    )


    # ------------------------------
    # Online nodes/users
    # ------------------------------

    online_nodes = (
        db.query(Node).filter(Node.retired_at.is_(None))
        .filter(Node.status == NodeStatus.ONLINE)
        .all()
    )

    # برای جلوگیری از دوبار شمردن کاربر
    # ابتدا نودهای ورودی ایران ملاک هستند.
    iran_online = [
        node
        for node in online_nodes
        if node.node_type == NodeType.IRAN
    ]

    user_source = (
        iran_online
        if iran_online
        else online_nodes
    )

    online_users = sum(
        int(node.current_users or 0)
        for node in user_source
    )


    # ------------------------------
    # Sales counters
    # ------------------------------

    def count_sales(start_at):
        return (
            db.query(Subscription)
            .filter(
                Subscription.starts_at.isnot(None),
                Subscription.starts_at >= start_at,
            )
            .count()
        )

    sales_today = count_sales(today_utc)
    sales_week = count_sales(week_utc)
    sales_month = count_sales(month_utc)


    # ------------------------------
    # Protocol availability
    # ------------------------------

    protocol_fields = {
        "cisco": "enable_cisco",
        "openvpn": "enable_openvpn",
        "wireguard": "enable_wireguard",
        "l2tp": "enable_l2tp",
        "v2ray": "enable_v2ray",
    }

    protocol_status = {}

    for name, field in protocol_fields.items():

        count = sum(
            1
            for node in online_nodes
            if bool(getattr(node, field, False))
        )

        protocol_status[name] = {
            "online": count > 0,
            "online_nodes": count,
        }


    # TWINPANEL_MONTHLY_USAGE_V85
    month_now = datetime.utcnow()

    month_start = month_now.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    monthly_usage_bytes = int(
        db.query(
            func.coalesce(
                func.sum(
                    QuotaUsageEvent.billable_bytes
                ),
                0,
            )
        )
        .filter(
            QuotaUsageEvent.reported_at >= month_start,
            QuotaUsageEvent.reported_at <= month_now,
        )
        .scalar()
        or 0
    )


    return {
        "monthly_usage_bytes": monthly_usage_bytes,
        "online_users": online_users,
        "total_users": total_users,
        "total_accounts": total_accounts,

        "sales_today": sales_today,
        "sales_week": sales_week,
        "sales_month": sales_month,

        "online_nodes": len(online_nodes),
        "total_nodes": db.query(Node).filter(Node.retired_at.is_(None)).count(),

        "protocols": protocol_status,

        "generated_at":
            datetime.utcnow().isoformat() + "Z",
    }


# END VPNShop ADMIN DASHBOARD SUMMARY V2

# TWINPANEL_SECURITY_CENTER_V1
@router.get("/security/overview")
def security_overview(
    db: Session = Depends(get_db),
):
    """
    Real security/abuse overview based only on
    existing quota device/session/usage telemetry.

    No synthetic counters and no automatic suspension.
    """

    from collections import defaultdict
    from datetime import datetime, timedelta

    from ..models import (
        Plan,
        Subscription,
        User,
    )
    from ..quota_models import (
        QuotaDevice,
        QuotaSession,
        QuotaUsageEvent,
    )

    now = datetime.utcnow()
    since_24h = now - timedelta(hours=24)

    def enum_value(value):
        if value is None:
            return ""
        return str(
            getattr(value, "value", value)
        ).lower()

    def first_attr(
        obj,
        names,
        default=None,
    ):
        for name in names:
            if hasattr(obj, name):
                value = getattr(obj, name)
                if value is not None:
                    return value
        return default

    def model_attr(
        model,
        names,
    ):
        for name in names:
            if hasattr(model, name):
                return getattr(model, name)
        return None

    def dt_value(obj):
        value = first_attr(
            obj,
            (
                "reported_at",
                "opened_at",
                "started_at",
                "created_at",
                "updated_at",
                "last_seen_at",
            ),
        )
        return value if isinstance(
            value,
            datetime,
        ) else None

    # -----------------------------------------------------
    # Load central subscription / user / plan data.
    # -----------------------------------------------------

    subscriptions = (
        db.query(Subscription)
        .all()
    )

    user_ids = {
        int(row.user_id)
        for row in subscriptions
        if row.user_id is not None
    }

    plan_ids = {
        int(row.plan_id)
        for row in subscriptions
        if row.plan_id is not None
    }

    users = {
        int(row.id): row
        for row in (
            db.query(User)
            .filter(User.id.in_(user_ids))
            .all()
            if user_ids
            else []
        )
    }

    plans = {
        int(row.id): row
        for row in (
            db.query(Plan)
            .filter(Plan.id.in_(plan_ids))
            .all()
            if plan_ids
            else []
        )
    }

    # -----------------------------------------------------
    # Load telemetry. Attribute selection is defensive so
    # the endpoint follows the installed quota schema.
    # -----------------------------------------------------

    session_time_attr = model_attr(
        QuotaSession,
        (
            "opened_at",
            "started_at",
            "created_at",
            "updated_at",
        ),
    )

    session_query = db.query(
        QuotaSession
    )

    if session_time_attr is not None:
        session_query = (
            session_query
            .filter(
                session_time_attr >= since_24h
            )
        )

    sessions = (
        session_query
        .order_by(
            QuotaSession.id.desc()
        )
        .limit(20000)
        .all()
    )

    devices = (
        db.query(QuotaDevice)
        .order_by(
            QuotaDevice.id.desc()
        )
        .limit(20000)
        .all()
    )

    usage_time_attr = model_attr(
        QuotaUsageEvent,
        (
            "reported_at",
            "created_at",
            "occurred_at",
        ),
    )

    usage_query = db.query(
        QuotaUsageEvent
    )

    if usage_time_attr is not None:
        usage_query = (
            usage_query
            .filter(
                usage_time_attr >= since_24h
            )
        )

    usage_events = (
        usage_query
        .order_by(
            QuotaUsageEvent.id.desc()
        )
        .limit(30000)
        .all()
    )

    # -----------------------------------------------------
    # Device -> subscription map.
    # -----------------------------------------------------

    device_by_id = {
        int(row.id): row
        for row in devices
        if getattr(row, "id", None)
        is not None
    }

    device_subscription = {}

    for device in devices:
        subscription_id = first_attr(
            device,
            (
                "subscription_id",
                "sub_id",
            ),
        )

        if (
            subscription_id is not None
            and getattr(
                device,
                "id",
                None,
            ) is not None
        ):
            device_subscription[
                int(device.id)
            ] = int(subscription_id)

    def telemetry_subscription_id(row):
        subscription_id = first_attr(
            row,
            (
                "subscription_id",
                "sub_id",
            ),
        )

        if subscription_id is not None:
            try:
                return int(subscription_id)
            except Exception:
                return None

        device_id = first_attr(
            row,
            ("device_id",),
        )

        if device_id is not None:
            try:
                return device_subscription.get(
                    int(device_id)
                )
            except Exception:
                return None

        return None

    # -----------------------------------------------------
    # Aggregate session telemetry.
    # -----------------------------------------------------

    session_stats = defaultdict(
        lambda: {
            "active_sessions": 0,
            "active_devices": set(),
            "recent_devices": set(),
            "recent_ips": set(),
            "last_activity_at": None,
        }
    )

    total_open_sessions = 0

    for session in sessions:
        subscription_id = (
            telemetry_subscription_id(
                session
            )
        )

        if not subscription_id:
            continue

        bucket = session_stats[
            subscription_id
        ]

        device_id = first_attr(
            session,
            ("device_id",),
        )

        if device_id is not None:
            try:
                bucket[
                    "recent_devices"
                ].add(int(device_id))
            except Exception:
                pass

        client_ip = first_attr(
            session,
            (
                "client_ip",
                "remote_ip",
                "ip_address",
            ),
        )

        if client_ip:
            bucket[
                "recent_ips"
            ].add(str(client_ip))

        activity = dt_value(session)

        if (
            activity is not None
            and (
                bucket["last_activity_at"]
                is None
                or activity
                > bucket[
                    "last_activity_at"
                ]
            )
        ):
            bucket[
                "last_activity_at"
            ] = activity

        status = enum_value(
            first_attr(
                session,
                ("status",),
            )
        )

        closed_at = first_attr(
            session,
            (
                "closed_at",
                "ended_at",
                "disconnected_at",
            ),
        )
        is_open = (
            status in {
                "open",
                "active",
                "online",
                "connected",
            }
            or (
                not status
                and closed_at is None
            )
        )

        if is_open:
            bucket[
                "active_sessions"
            ] += 1

            total_open_sessions += 1

            if device_id is not None:
                try:
                    bucket[
                        "active_devices"
                    ].add(int(device_id))
                except Exception:
                    pass

    # -----------------------------------------------------
    # Aggregate 24h usage.
    # -----------------------------------------------------

    usage_24h = defaultdict(int)

    for event in usage_events:
        subscription_id = (
            telemetry_subscription_id(
                event
            )
        )

        if not subscription_id:
            continue

        value = first_attr(
            event,
            (
                "billable_bytes",
                "usage_bytes",
                "bytes_used",
                "bytes",
            ),
            0,
        )

        try:
            usage_24h[
                subscription_id
            ] += max(0, int(value or 0))
        except Exception:
            pass

    # -----------------------------------------------------
    # Calculate measurable risk.
    # -----------------------------------------------------

    rows = []

    high_count = 0
    medium_count = 0
    normal_count = 0
    telemetry_count = 0

    for sub in subscriptions:
        sid = int(sub.id)

        user = users.get(
            int(sub.user_id)
        )

        # Manual/legacy subscriptions may not have a backing plan.
        # Missing plan metadata falls back to the conservative default below.
        plan = (
            plans.get(int(sub.plan_id))
            if sub.plan_id is not None
            else None
        )

        stats = session_stats[sid]

        device_limit = max(
            1,
            int(
                getattr(
                    plan,
                    "device_limit",
                    1,
                )
                or 1
            ),
        )

        active_sessions = int(
            stats["active_sessions"]
        )

        active_devices = len(
            stats["active_devices"]
        )

        recent_devices = len(
            stats["recent_devices"]
        )

        recent_ips = len(
            stats["recent_ips"]
        )

        usage_bytes = int(
            usage_24h.get(sid, 0)
        )

        has_telemetry = bool(
            active_sessions
            or recent_devices
            or recent_ips
            or usage_bytes
        )

        if has_telemetry:
            telemetry_count += 1

        score = 0
        reasons = []

        # Hard rule:
        # simultaneous active devices exceed plan limit.
        if active_devices > device_limit:
            score += 70
            reasons.append(
                "تعداد دستگاه فعال هم‌زمان "
                f"({active_devices}) بیشتر از سقف پلن "
                f"({device_limit}) است."
            )

        # 24h device churn.
        if (
            recent_devices
            > max(
                device_limit + 1,
                device_limit * 2,
            )
        ):
            score += 25
            reasons.append(
                "تعداد دستگاه‌های متفاوت در ۲۴ ساعت "
                f"({recent_devices}) غیرعادی است."
            )

        # IP churn uses a deliberately generous threshold
        # to reduce false positives on mobile networks.
        ip_threshold = max(
            6,
            device_limit * 4,
        )

        if recent_ips > ip_threshold:
            score += 20
            reasons.append(
                "تعداد IPهای متفاوت در ۲۴ ساعت "
                f"({recent_ips}) از آستانه "
                f"({ip_threshold}) عبور کرده است."
            )

        score = min(score, 100)

        if score >= 60:
            risk_level = "high"
            high_count += 1
        elif score >= 20:
            risk_level = "medium"
            medium_count += 1
        else:
            risk_level = "normal"
            normal_count += 1

        last_activity = stats[
            "last_activity_at"
        ]

        rows.append(
            {
                "subscription_id": sid,
                "user_id": int(
                    sub.user_id
                ),
                "user_name": (
                    getattr(
                        user,
                        "full_name",
                        None,
                    )
                    or getattr(
                        user,
                        "email",
                        None,
                    )
                    or f"User #{sub.user_id}"
                ),
                "email": (
                    getattr(
                        user,
                        "email",
                        "",
                    )
                    or ""
                ),
                "plan_name": (
                    getattr(
                        plan,
                        "name",
                        "",
                    )
                    or ""
                ),
                "status": enum_value(
                    sub.status
                ),
                "device_limit": device_limit,
                "active_sessions": active_sessions,
                "active_devices": active_devices,
                "recent_devices_24h": recent_devices,
                "recent_ips_24h": recent_ips,
                "recent_ips": sorted(
                    stats["recent_ips"]
                )[:12],
                "usage_24h_bytes": usage_bytes,
                "traffic_used_bytes": int(
                    getattr(
                        sub,
                        "traffic_used_bytes",
                        0,
                    )
                    or 0
                ),
                "traffic_limit_bytes": int(
                    getattr(
                        sub,
                        "traffic_limit_bytes",
                        0,
                    )
                    or 0
                ),
                "risk_score": score,
                "risk_level": risk_level,
                "reasons": reasons,
                "has_telemetry": has_telemetry,
                "last_activity_at": (
                    last_activity.isoformat()
                    if isinstance(
                        last_activity,
                        datetime,
                    )
                    else None
                ),
            }
        )

    risk_order = {
        "high": 0,
        "medium": 1,
        "normal": 2,
    }

    rows.sort(
        key=lambda row: (
            risk_order.get(
                row["risk_level"],
                9,
            ),
            -int(row["risk_score"]),
            -int(row["active_devices"]),
            -int(row["recent_ips_24h"]),
        )
    )

    return {
        "generated_at": now.isoformat(),
        "window_hours": 24,
        "summary": {
            "subscriptions": len(
                subscriptions
            ),
            "with_telemetry": telemetry_count,
            "high_risk": high_count,
            "medium_risk": medium_count,
            "normal": normal_count,
            "open_sessions": total_open_sessions,
        },
        "rules": {
            "device_limit":
                "دستگاه فعال هم‌زمان بیشتر از سقف پلن",
            "device_churn":
                "دستگاه‌های متفاوت زیاد در ۲۴ ساعت",
            "ip_churn":
                "IPهای متفاوت زیاد در ۲۴ ساعت",
            "automatic_suspend": False,
        },
        "items": rows[:500],
    }

