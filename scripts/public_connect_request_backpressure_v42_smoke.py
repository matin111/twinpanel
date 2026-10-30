from app.routers.public_connection_final_presentation_v37 import _SCRIPT as V37_SCRIPT
from app.routers.public_connection_forward_v34 import _SCRIPT as V34_SCRIPT
from app.routers.public_connection_hub_live_v5 import _LIVE_SCRIPT
from app.routers.public_connection_request_backpressure_v42 import (
    refine_public_connection_request_backpressure_v42,
)


source = "<html><body>" + _LIVE_SCRIPT + V34_SCRIPT + V37_SCRIPT + "</body></html>"
result = refine_public_connection_request_backpressure_v42(source)

assert "TWINPANEL_PUBLIC_CONNECT_REQUEST_BACKPRESSURE_V42" in result

# Initial render must not fan out into subscription or multi-meta network reads.
assert "fetch(url,{cache:'no-store',headers:{Accept:'text/plain'}})" not in result
assert "fetch(url+'/meta',{cache:'no-store',headers:{Accept:'application/json'}})" not in result
assert "subscriptionCount(key).then" not in result
assert "const meta=await multiMeta(protocol);" not in result

# Presentation counts come from the already rendered canonical server inventory.
assert "function subscriptionCount(panel)" in result
assert "panel.querySelectorAll('.server-views .server-view').length" in result
assert "const meta=multiMeta(panel);" in result

# Live status remains enabled, but polling cannot overlap and uses a quieter cadence.
assert "let refreshInFlight=false;" in result
assert "if(refreshInFlight||document.hidden)return;" in result
assert "finally{refreshInFlight=false}" in result
assert "setInterval(refresh,10000)" in result
assert "setInterval(refresh,3000)" not in result

print("PUBLIC_CONNECT_REQUEST_BACKPRESSURE_V42_SMOKE_OK")
