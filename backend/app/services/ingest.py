from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.classify.openai_classifier import classify_email
from app.email.folders import normalize_folder
from app.models import EmailMessage, MailboxConnection
from app.realtime.sse import publish
from app.schemas import EmailOut

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
        folder = normalize_folder(normalized.get("folder"))
        if existing.folder != folder:
            existing.folder = folder
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
        received_at=normalized.get("received_at"),
        snippet=(normalized.get("snippet") or "")[:1000],
        body_text=normalized.get("body_text") or "",
        body_html=normalized.get("body_html") or "",
        label=classification.label,
        confidence=classification.confidence,
        openai_response_id=classification.response_id,
        folder=normalize_folder(normalized.get("folder")),
    )
    db.add(email)
    db.commit()
    db.refresh(email)

    await publish("email.classified", EmailOut.model_validate(email).model_dump())
    return email
