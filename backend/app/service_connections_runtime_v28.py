"""Release-line marker for the restored Service Connections runtime."""

SERVICE_CONNECTIONS_RUNTIME_VERSION = 28
SERVICE_CONNECTIONS_ROUTE = "/v1/tunnels/{tunnel_id}/service-connections"
SERVICE_CONNECTIONS_REPAIR_ROUTE = (
    "/v1/tunnels/{tunnel_id}/service-connections/repair-real-egress"
)
SERVICE_CONNECTIONS_XRAY_JOB_ROUTE = (
    "/v1/tunnels/{tunnel_id}/service-connections/xray-reconcile-job"
)
