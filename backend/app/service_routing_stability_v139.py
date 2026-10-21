from __future__ import annotations

from . import unified_l3_agent_rollout_v49 as rollout
from .routers import provision


# ============================================================
# TWINPANEL SERVICE ROUTING STABILITY V139
#
# Production audit on Tunnel #5 proved that the Iran Node Agent rebuilt the
# managed service-routing chains every ~12 seconds. The old reconciler first
# flushed TP_DNAT / TP_SNAT / TP_FWD / TP_CISCO_MSS and then appended rules one
# by one. Half-second sampling caught live partial states (for example
# DNAT=12 -> 5 -> 12 and FWD=13 -> 6 -> 13) while the GRE carrier itself
# sustained 192/373 Mbps.
#
# V139 keeps the same desired rules and ownership boundaries, but changes only
# publication semantics:
#   1. stable desired state is read-only (no iptables mutation);
#   2. drift/real desired changes are rendered first;
#   3. each table is committed through iptables-restore --noflush instead of a
#      live flush followed by individual iptables -A calls;
#   4. the committed state is verified before reconciliation succeeds.
#
# This preserves Unified L3 V49 carrier election, ports, SNAT/DNAT policy,
# MSS=1200 policy, Exit egress, protocol services and failover behavior.
# ============================================================

AGENT_MARKER = "TWINPANEL_SERVICE_ROUTING_STABILITY_V139"

_runtime_applied = False
_original_make_agent = None


