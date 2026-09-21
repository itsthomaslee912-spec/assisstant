from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import emails
from app.db import Base, get_db
from app.models import EmailLabel, EmailMessage, MailboxConnection, Provider, User


def _session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _client(SessionLocal):
    app = FastAPI()
    app.include_router(emails.router)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _seed_unread_email(db) -> EmailMessage:
    user = User(external_id="u-mark-read")
    db.add(user)
    db.flush()
    mailbox = MailboxConnection(
        user_id=user.id,
        provider=Provider.GOOGLE.value,
        email_address="mark-read@example.com",
        access_token_enc="x",
        refresh_token_enc="",
        is_active=True,
    )
    db.add(mailbox)
    db.flush()
    email = EmailMessage(
        mailbox_id=mailbox.id,
        provider_message_id="msg-unread-1",
        subject="Please open me",
        sender="sender@example.com",
        snippet="hello",
        body_text="Hello body",
        label=EmailLabel.OTHERS.value,
        is_read=False,
    )
    db.add(email)
    db.commit()
    db.refresh(email)
    return email


def test_get_email_marks_provider_read_once():
    SessionLocal = _session_factory()
    db = SessionLocal()
    email = _seed_unread_email(db)
    email_id = email.id
    db.close()

    client = _client(SessionLocal)
    mark_read = AsyncMock()
    ensure_token = AsyncMock(return_value="token")

    with (
        patch("app.api.emails.gmail_mark_read", mark_read),
        patch("app.api.emails.ensure_google_access_token", ensure_token),
    ):
        first = client.get(f"/api/emails/{email_id}")
        assert first.status_code == 200
        assert first.json()["is_read"] is True
        mark_read.assert_awaited_once_with("token", "msg-unread-1")

        mark_read.reset_mock()
        second = client.get(f"/api/emails/{email_id}")
        assert second.status_code == 200
        assert second.json()["is_read"] is True
        mark_read.assert_not_awaited()


def test_get_email_still_marks_local_read_when_provider_fails():
    SessionLocal = _session_factory()
    db = SessionLocal()
    email = _seed_unread_email(db)
    email_id = email.id
    db.close()

    client = _client(SessionLocal)
    mark_read = AsyncMock(side_effect=RuntimeError("quota"))
    ensure_token = AsyncMock(return_value="token")

    with (
        patch("app.api.emails.gmail_mark_read", mark_read),
        patch("app.api.emails.ensure_google_access_token", ensure_token),
    ):
        res = client.get(f"/api/emails/{email_id}")
        assert res.status_code == 200
        assert res.json()["is_read"] is True
        mark_read.assert_awaited_once()
