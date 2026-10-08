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

    payment_sms_relay_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
