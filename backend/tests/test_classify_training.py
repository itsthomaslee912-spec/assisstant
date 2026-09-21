from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import classify, emails
from app.classify.openai_classifier import classify_email
from app.classify.prompt import SYSTEM_PROMPT
from app.classify.prompt_store import activate_prompt_text, get_active_system_prompt, invalidate_prompt_cache
from app.db import Base, get_db
from app.models import (
    ClassifyCorrection,
    ClassifyPromptVersion,
    EmailLabel,
    EmailMessage,
    MailboxConnection,
    Provider,
    User,
)
from app.services.prompt_update import PromptUpdateError, update_prompt_from_corrections


def _session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _seed_email(db, *, label: str = EmailLabel.APPLIED.value, human_corrected: bool = False) -> EmailMessage:
    user = User(external_id="test-user")
    db.add(user)
    db.flush()
    mailbox = MailboxConnection(
        user_id=user.id,
        provider=Provider.GOOGLE.value,
        email_address="me@example.com",
        access_token_enc="x",
        refresh_token_enc="",
        is_active=True,
    )
    db.add(mailbox)
    db.flush()
    email = EmailMessage(
        mailbox_id=mailbox.id,
        provider_message_id="msg-1",
        subject="Thanks for applying",
        sender="Talent <jobs@cloudbeds.com>",
        snippet="we will not be moving forward",
        body_text="Unfortunately we will not be moving forward with your application.",
        label=label,
        human_corrected=human_corrected,
    )
    db.add(email)
    db.commit()
    db.refresh(email)
    return email


def _client(SessionLocal):
    app = FastAPI()
    app.include_router(emails.router)
    app.include_router(classify.router)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_patch_label_saves_training_and_pins():
    SessionLocal = _session_factory()
    db = SessionLocal()
    email = _seed_email(db)
    email_id = email.id
    db.close()

    client = _client(SessionLocal)
    res = client.patch(
        f"/api/emails/{email_id}/label",
        json={"label": "rejected", "save_training": True},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["label"] == "rejected"
    assert body["human_corrected"] is True

    db = SessionLocal()
    stored = db.query(EmailMessage).filter(EmailMessage.id == email_id).one()
    assert stored.label == EmailLabel.REJECTED.value
    assert stored.human_corrected is True
    row = db.query(ClassifyCorrection).one()
    assert row.previous_label == EmailLabel.APPLIED.value
    assert row.corrected_label == EmailLabel.REJECTED.value
    assert "not be moving forward" in row.body_text
    db.close()


def test_patch_label_without_training_skips_correction():
    SessionLocal = _session_factory()
    db = SessionLocal()
    email = _seed_email(db, label=EmailLabel.OTHERS.value)
    email_id = email.id
    db.close()

    client = _client(SessionLocal)
    res = client.patch(
        f"/api/emails/{email_id}/label",
        json={"label": "job_alert", "save_training": False},
    )
    assert res.status_code == 200, res.text
    db = SessionLocal()
    assert db.query(ClassifyCorrection).count() == 0
    assert db.query(EmailMessage).one().human_corrected is True
    db.close()


def test_reclassify_query_skips_human_corrected():
    SessionLocal = _session_factory()
    db = SessionLocal()
    locked = _seed_email(db, human_corrected=True)
    unlocked = EmailMessage(
        mailbox_id=locked.mailbox_id,
        provider_message_id="msg-2",
        subject="Interview confirmed",
        sender="Kate",
        snippet="You are confirmed",
        body_text="You are confirmed for your interview.",
        label=EmailLabel.OTHERS.value,
        human_corrected=False,
    )
    db.add(unlocked)
    db.commit()
    rows = (
        db.query(EmailMessage.id)
        .filter(
            EmailMessage.mailbox_id == locked.mailbox_id,
            EmailMessage.human_corrected.is_not(True),
        )
        .all()
    )
    ids = {row[0] for row in rows}
    assert unlocked.id in ids
    assert locked.id not in ids
    db.close()


def test_prompt_loader_falls_back_to_seed(monkeypatch):
    invalidate_prompt_cache()
    monkeypatch.setattr("app.classify.prompt_store._load_from_db", lambda: None)
    assert get_active_system_prompt() == SYSTEM_PROMPT
    invalidate_prompt_cache()


def test_update_prompt_from_corrections(monkeypatch):
    SessionLocal = _session_factory()
    db = SessionLocal()
    email = _seed_email(db)
    db.add(
        ClassifyCorrection(
            email_id=email.id,
            previous_label=EmailLabel.APPLIED.value,
            corrected_label=EmailLabel.REJECTED.value,
            subject=email.subject,
            sender=email.sender,
            snippet=email.snippet,
            body_text=email.body_text,
        )
    )
    db.commit()

    updated = SYSTEM_PROMPT + "\n- Cloudbeds-style polite turndowns are rejected, not applied.\n"

    class FakeCompletions:
        async def create(self, **kwargs):
            return SimpleNamespace(
                id="resp_prompt",
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"prompt": updated})))],
            )

    monkeypatch.setattr(
        "app.services.prompt_update.get_settings",
        lambda: SimpleNamespace(openai_api_key="sk-test", openai_model="gpt-4o-mini"),
    )
    monkeypatch.setattr(
        "app.services.prompt_update.AsyncOpenAI",
        lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())),
    )

    result = asyncio.run(update_prompt_from_corrections(db))
    assert result.ok is True
    assert result.example_count == 1
    active = (
        db.query(ClassifyPromptVersion)
        .filter(ClassifyPromptVersion.is_active.is_(True))
        .one()
    )
    assert "Cloudbeds-style" in active.prompt_text
    assert db.query(ClassifyCorrection).one().used_in_prompt_version_id == active.id
    assert get_active_system_prompt() == active.prompt_text
    db.close()
    invalidate_prompt_cache()


