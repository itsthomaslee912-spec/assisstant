from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api import auth, dashboard, jobs, profiles, users
from app.db import Base, SessionLocal, engine
from app.models import User
from app.security import hash_password


def seed_admin() -> None:
    admin_email = os.environ.get("INITIAL_ADMIN_EMAIL", "").strip()
    admin_user_id = os.environ.get("INITIAL_ADMIN_USER_ID", "").strip()
    admin_password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
    if not all((admin_email, admin_user_id, admin_password)):
        return
    with SessionLocal() as db:
        exists = db.query(User).filter(User.user_id == admin_user_id).one_or_none()
        if exists is None:
            db.add(User(
                email=admin_email,
                user_id=admin_user_id,
                password_hash=hash_password(admin_password),
                status="active",
                role="admin",
            ))
            db.commit()


def migrate_job_audit_fields() -> None:
    """Add newer job fields to databases created by earlier versions."""
    columns = {column["name"] for column in inspect(engine).get_columns("job_applications")}
    if "submitted_at" not in columns:
        column_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE job_applications ADD COLUMN submitted_at {column_type}"))
    if "bot_check_passed" not in columns:
        boolean_type = "BOOLEAN NOT NULL DEFAULT FALSE" if engine.dialect.name == "postgresql" else "BOOLEAN NOT NULL DEFAULT 0"
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE job_applications ADD COLUMN bot_check_passed {boolean_type}"))
    if "bot_check_status" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE job_applications ADD COLUMN bot_check_status VARCHAR(16) NOT NULL DEFAULT 'pending'"))
            connection.execute(text("UPDATE job_applications SET bot_check_status = 'pass' WHERE bot_check_passed = TRUE"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    migrate_job_audit_fields()
    seed_admin()
    yield


app = FastAPI(title="Bid Manage System API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:9012", "http://127.0.0.1:9012"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(profiles.router)
app.include_router(users.router)
app.include_router(jobs.router)
app.include_router(dashboard.router)


@app.get("/api/health")
def health():
    return {"ok": True}
