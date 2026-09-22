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


LABEL_SLUG_REMAPS = (
    ("tech", "assessment"),
    ("available", "screening"),
    ("alert", "job_alert"),
    ("application_submitted", "applied"),
    ("new_opportunity", "job_alert"),
    ("recruiter_outreach", "job_alert"),
    ("talent_pool", "others"),
    ("company_news", "others"),
    ("career_event", "others"),
    ("profile_update_request", "others"),
    ("withdrawn", "rejected"),
    ("hired", "offer"),
    ("unknown", "others"),
)

_DROPPED_TAXONOMY_SLUGS = (
    "application_submitted",
    "new_opportunity",
    "recruiter_outreach",
    "talent_pool",
    "company_news",
    "career_event",
    "profile_update_request",
    "withdrawn",
    "hired",
    "unknown",
)


def seed_default_classify_prompt() -> None:
    from app.classify.prompt import SYSTEM_PROMPT
    from app.models import ClassifyPromptVersion

    db = SessionLocal()
    try:
        exists = db.query(ClassifyPromptVersion.id).first()
        if exists is None:
            db.add(
                ClassifyPromptVersion(
                    prompt_text=SYSTEM_PROMPT,
                    is_active=True,
                    source="seed",
                    example_count=0,
                )
            )
            db.commit()
    finally:
        db.close()


def _is_current_taxonomy_prompt(text: str) -> bool:
    if not text:
        return False
    if any(f"- {slug}" in text for slug in _DROPPED_TAXONOMY_SLUGS):
        return False
    from app.models import EmailLabel

    return all(item.value in text for item in EmailLabel)


def ensure_taxonomy_v4_prompt() -> bool:
    """Activate the eight-label SYSTEM_PROMPT when the live prompt still lists unknown.

    Does not start a reclassify job. Returns True only when a new version was inserted.
    """
    from app.classify.prompt import SYSTEM_PROMPT
    from app.classify.prompt_store import activate_prompt_text
    from app.models import ClassifyPromptVersion

    db = SessionLocal()
    try:
        active = (
            db.query(ClassifyPromptVersion)
            .filter(ClassifyPromptVersion.is_active.is_(True))
            .order_by(ClassifyPromptVersion.id.desc())
            .first()
        )
        text = (active.prompt_text if active else "") or ""
        if _is_current_taxonomy_prompt(text):
            return False
        if active is not None:
            active.is_active = False
        db.add(
            ClassifyPromptVersion(
                prompt_text=SYSTEM_PROMPT,
                is_active=True,
                source="taxonomy_v4",
                example_count=0,
            )
        )
        db.commit()
        activate_prompt_text(SYSTEM_PROMPT)
        return True
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
                if "human_corrected" not in cols:
                    conn.execute(
                        text(
                            "ALTER TABLE email_messages ADD COLUMN human_corrected BOOLEAN DEFAULT 0"
                        )
                    )
                if "folder" not in cols:
                    conn.execute(
                        text(
                            "ALTER TABLE email_messages ADD COLUMN folder VARCHAR(16) DEFAULT 'inbox'"
                        )
                    )
                    conn.execute(
                        text("UPDATE email_messages SET folder = 'inbox' WHERE folder IS NULL")
                    )
                if "company" not in cols:
                    conn.execute(text("ALTER TABLE email_messages ADD COLUMN company VARCHAR(255)"))
                if "job_role" not in cols:
                    conn.execute(text("ALTER TABLE email_messages ADD COLUMN job_role VARCHAR(255)"))
                if "outcome_extracted" not in cols:
                    conn.execute(
                        text(
                            "ALTER TABLE email_messages ADD COLUMN outcome_extracted BOOLEAN DEFAULT 0"
                        )
                    )
                for old, new in LABEL_SLUG_REMAPS:
                    conn.execute(
                        text("UPDATE email_messages SET label = :new WHERE label = :old"),
                        {"new": new, "old": old},
                    )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_email_messages_received_id "
                        "ON email_messages (received_at, id)"
                    )
                )
            if "mailbox_connections" in tables:
                mb_cols = {c["name"] for c in inspect(conn).get_columns("mailbox_connections")}
                if "received_at_utc_fixed" not in mb_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE mailbox_connections "
                            "ADD COLUMN received_at_utc_fixed BOOLEAN DEFAULT 0"
                        )
                    )
            if "classify_corrections" in tables:
                for old, new in LABEL_SLUG_REMAPS:
                    conn.execute(
                        text(
                            "UPDATE classify_corrections SET previous_label = :new "
                            "WHERE previous_label = :old"
                        ),
                        {"new": new, "old": old},
                    )
                    conn.execute(
                        text(
                            "UPDATE classify_corrections SET corrected_label = :new "
                            "WHERE corrected_label = :old"
                        ),
                        {"new": new, "old": old},
                    )
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA busy_timeout=60000"))
            conn.commit()

    seed_default_classify_prompt()
    from app.services.mailbox_cleanup import purge_orphaned_mailbox_mail

    purge_orphaned_mailbox_mail()
    ensure_taxonomy_v4_prompt()
