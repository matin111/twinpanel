from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

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

    # TWINPANEL_API_DB_LOCK_TIMEOUT_V1
    # The API currently uses synchronous SQLAlchemy sessions from routes which
    # may also perform async remote work. A database lock wait therefore blocks
    # the single Uvicorn event-loop worker. Bound PostgreSQL lock waits so one
    # contended transaction cannot freeze the whole admin/customer API.
    #
    # This is deliberately a lock timeout only; normal long-running statements
    # are not given a statement_timeout here.
    connect_args={"options": "-c lock_timeout=3000"},
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
