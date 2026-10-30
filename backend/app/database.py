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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
