from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VPNShop"
    app_env: str = "production"
    app_secret_key: str
    access_token_expire_minutes: int = 10080
    database_url: str
    redis_url: str = "redis://127.0.0.1:6379/0"
    node_agent_shared_secret: str

    # Public API discovery:
    # - before an API domain exists, expose this IP/base URL
    # - after admin configures an active API domain, runtime discovery
    #   automatically prefers the domain without requiring a frontend rebuild
    public_api_fallback: str = ""

    # Public customer connection delivery can live behind a dedicated HTTPS
    # edge/domain independently from the API origin. This is especially useful
    # when TCP/443 on the controller is intentionally owned by Cisco/ocserv.
    # Example: https://connect.example.com
    public_subscription_base_url: str = ""

    # Packaged/licensed Backhaul runtime used by self-hosted tunnel provisioning.
    # Release/installer must place the binary at this path or override it by env.
    backhaul_binary_path: str = "/opt/twinpanel/runtime/backhaul/backhaul_premium"

    # Netrix remains a third-party licensed runtime. TwinPanel never bypasses
    # its license system; customers who own a valid binary can place it here
    # (or override it by env) and TwinPanel will provision it to nodes.
    netrix_binary_path: str = "/opt/twinpanel/runtime/netrix/netrix"

    payment_sms_relay_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
