from __future__ import annotations

from .transport_policy_v17 import install_transport_policy_v17


# V18 keeps V17's proven modern-first health/priority logic. The change is the
# underlay: KCP/ARQ/QUIC/TCP no longer depend on Backhaul and can fan one Iran
# node out to several Exit nodes independently.
def install_transport_policy_v18() -> None:
    install_transport_policy_v17()
    print(
        "TWINPANEL_TRANSPORT_POLICY_V18_ACTIVE "
        "mode=modern-first underlay=public-direct multi_exit=1",
        flush=True,
    )
