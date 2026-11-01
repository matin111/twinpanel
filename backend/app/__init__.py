# TWINPANEL_XRAY_PROVISION_SCRIPT_FIX_V1
# Install narrow import-time compatibility patches before routers load.
# These keep the production account-delivery API contract unchanged while
# refining only the affected Xray runtime composition.
from .xray_provision_patch import install as _install_xray_provision_patch
from .xray_grpc_target_isolation_v48 import (
    install as _install_xray_grpc_target_isolation_v48,
)
from .xray_duplicate_email_repair_v1 import (
    install as _install_xray_duplicate_email_repair_v1,
)
from .v2ray_provision_idempotency_v1 import (
    install as _install_v2ray_provision_idempotency_v1,
)
from .reseller_order_partial_provision_success_v1 import (
    install as _install_reseller_order_partial_provision_success_v1,
)
from .convergence_event_loop_isolation_v1 import (
    install as _install_convergence_event_loop_isolation_v1,
)
from .convergence_process_isolation_v2 import (
    install as _install_convergence_process_isolation_v2,
)

_install_xray_provision_patch()
_install_xray_grpc_target_isolation_v48()
_install_xray_duplicate_email_repair_v1()
_install_v2ray_provision_idempotency_v1()
_install_reseller_order_partial_provision_success_v1()
_install_convergence_event_loop_isolation_v1()
_install_convergence_process_isolation_v2()
