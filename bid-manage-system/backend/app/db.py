from __future__ import annotations

from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

# Local SQLite remains a convenient development fallback. Production and
# shared environments use DATABASE_URL (for example, a Neon PostgreSQL URL).
database_url = os.environ.get("DATABASE_URL", "").strip()
if not database_url:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{DATA_DIR / 'bid_manager.db'}"
elif database_url.startswith("postgresql://"):
    # Select SQLAlchemy's modern psycopg v3 dialect explicitly.
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False, "timeout": 30} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
