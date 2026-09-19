from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.classify.openai_classifier import classify_email
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
        return None

    try:
        classification = await classify_email(
            subject=normalized.get("subject") or "",
            sender=normalized.get("sender") or "",
            body_text=normalized.get("body_text") or "",
            snippet=normalized.get("snippet") or "",
            force_openai=force_openai,
            use_openai=use_openai,
        )
    except Exception:
        logger.exception("Classification failed; defaulting to others")
        from app.models import EmailLabel
        from app.schemas import ClassificationResult

        classification = ClassificationResult(label=EmailLabel.OTHERS.value)

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
    )
    db.add(email)
    db.commit()
    db.refresh(email)

    await publish("email.classified", EmailOut.model_validate(email).model_dump())
    return email
