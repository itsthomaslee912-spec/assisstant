from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.classify.openai_classifier import classify_email
from app.classify.outcome_extract import apply_outcome
from app.email.folders import normalize_folder
from app.models import EmailMessage, MailboxConnection
from app.realtime.sse import publish
from app.schemas import EmailOut
from app.timeutil import as_utc

logger = logging.getLogger(__name__)


async def ingest_normalized_message(
    db: Session,
    mailbox: MailboxConnection,
    normalized: dict,
    *,
    force_openai: bool = False,
    use_openai: bool = True,
) -> EmailMessage | None:
    existing = (
        db.query(EmailMessage)
        .filter(
            EmailMessage.mailbox_id == mailbox.id,
            EmailMessage.provider_message_id == normalized["provider_message_id"],
        )
        .one_or_none()
    )
    if existing is not None:
        changed = False
        folder = normalize_folder(normalized.get("folder"))
        if existing.folder != folder:
            existing.folder = folder
            changed = True
        new_received = as_utc(normalized.get("received_at"))
        if new_received is not None and existing.received_at != new_received:
            existing.received_at = new_received
            changed = True
        if changed:
            db.commit()
        return None

    try:
        # Live/Sync classify with the active SQLite prompt (updated via Update prompt).
        classification = await classify_email(
            subject=normalized.get("subject") or "",
            sender=normalized.get("sender") or "",
            body_text=normalized.get("body_text") or "",
            snippet=normalized.get("snippet") or "",
            force_openai=force_openai,
            use_openai=use_openai,
        )
    except Exception:
        logger.exception("Classification failed; using heuristic")
        classification = await classify_email(
            subject=normalized.get("subject") or "",
            sender=normalized.get("sender") or "",
            body_text=normalized.get("body_text") or "",
            snippet=normalized.get("snippet") or "",
            use_openai=False,
        )

    email = EmailMessage(
        mailbox_id=mailbox.id,
        provider_message_id=normalized["provider_message_id"],
        thread_id=normalized.get("thread_id"),
        subject=normalized.get("subject") or "",
        sender=normalized.get("sender") or "",
        received_at=as_utc(normalized.get("received_at")),
        snippet=(normalized.get("snippet") or "")[:1000],
        body_text=normalized.get("body_text") or "",
        body_html=normalized.get("body_html") or "",
        label=classification.label,
        confidence=classification.confidence,
        openai_response_id=classification.response_id,
        folder=normalize_folder(normalized.get("folder")),
    )
    db.add(email)
    await apply_outcome(db, email)
    db.commit()
    db.refresh(email)

    await publish("email.classified", EmailOut.model_validate(email).model_dump(mode="json"))
    return email
