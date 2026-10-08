from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

from .models import NodeStatus, NodeType, SubscriptionStatus, TunnelStatus, UserRole


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class EmailChangeIn(BaseModel):
    email: EmailStr
    current_password: str


class AdminPasswordResetIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class AdminUserCreateIn(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class AdminUserUpdateIn(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    full_name: str | None = None


class UserOut(BaseModel):
    id: int
    # TWINPANEL_USEROUT_INTERNAL_EMAIL_V1
    # Output may include system-generated Telegram identities.
    # Input schemas still use EmailStr validation.
    email: str | None
    phone: str | None = None
    full_name: str | None
    role: UserRole
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class PlanCreate(BaseModel):
    name: str
    description: str | None = Field(default=None, max_length=500)
    duration_days: int = Field(gt=0)
    traffic_gb: int = Field(gt=0)
    device_limit: int = Field(default=1, gt=0)
    price_toman: int = Field(gt=0)
    enable_cisco: bool = True
    enable_openvpn: bool = True
    enable_wireguard: bool = True
    enable_l2tp: bool = True
    enable_v2ray: bool = True


class PlanUpdate(BaseModel):
    name: str | None = None
    description: str | None = Field(default=None, max_length=500)
    duration_days: int | None = Field(default=None, gt=0)
    traffic_gb: int | None = Field(default=None, gt=0)
    device_limit: int | None = Field(default=None, gt=0)
    price_toman: int | None = Field(default=None, gt=0)
    is_active: bool | None = None
    enable_cisco: bool | None = None
    enable_openvpn: bool | None = None
    enable_wireguard: bool | None = None
    enable_l2tp: bool | None = None
    enable_v2ray: bool | None = None


class PlanOut(PlanCreate):
    id: int
    is_active: bool

    # TWINPANEL_LOGICAL_TUNNEL_SCHEMA_V52_OUT
    mode: str = "manual"
    preferred_transport: str | None = None
    active_transport: str | None = None
    last_switch_at: datetime | None = None

    model_config = {"from_attributes": True}


class NodeCreate(BaseModel):
    name: str
    node_type: NodeType
    country_code: str = "IR"
    public_ip: str

    # Filled automatically by the backend when omitted by the simple panel.
    agent_url: str | None = None

    enable_cisco: bool = False
    enable_openvpn: bool = False
    enable_wireguard: bool = False
    enable_l2tp: bool = False
    enable_v2ray: bool = False
    show_to_users: bool = True
    capacity_users: int = Field(default=1000, gt=0)


class NodeUpdate(BaseModel):
    name: str | None = None
    country_code: str | None = None
    public_ip: str | None = None
    capacity_users: int | None = Field(default=None, gt=0)
    status: NodeStatus | None = None
    show_to_users: bool | None = None


class NodeOut(BaseModel):
    id: int
    name: str
    node_type: NodeType
    country_code: str
    public_ip: str
    public_domain: str | None = None
    agent_url: str
    enable_cisco: bool
    enable_openvpn: bool
    enable_wireguard: bool
    enable_l2tp: bool
    enable_v2ray: bool
    capacity_users: int
    status: NodeStatus
    current_users: int
    last_seen_at: datetime | None = None
    is_mother: bool = False
    model_config = {"from_attributes": True}


class NodeHeartbeatIn(BaseModel):
    current_users: int = Field(default=0, ge=0)
    cpu_percent: float = Field(default=0, ge=0, le=100)
    memory_percent: float = Field(default=0, ge=0, le=100)
    disk_percent: float = Field(default=0, ge=0, le=100)
    protocols: dict[str, bool] = {}
    hostname: str | None = None


class TunnelCreate(BaseModel):
    iran_node_id: int
    exit_node_id: int
    # TWINPANEL_TUNNEL_CREATE_SCHEMA_V63
    transport: str = "ssh_tun"
    priority: int = 100
    is_active: bool = True


class TunnelUpdate(BaseModel):
    # TWINPANEL_LOGICAL_TUNNEL_SCHEMA_V52
    transport: str | None = None
    mode: str | None = None
    preferred_transport: str | None = None
    priority: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class TunnelOut(BaseModel):
    id: int
    iran_node_id: int
    exit_node_id: int
    transport: str
    active_transport: str | None = None
    preferred_transport: str | None = None
    status: TunnelStatus
    latency_ms: int | None
    priority: int
    is_active: bool
    model_config = {"from_attributes": True}


class SubscriptionCreate(BaseModel):
    user_id: int
    plan_id: int
    node_ids: list[int] = Field(default_factory=list)
    protocols: list[str] = Field(default_factory=list)
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    traffic_gb: int | None = Field(default=None, ge=1, le=100000)
    username: str | None = None
    password: str | None = None


class SubscriptionOut(BaseModel):
    id: int
    user_id: int
    plan_id: int
    status: SubscriptionStatus
    traffic_limit_bytes: int
    traffic_used_bytes: int
    iran_node_id: int | None
    exit_node_id: int | None
    starts_at: datetime | None
    expires_at: datetime | None
    created_at: datetime | None = None
    account_username: str | None = None

    customer_email: str | None = None
    customer_name: str | None = None
    plan_name: str | None = None

    traffic_limit_gb: float = 0
    traffic_used_gb: float = 0

    node_ids: list[int] = Field(default_factory=list)
    protocols: list[str] = Field(default_factory=list)
    model_config = {"from_attributes": True}


class MySubscriptionOut(SubscriptionOut):
    plan_name: str | None = None
    account_username: str | None = None
    traffic_limit_gb: float = 0
    traffic_used_gb: float = 0
    traffic_remaining_gb: float = 0
    days_remaining: int = 0
    device_limit: int = 0

    # TWINPANEL_MY_SUB_FIRST_USE_UI_V1
    activation_duration_days: int = 0
    protocols: list[str] = Field(default_factory=list)


class AdminStatsOut(BaseModel):
    users: int
    active_subscriptions: int
    online_nodes: int
    active_plans: int


class TunnelPeerReportIn(BaseModel):
    wireguard_public_key: str | None = Field(default=None, max_length=128)
    selected_transport: str | None = Field(default=None, max_length=32)
    endpoint_reachable: bool = False
    tunnel_reachable: bool = False
    latency_ms: int | None = Field(default=None, ge=0, le=60000)
    last_error: str | None = Field(default=None, max_length=1000)


# TWINPANEL_REAL_2FA_LOGIN_RESPONSE_V1
class LoginOut(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"
    requires_2fa: bool = False
    two_factor_token: str | None = None
