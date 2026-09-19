from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 60}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401
    from sqlalchemy import inspect, text

    Base.metadata.create_all(bind=engine)

    # Lightweight SQLite column / label migrations for existing DBs
    if settings.database_url.startswith("sqlite"):
        with engine.begin() as conn:
            tables = inspect(conn).get_table_names()
            if "email_messages" in tables:
                cols = {c["name"] for c in inspect(conn).get_columns("email_messages")}
                if "body_html" not in cols:
                    conn.execute(text("ALTER TABLE email_messages ADD COLUMN body_html TEXT DEFAULT ''"))
                if "is_read" not in cols:
                    conn.execute(text("ALTER TABLE email_messages ADD COLUMN is_read BOOLEAN DEFAULT 0"))
                conn.execute(
                    text("UPDATE email_messages SET label = 'assessment' WHERE label = 'tech'")
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_email_messages_received_id "
                        "ON email_messages (received_at, id)"
                    )
                )
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA busy_timeout=60000"))
            conn.commit()
