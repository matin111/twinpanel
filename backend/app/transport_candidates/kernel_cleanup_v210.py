from __future__ import annotations

import shlex

from . import common


async def cleanup_probe_state(
    ci,
    ce,
    *,
    name: str,
    tunnel_id: int,
    rt: dict,
) -> list[str]:
    """Remove probe-owned policy/NAT state after a failed kernel canary.

    The common L3 probe intentionally creates a source policy rule/table on the
    Iran node and a narrowly scoped MASQUERADE rule on the Exit node. Kernel
    IPIP/VXLAN installers are explicit canaries, so a failed install must leave
    neither artifact behind. Cleanup is idempotent and verifies absence before
    returning; callers keep the candidate failed if any cleanup verification
    fails.
    """

    tid = int(tunnel_id)
    table, priority = common.policy_ids(name, tid)
    errors: list[str] = []

    if ci is not None:
        try:
            result = await ci.run(
                f"""
set +e
while ip rule del priority {int(priority)} 2>/dev/null; do :; done
ip route flush table {int(table)} 2>/dev/null || true

if ip rule show | grep -Eq '^{int(priority)}:'; then
  echo 'policy_rule_cleanup_failed' >&2
  exit 41
fi

if ip route show table {int(table)} 2>/dev/null | grep -q .; then
  echo 'policy_table_cleanup_failed' >&2
  exit 42
fi

exit 0
""",
                check=False,
                timeout=30,
            )
            if result.exit_status != 0:
                detail = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
                errors.append(
                    f"iran_policy_cleanup_rc={result.exit_status}:{detail[-800:]}"
                )
        except Exception as exc:
            errors.append(
                f"iran_policy_cleanup_exception={type(exc).__name__}:{exc}"
            )

    if ce is not None:
        comment = f"TwinPanel-{name}-{tid}"
        network = str(rt["network"])
        try:
            result = await ce.run(
                f"""
set +e
NETWORK={shlex.quote(network)}
COMMENT={shlex.quote(comment)}

if command -v iptables >/dev/null 2>&1; then
  while true; do
    RULE_NO="$(
      iptables -t nat -L POSTROUTING --line-numbers -n 2>/dev/null \
      | awk -v src="$NETWORK" -v c="$COMMENT" \
          'index($0, src) && index($0, c) {{print $1; exit}}'
    )"
    [ -n "$RULE_NO" ] || break
    iptables -t nat -D POSTROUTING "$RULE_NO" >/dev/null 2>&1 || break
  done

  if iptables -t nat -L POSTROUTING --line-numbers -n 2>/dev/null \
      | awk -v src="$NETWORK" -v c="$COMMENT" \
          'index($0, src) && index($0, c) {{found=1}} END {{exit found ? 0 : 1}}'; then
    echo 'canary_nat_cleanup_failed' >&2
    exit 43
  fi
fi

exit 0
""",
                check=False,
                timeout=30,
            )
            if result.exit_status != 0:
                detail = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
                errors.append(
                    f"exit_nat_cleanup_rc={result.exit_status}:{detail[-800:]}"
                )
        except Exception as exc:
            errors.append(
                f"exit_nat_cleanup_exception={type(exc).__name__}:{exc}"
            )

    return errors