def test_update_prompt_requires_examples(monkeypatch):
    SessionLocal = _session_factory()
    db = SessionLocal()
    monkeypatch.setattr(
        "app.services.prompt_update.get_settings",
        lambda: SimpleNamespace(openai_api_key="sk-test", openai_model="gpt-4o-mini"),
    )
    try:
        asyncio.run(update_prompt_from_corrections(db))
        assert False, "expected PromptUpdateError"
    except PromptUpdateError as exc:
        assert "No unused training examples" in str(exc)
    db.close()


def test_prompt_status_endpoint():
    SessionLocal = _session_factory()
    client = _client(SessionLocal)
    res = client.get("/api/classify/prompt")
    assert res.status_code == 200, res.text
    assert res.json()["unused_count"] == 0


def test_list_training_examples_marks_used_and_unused():
    SessionLocal = _session_factory()
    db = SessionLocal()
    email = _seed_email(db)
    unused = ClassifyCorrection(
        email_id=email.id,
        previous_label=EmailLabel.APPLIED.value,
        corrected_label=EmailLabel.REJECTED.value,
        subject=email.subject,
        sender=email.sender,
        snippet=email.snippet,
        body_text=email.body_text,
    )
    version = ClassifyPromptVersion(
        prompt_text=SYSTEM_PROMPT,
        is_active=True,
        source="seed",
        example_count=1,
    )
    db.add_all([unused, version])
    db.flush()
    used = ClassifyCorrection(
        email_id=email.id,
        previous_label=EmailLabel.OTHERS.value,
        corrected_label=EmailLabel.INTERVIEW.value,
        subject="Interview next week",
        sender="Kate",
        snippet="confirmed",
        body_text="You are confirmed",
        used_in_prompt_version_id=version.id,
    )
    db.add(used)
    db.commit()
    db.close()

    client = _client(SessionLocal)
    res = client.get("/api/classify/training")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 2
    assert body["unused_count"] == 1
    items = body["items"]
    assert items[0]["id"] > items[1]["id"]
    used_flags = {item["subject"]: item["used_in_prompt_version_id"] is not None for item in items}
    assert used_flags["Thanks for applying"] is False
    assert used_flags["Interview next week"] is True
    assert "body_text" not in items[0]


def test_classify_email_uses_db_prompt_not_seed(monkeypatch):
    updated = SYSTEM_PROMPT + "\n- Unique marker from the SQLite active prompt.\n"
    captured: dict = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            return SimpleNamespace(
                id="resp_cls",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps({"label": "others", "confidence": 0.9})
                        )
                    )
                ],
            )

    monkeypatch.setattr(
        "app.classify.openai_classifier.get_settings",
        lambda: SimpleNamespace(openai_api_key="sk-test", openai_model="gpt-4o-mini"),
    )
    monkeypatch.setattr(
        "app.classify.openai_classifier.AsyncOpenAI",
        lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())),
    )
    monkeypatch.setattr("app.classify.prompt_store._load_from_db", lambda: updated.strip())
    invalidate_prompt_cache()

    asyncio.run(
        classify_email(
            subject="Hello",
            sender="recruiter@example.com",
            body_text="A generic note.",
            snippet="A generic note.",
        )
    )
    system = captured["messages"][0]["content"]
    assert "Unique marker from the SQLite active prompt" in system
    assert system != SYSTEM_PROMPT
    invalidate_prompt_cache()


def test_classify_email_uses_activated_prompt_immediately(monkeypatch):
    updated = SYSTEM_PROMPT + "\n- Immediate cache marker after Update prompt.\n"
    captured: dict = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            return SimpleNamespace(
                id="resp_cls2",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps({"label": "others", "confidence": 0.8})
                        )
                    )
                ],
            )

    monkeypatch.setattr(
        "app.classify.openai_classifier.get_settings",
        lambda: SimpleNamespace(openai_api_key="sk-test", openai_model="gpt-4o-mini"),
    )
    monkeypatch.setattr(
        "app.classify.openai_classifier.AsyncOpenAI",
        lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())),
    )
    monkeypatch.setattr("app.classify.prompt_store._load_from_db", lambda: SYSTEM_PROMPT)
    invalidate_prompt_cache()
    activate_prompt_text(updated)

    asyncio.run(
        classify_email(
            subject="Hello",
            sender="recruiter@example.com",
            body_text="A generic note.",
            snippet="A generic note.",
        )
    )
    system = captured["messages"][0]["content"]
    assert "Immediate cache marker after Update prompt" in system
    invalidate_prompt_cache()

