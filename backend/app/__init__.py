# TWINPANEL_XRAY_PROVISION_SCRIPT_FIX_V1
# Install narrow import-time compatibility patches before routers load.
# These keep the production account-delivery API contract unchanged while
# refining only the affected Xray runtime composition.
from .xray_provision_patch import install as _install_xray_provision_patch
from .xray_grpc_target_isolation_v48 import (
    install as _install_xray_grpc_target_isolation_v48,
)

_install_xray_provision_patch()
_install_xray_grpc_target_isolation_v48()
