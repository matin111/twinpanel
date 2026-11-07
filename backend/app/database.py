from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings


# TWINPANEL_API_DB_LOCK_TIMEOUT_V2
# PostgreSQL accepts libpq `options`; SQLite and other CI/test dialects do not.
# Keep the freeze protection production-scoped without changing test/database
# compatibility for non-PostgreSQL URLs.
_DATABASE_CONNECT_ARGS = (
    {"options": "-c lock_timeout=3000"}
    if settings.database_url.startswith(("postgresql://", "postgresql+psycopg2://"))
    else {}
)

engine = create_engine(
    settings.database_url,

    # TWINPANEL_DATABASE_POOL_V1
    # Agents, admin panel and customer traffic
    # share this API process.
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=20,
    pool_timeout=10,
    pool_recycle=1800,

    # Bound PostgreSQL lock waits so a contended synchronous SQL statement
    # cannot freeze the single Uvicorn event-loop worker indefinitely.
    connect_args=_DATABASE_CONNECT_ARGS,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

Base = declarative_base()


# HTTP has a bounded pool independent of long-running background jobs.
# Keep transaction and credentials semantics identical to the existing engine.
if settings.database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
    request_engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        # Keep HTTP responses responsive when node polling and the admin UI
        # overlap. 32 HTTP connections + up to 40 worker connections remains
        # below the PostgreSQL max_connections=100 of the standard install.
        pool_size=16,
        max_overflow=16,
        pool_timeout=10,
        pool_recycle=1800,
        pool_use_lifo=True,
        connect_args=_DATABASE_CONNECT_ARGS,
        future=True,
    )
else:
    # SQLite tests and other drivers retain their own compatible default pool.
    request_engine = engine
RequestSessionLocal = sessionmaker(
    bind=request_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db():
    db = RequestSessionLocal()
    try:
        yield db
    finally:
        db.close()