_AGENT_ROUTING_V139 = r'''# TWINPANEL_SERVICE_ROUTING_STABILITY_V139

_SERVICE_ROUTING_CHAINS = (
    ("nat", "TP_DNAT"),
    ("nat", "TP_SNAT"),
    ("nat", "TP_EGRESS"),
    ("filter", "TP_FWD"),
    ("filter", "TP_EGRESS_FWD"),
    ("mangle", "TP_CISCO_MSS"),
)

_SERVICE_ROUTING_JUMPS = (
    ("nat", "PREROUTING", "TP_DNAT"),
    ("nat", "POSTROUTING", "TP_SNAT"),
    ("nat", "POSTROUTING", "TP_EGRESS"),
    ("filter", "FORWARD", "TP_FWD"),
    ("filter", "FORWARD", "TP_EGRESS_FWD"),
    ("mangle", "FORWARD", "TP_CISCO_MSS"),
)


def _service_routing_must_ipt(table, *args):
    code, output = ipt(
        table,
        *args,
    )

    if code != 0:
        command = " ".join(
            str(x)
            for x in args
        )

        raise RuntimeError(
            (
                "iptables_failed "
                f"table={table} "
                f"args={command} "
                f"error={output}"
            )[:900]
        )

    return code, output


def _service_routing_ensure_prerequisites():
    for table, chain in _SERVICE_ROUTING_CHAINS:
        code, _ = ipt(
            table,
            "-S",
            chain,
        )

        if code != 0:
            _service_routing_must_ipt(
                table,
                "-N",
                chain,
            )

    for table, parent, child in _SERVICE_ROUTING_JUMPS:
        code, _ = ipt(
            table,
            "-C",
            parent,
            "-j",
            child,
        )

        if code != 0:
            _service_routing_must_ipt(
                table,
                "-I",
                parent,
                "1",
                "-j",
                child,
            )


def _service_routing_rule_map(items, wan_if):
    desired = {
        key: []
        for key in _SERVICE_ROUTING_CHAINS
    }

    def add(table, chain, *args):
        desired[(table, chain)].append(
            tuple(str(x) for x in args)
        )

    egress_subnets = set()

    for item in items:
        role = item.get(
            "node_role"
        )

        interface = str(
            item.get(
                "interface"
            )
            or ""
        ).strip()

        local_ip = str(
            item.get(
                "local_address",
                "",
            )
            or ""
        ).split("/")[0].strip()

        exit_ip = str(
            item.get(
                "exit_tunnel_ip"
            )
            or ""
        ).strip()

        routes = (
            item.get(
                "service_routes"
            )
            or []
        )

        if role == "iran":
            if (
                not interface
                or not local_ip
                or not exit_ip
            ):
                if routes:
                    raise RuntimeError(
                        "iran_route_metadata_missing"
                    )

                continue

            # Exit -> Iran -> Internet. Preserve V49's return-path allowance
            # even for a standby item with no published service_routes.
            add(
                "filter",
                "TP_FWD",
                "-i",
                interface,
                "-o",
                wan_if,
                "-s",
                exit_ip,
                "-m",
                "conntrack",
                "--ctstate",
                "ESTABLISHED,RELATED",
                "-j",
                "ACCEPT",
            )

            for route in routes:
                route_protocol = str(
                    route.get(
                        "protocol",
                        "",
                    )
                    or ""
                ).strip().lower()

                transport = str(
                    route.get(
                        "transport",
                        "",
                    )
                    or ""
                ).strip().lower()

                # Raw ESP / IPsec protocol 50.
                if transport == "esp":
                    add(
                        "nat",
                        "TP_DNAT",
                        "-i",
                        wan_if,
                        "-p",
                        "esp",
                        "-j",
                        "DNAT",
                        "--to-destination",
                        exit_ip,
                    )

                    add(
                        "nat",
                        "TP_SNAT",
                        "-o",
                        interface,
                        "-d",
                        exit_ip,
                        "-p",
                        "esp",
                        "-j",
                        "SNAT",
                        "--to-source",
                        local_ip,
                    )

                    add(
                        "filter",
                        "TP_FWD",
                        "-i",
                        wan_if,
                        "-o",
                        interface,
                        "-d",
                        exit_ip,
                        "-p",
                        "esp",
                        "-m",
                        "conntrack",
                        "--ctstate",
                        "NEW,ESTABLISHED,RELATED",
                        "-j",
                        "ACCEPT",
                    )

                    continue

                public_port = str(
                    int(
                        route[
                            "public_port"
                        ]
                    )
                )

                target_port = str(
                    int(
                        route[
                            "target_port"
                        ]
                    )
                )

                protocols = expand_transport(
                    transport
                )

                if not protocols:
                    raise RuntimeError(
                        (
                            "unsupported_service_transport:"
                            f"{transport}"
                        )
                    )

                for proto in protocols:
                    # Keep the existing fixed 1200 MSS contract for Cisco CSTP
                    # and Xray TCP service ingress. V139 changes publication,
                    # not packet sizing.
                    if (
                        route_protocol
                        in {
                            "cisco",
                            "v2ray",
                        }
                        and proto == "tcp"
                    ):
                        add(
                            "mangle",
                            "TP_CISCO_MSS",
                            "-o",
                            interface,
                            "-d",
                            exit_ip,
                            "-p",
                            "tcp",
                            "--dport",
                            target_port,
                            "--tcp-flags",
                            "SYN,RST",
                            "SYN",
                            "-j",
                            "TCPMSS",
                            "--set-mss",
                            "1200",
                        )

                        add(
                            "mangle",
                            "TP_CISCO_MSS",
                            "-i",
                            interface,
                            "-s",
                            exit_ip,
                            "-p",
                            "tcp",
                            "--sport",
                            target_port,
                            "--tcp-flags",
                            "SYN,RST",
                            "SYN",
                            "-j",
                            "TCPMSS",
                            "--set-mss",
                            "1200",
                        )

                    add(
                        "nat",
                        "TP_DNAT",
                        "-i",
                        wan_if,
                        "-p",
                        proto,
                        "--dport",
                        public_port,
                        "-j",
                        "DNAT",
                        "--to-destination",
                        (
                            f"{exit_ip}:"
                            f"{target_port}"
                        ),
                    )

                    add(
                        "nat",
                        "TP_SNAT",
                        "-o",
                        interface,
                        "-d",
                        exit_ip,
                        "-p",
                        proto,
                        "--dport",
                        target_port,
                        "-j",
                        "SNAT",
                        "--to-source",
                        local_ip,
                    )

                    add(
                        "filter",
                        "TP_FWD",
                        "-i",
                        wan_if,
                        "-o",
                        interface,
                        "-d",
                        exit_ip,
                        "-p",
                        proto,
                        "--dport",
                        target_port,
                        "-m",
                        "conntrack",
                        "--ctstate",
                        "NEW,ESTABLISHED,RELATED",
                        "-j",
                        "ACCEPT",
                    )

        elif role == "exit":
            for route in routes:
                subnet = route.get(
                    "client_subnet"
                )

                if subnet:
                    egress_subnets.add(
                        str(subnet)
                    )

    for subnet in sorted(
        egress_subnets
    ):
        add(
            "nat",
            "TP_EGRESS",
            "-s",
            subnet,
            "-o",
            wan_if,
            "-j",
            "MASQUERADE",
        )

        add(
            "filter",
            "TP_EGRESS_FWD",
            "-s",
            subnet,
            "-o",
            wan_if,
            "-j",
            "ACCEPT",
        )

        add(
            "filter",
            "TP_EGRESS_FWD",
            "-d",
            subnet,
            "-i",
            wan_if,
            "-m",
            "conntrack",
            "--ctstate",
            "ESTABLISHED,RELATED",
            "-j",
            "ACCEPT",
        )

    return desired


def _service_routing_matches(desired):
    # Read-only drift detection. Stable reconciliation performs no mutation,
    # so packet counters and live flows are preserved across the 12-second
    # Agent loop.
    for table, chain in _SERVICE_ROUTING_CHAINS:
        code, output = ipt(
            table,
            "-S",
            chain,
        )

        if code != 0:
            return False

        prefix = f"-A {chain} "
        current_count = sum(
            1
            for line in output.splitlines()
            if line.strip().startswith(
                prefix
            )
        )

        rules = desired[
            (table, chain)
        ]

        if current_count != len(rules):
            return False

        for args in rules:
            code, _ = ipt(
                table,
                "-C",
                chain,
                *args,
            )

            if code != 0:
                return False

    return True


def _service_routing_restore_script(desired):
    import shlex

    lines = []

    for table in (
        "nat",
        "filter",
        "mangle",
    ):
        lines.append(
            f"*{table}"
        )

        for rule_table, chain in _SERVICE_ROUTING_CHAINS:
            if rule_table != table:
                continue

            lines.append(
                f"-F {chain}"
            )

            for args in desired[
                (table, chain)
            ]:
                tokens = (
                    "-A",
                    chain,
                    *args,
                )

                lines.append(
                    " ".join(
                        shlex.quote(
                            str(token)
                        )
                        for token in tokens
                    )
                )

        lines.append(
            "COMMIT"
        )

    return "\n".join(lines) + "\n"


def _service_routing_run_restore(
    script,
    *,
    test_only,
):
    command = [
        "iptables-restore",
        "--wait",
        "5",
        "--noflush",
    ]

    if test_only:
        command.append(
            "--test"
        )

    try:
        process = subprocess.run(
            command,
            input=script,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception as exc:
        raise RuntimeError(
            (
                "iptables_restore_exec_failed:"
                f"{type(exc).__name__}:{exc}"
            )[:900]
        ) from exc

    if process.returncode != 0:
        mode = (
            "test"
            if test_only
            else "commit"
        )

        raise RuntimeError(
            (
                "iptables_restore_failed "
                f"mode={mode} "
                f"error={(process.stdout or '').strip()}"
            )[:900]
        )


def _service_routing_restore(desired):
    script = _service_routing_restore_script(
        desired
    )

    # Parse/validate the complete transaction before touching live chains.
    _service_routing_run_restore(
        script,
        test_only=True,
    )

    # --noflush retains all non-TwinPanel rules. The explicit -F commands are
    # evaluated inside iptables-restore's per-table commit, so users never see
    # the old "flush now, append rules one by one" partial chain state.
    _service_routing_run_restore(
        script,
        test_only=False,
    )


def reconcile_service_routing(items):
    try:
        return _reconcile_service_routing_strict(
            items
        )
    except Exception as exc:
        return (
            False,
            str(exc)[:900],
        )


def _reconcile_service_routing_strict(items):
    wan_if = default_interface()

    if not wan_if:
        raise RuntimeError(
            "default_interface_not_found"
        )

    _service_routing_ensure_prerequisites()

    desired = _service_routing_rule_map(
        items,
        wan_if,
    )

    if _service_routing_matches(
        desired
    ):
        return True, None

    _service_routing_restore(
        desired
    )

    if not _service_routing_matches(
        desired
    ):
        raise RuntimeError(
            "service_routing_post_commit_mismatch"
        )

    total_rules = sum(
        len(rules)
        for rules in desired.values()
    )

    print(
        "[TwinPanel] SERVICE_ROUTING_V139 COMMITTED "
        f"rules={total_rules}",
        flush=True,
    )

    return True, None
'''


def _patch_agent_source(source: str) -> str:
    if AGENT_MARKER in source:
        return source

    start_marker = "# TWINPANEL_SERVICE_ROUTING_STRICT_V2"
    end_marker = (
        "\n\n# ============================================================\n"
        "# API REPORT"
    )

    start = source.find(start_marker)
    end = source.find(
        end_marker,
        start + 1,
    )

    if (
        start < 0
        or end < 0
        or end <= start
    ):
        raise RuntimeError(
            "TwinPanel Agent service-routing contract changed; "
            "V139 stability patch refused"
        )

    patched = (
        source[:start]
        + _AGENT_ROUTING_V139.rstrip()
        + source[end:]
    )

    required = (
        AGENT_MARKER,
        "_service_routing_matches",
        "iptables-restore",
        "--noflush",
        "SERVICE_ROUTING_V139 COMMITTED",
    )

    if not all(
        token in patched
        for token in required
    ):
        raise RuntimeError(
            "Service Routing V139 Agent validation failed"
        )

    return patched


def _make_agent_v139(
    node_id: int,
    api_base: str,
) -> str:
    assert _original_make_agent is not None

    return _patch_agent_source(
        _original_make_agent(
            node_id,
            api_base,
        )
    )


def apply_service_routing_stability_v139() -> None:
    global _runtime_applied
    global _original_make_agent

    if _runtime_applied:
        return

    _original_make_agent = (
        provision.make_agent
    )

    provision.make_agent = (
        _make_agent_v139
    )

    # Unified L3 rollout must upgrade existing nodes that already carry the
    # older V79/V49 markers; otherwise the fixed renderer would only affect
    # newly installed/repaired nodes.
    rollout._AGENT_MARKER = (
        AGENT_MARKER
    )

    # Fail closed during controller startup if the current renderer no longer
    # satisfies the patch contract.
    probe = provision.make_agent(
        1,
        "https://127.0.0.1.invalid",
    )

    if AGENT_MARKER not in probe:
        raise RuntimeError(
            "Service Routing V139 rollout marker missing"
        )

    _runtime_applied = True

    print(
        "TWINPANEL_SERVICE_ROUTING_STABILITY_V139_ACTIVE "
        "steady_state_writes=0 "
        "publish=iptables_restore_noflush "
        "verify_after_commit=1 "
        "rollout_marker=v139",
        flush=True,
    )
