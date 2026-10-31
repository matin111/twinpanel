# TWINPANEL_XRAY_PROVISION_SCRIPT_FIX_V1
# Install the narrow import-time compatibility patch before routers load.
# This keeps the production account-delivery API contract unchanged while
# replacing only the broken generated Xray mutation script.
from .xray_provision_patch import install as _install_xray_provision_patch

_install_xray_provision_patch()
