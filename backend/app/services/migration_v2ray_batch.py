from __future__ import annotations

import base64
import json
import shlex
from typing import Any

from sqlalchemy.orm import Session

from ..models import Node, NodeType, ProtocolCredential, Subscription, User
from ..routers.provision import cmd, ssh_connect_saved


# TWINPANEL_MIGRATION_V2RAY_BATCH_PROVISION_V2
#
# Migration imports can contain thousands of V2Ray accounts. Provisioning each
# account through the normal single-account path would open one SSH session and
# restart Xray once per account. Besides being slow, parallelising that legacy
# read/modify/write flow would create a lost-update race on config.json.
#
# This helper keeps the canonical account shape but applies the whole migration
# batch atomically per Exit node: one SSH connection, one config rewrite and one
# Xray restart per node. Database state is loaded in bulk so large imports do not
# spend the proxy timeout budget on thousands of individual SELECT statements.


def _remote_batch_script(clients_payload: list[dict[str, str]]) -> str:
    payload_b64 = base64.b64encode(
        json.dumps(clients_payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).decode()
    return f'''import base64,json,os\np='/usr/local/etc/xray/config.json'\npayload=json.loads(base64.b64decode({payload_b64!r}).decode())\nd=json.load(open(p))\nclients=d['inbounds'][0]['settings'].setdefault('clients',[])\nemails={{item['email'] for item in payload}}\nclients[:]=[item for item in clients if item.get('email') not in emails]\nclients.extend(payload)\ntmp=p+'.twinpanel-migration.tmp'\nwith open(tmp,'w') as handle:\n    json.dump(d,handle,indent=2)\n    handle.flush()\n    os.fsync(handle.fileno())\nos.replace(tmp,p)\n'''


async def provision_migrated_v2ray_batch(
    db: Session,
    subscription_uuids: dict[int, str],
) -> dict[str, Any]:
    """Provision imported V2Ray identities with one Xray restart per Exit node."""

    from ..routers import account_delivery as ad

    if not subscription_uuids:
        return {
            "ok": True,
            "subscriptions": 0,
            "nodes": 0,
            "node_restarts": 0,
            "errors": [],
        }

    subscription_ids = sorted(int(item) for item in subscription_uuids)
    subscriptions_list = (
        db.query(Subscription)
        .filter(Subscription.id.in_(subscription_ids))
        .all()
    )
    subscriptions = {item.id: item for item in subscriptions_list}
    missing_subscriptions = [item for item in subscription_ids if item not in subscriptions]
    if missing_subscriptions:
        raise RuntimeError(
            "subscriptions not found after migration import: "
            + ",".join(str(item) for item in missing_subscriptions[:20])
        )

    user_ids = sorted({int(item.user_id) for item in subscriptions_list})
    user_list = db.query(User).filter(User.id.in_(user_ids)).all()
    users_by_id = {item.id: item for item in user_list}
    users: dict[int, User] = {}
    for subscription_id, sub in subscriptions.items():
        user = users_by_id.get(int(sub.user_id))
        if user is None:
            raise RuntimeError(f"user {sub.user_id} not found for subscription {subscription_id}")
        users[subscription_id] = user

    existing_credentials = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id.in_(subscription_ids),
            ProtocolCredential.protocol == "v2ray",
        )
        .all()
    )
    credentials_by_subscription = {
        int(item.subscription_id): item for item in existing_credentials
    }

    nodes = (
        db.query(Node)
        .filter(
            Node.node_type == NodeType.EXIT,
            Node.retired_at.is_(None),
            Node.enable_v2ray.is_(True),
        )
        .order_by(Node.id.asc())
        .all()
    )
    if not nodes:
        raise RuntimeError("no active Exit node with V2Ray enabled is available")

    items_by_subscription: dict[int, list[dict[str, Any]]] = {
        subscription_id: [] for subscription_id in subscriptions
    }
    errors: list[dict[str, str]] = []
    successful_nodes = 0

    clients_payload = [
        {
            "id": str(subscription_uuids[subscription_id]),
            "email": f"mv-{subscription_id}@twinpanel",
        }
        for subscription_id in subscription_ids
    ]
    script = _remote_batch_script(clients_payload)
    encoded_script = base64.b64encode(script.encode()).decode()

    for node in nodes:
        conn = None
        try:
            conn = await ssh_connect_saved(node, db)
            await cmd(
                conn,
                "printf '%s' "
                + shlex.quote(encoded_script)
                + " | base64 -d | python3 && systemctl restart xray",
            )
            successful_nodes += 1

            host, port = ad._tunnel_access_endpoint(db, node, "v2ray")
            country_part = ad._country_download_name(node)

            for subscription_id, sub in subscriptions.items():
                user = users[subscription_id]
                client_id = str(subscription_uuids[subscription_id])
                username_part = ad._download_filename_part(
                    sub.account_username or ad._safe_username(sub, user),
                    f"user{sub.id}",
                )
                profile_name = f"{username_part}-{country_part}"
                uri = (
                    f"vless://{client_id}@{host}:{port}"
                    f"?encryption=none&type=tcp#{profile_name}"
                )
                items_by_subscription[subscription_id].append(
                    {
                        "node_id": node.id,
                        "node": node.name,
                        "server": host,
                        "server_ip": host,
                        "port": port,
                        "uuid": client_id,
                        "uri": uri,
                    }
                )
        except Exception as exc:
            errors.append(
                {
                    "node": str(node.name),
                    "error": str(exc)[:800],
                }
            )
        finally:
            if conn is not None:
                conn.close()
                await conn.wait_closed()

    if successful_nodes == 0:
        raise RuntimeError(
            "V2Ray migration batch could not be provisioned on any Exit node: "
            + "; ".join(f"{item['node']}: {item['error']}" for item in errors)
        )

    for subscription_id, items in items_by_subscription.items():
        if not items:
            continue
        cred = credentials_by_subscription.get(subscription_id)
        if cred is None:
            cred = ProtocolCredential(
                subscription_id=subscription_id,
                protocol="v2ray",
                is_active=True,
            )
            db.add(cred)
            credentials_by_subscription[subscription_id] = cred
        cred.username = None
        cred.secret_encrypted = None
        cred.config_text_encrypted = ad._enc(items)
        cred.is_active = True

    db.commit()

    return {
        "ok": len(errors) == 0,
        "subscriptions": len(subscriptions),
        "nodes": successful_nodes,
        "node_restarts": successful_nodes,
        "errors": errors,
    }
