import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, BigInteger,
    String, Text, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class SubscriptionStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    CANCELED = "canceled"


class NodeType(str, enum.Enum):
    IRAN = "iran"
    EXIT = "exit"


class NodeStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class TunnelStatus(str, enum.Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(190), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="user")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_days: Mapped[int] = mapped_column(Integer)
    traffic_gb: Mapped[int] = mapped_column(Integer)
    device_limit: Mapped[int] = mapped_column(Integer, default=1)
    price_toman: Mapped[int] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    enable_cisco: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_openvpn: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_wireguard: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_l2tp: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_v2ray: Mapped[bool] = mapped_column(Boolean, default=True)


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    node_type: Mapped[NodeType] = mapped_column(Enum(NodeType))
    country_code: Mapped[str] = mapped_column(String(8), default="IR")
    public_ip: Mapped[str] = mapped_column(String(64))
    public_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agent_url: Mapped[str] = mapped_column(String(255))
    status: Mapped[NodeStatus] = mapped_column(Enum(NodeStatus), default=NodeStatus.OFFLINE)

    # Visibility control for customer delivery
    show_to_users: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    enable_cisco: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_openvpn: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_wireguard: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_l2tp: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_v2ray: Mapped[bool] = mapped_column(Boolean, default=False)

    current_users: Mapped[int] = mapped_column(Integer, default=0)
    capacity_users: Mapped[int] = mapped_column(Integer, default=1000)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # TWINPANEL_NODE_RETIRE_V1
    # Retired nodes remain only as historical identities for
    # append-only quota/accounting records.
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )


    @property
    def is_mother(self) -> bool:
        return self.agent_url == "local://core"


class NodeAccess(Base):
    __tablename__ = "node_access"
    __table_args__ = (UniqueConstraint("node_id", name="uq_node_access_node"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_username: Mapped[str] = mapped_column(String(120), default="root")
    private_key_path: Mapped[str] = mapped_column(String(500))
    public_key_fingerprint: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Tunnel(Base):
    __tablename__ = "tunnels"
    # TWINPANEL_LOGICAL_PAIR_MODEL_V53
    # One Iran -> Exit pair is one logical Tunnel.
    __table_args__ = (
        UniqueConstraint(
            "iran_node_id",
            "exit_node_id",
            name="uq_tunnel_pair",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    iran_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    exit_node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    transport: Mapped[str] = mapped_column(String(50), default="wireguard")
    status: Mapped[TunnelStatus] = mapped_column(Enum(TunnelStatus), default=TunnelStatus.OFFLINE)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # TWINPANEL_TUNNEL_WG_PORT_SELF_HEAL_V1
    # Last working / currently selected WireGuard transport port.
    wireguard_port: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )


    # TWINPANEL_LOGICAL_TUNNEL_V52
    #
    # One Tunnel row = one logical Iran -> Exit path.
    # Physical transports are children in tunnel_transports.
    mode: Mapped[str] = mapped_column(
        String(16),
        default="manual",
        nullable=False,
    )

    preferred_transport: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    active_transport: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    last_switch_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )


class TunnelTransport(Base):
    __tablename__ = "tunnel_transports"

    __table_args__ = (
        UniqueConstraint(
            "tunnel_id",
            "transport",
            name="uq_tunnel_transport",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
    )

    tunnel_id: Mapped[int] = mapped_column(
        ForeignKey(
            "tunnels.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    transport: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        default=100,
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(24),
        default="not_installed",
        nullable=False,
    )

    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    last_healthy_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    config_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.PENDING
    )

    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # TWINPANEL_FIRST_USE_DURATION_MODEL_V1
    # Purchased duration is stored separately until the first
    # accepted VPN session starts the subscription clock.
    activation_duration_days: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    traffic_limit_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_used_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

    iran_node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id"), nullable=True)
    exit_node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id"), nullable=True)

    # Custom VPN account credentials
    account_username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    account_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Public subscription short link code
    share_code: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=True
    )

    user = relationship("User", back_populates="subscriptions")
    plan = relationship("Plan")


class SubscriptionNode(Base):
    __tablename__ = "subscription_nodes"
    __table_args__ = (
        UniqueConstraint("subscription_id", "node_id", name="uq_subscription_node"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SubscriptionProtocol(Base):
    __tablename__ = "subscription_protocols"
    __table_args__ = (
        UniqueConstraint("subscription_id", "protocol", name="uq_subscription_selected_protocol"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    protocol: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProtocolCredential(Base):
    __tablename__ = "protocol_credentials"
    __table_args__ = (
        UniqueConstraint("subscription_id", "protocol", name="uq_subscription_protocol"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"))
    protocol: Mapped[str] = mapped_column(String(30))
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_text_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TunnelPeerState(Base):
    __tablename__ = "tunnel_peer_states"
    __table_args__ = (
        UniqueConstraint("tunnel_id", "node_id", name="uq_tunnel_peer_state"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tunnel_id: Mapped[int] = mapped_column(
        ForeignKey("tunnels.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[int] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False
    )
    wireguard_public_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    selected_transport: Mapped[str | None] = mapped_column(String(32), nullable=True)
    endpoint_reachable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tunnel_reachable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class NodeProtocolConfig(Base):
    __tablename__ = "node_protocol_configs"
    __table_args__ = (UniqueConstraint("node_id", "protocol", name="uq_node_protocol_config"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    port_text: Mapped[str] = mapped_column(String(80), default="")
    transport: Mapped[str] = mapped_column(String(32), default="")
    service_name: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(24), default="offline")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CleanupJob(Base):
    __tablename__ = "cleanup_jobs"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True
    )

    target_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    target_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )

    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )
