from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.oauth_google import ensure_google_access_token
from app.auth.oauth_microsoft import ensure_microsoft_access_token
from app.db import get_db
from app.models import MailboxConnection, Provider
from app.realtime.gmail_watch import stop_gmail_watch
from app.realtime.outlook_subscriptions import delete_outlook_subscription
from app.schemas import MailboxOut

router = APIRouter(prefix="/api/mailboxes", tags=["mailboxes"])


@router.get("", response_model=list[MailboxOut])
def list_mailboxes(db: Session = Depends(get_db)) -> list[MailboxConnection]:
    return (
        db.query(MailboxConnection)
        .filter(MailboxConnection.is_active.is_(True))
        .order_by(MailboxConnection.created_at.desc())
        .all()
    )


@router.delete("/{mailbox_id}")
async def disconnect_mailbox(mailbox_id: int, db: Session = Depends(get_db)) -> dict:
    mailbox = db.query(MailboxConnection).filter(MailboxConnection.id == mailbox_id).one_or_none()
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    try:
        if mailbox.provider == Provider.GOOGLE.value:
            token = await ensure_google_access_token(db, mailbox)
            await stop_gmail_watch(token)
        elif mailbox.provider == Provider.MICROSOFT.value and mailbox.webhook and mailbox.webhook.external_id:
            token = await ensure_microsoft_access_token(db, mailbox)
            await delete_outlook_subscription(token, mailbox.webhook.external_id)
    except Exception:
        # Still disconnect locally even if remote cleanup fails.
        pass

    mailbox.is_active = False
    db.commit()
    return {"ok": True}


@router.post("/{mailbox_id}/sync")
async def sync_mailbox(mailbox_id: int, db: Session = Depends(get_db)) -> dict:
    from app.services.mailbox_sync import start_mailbox_sync

    mailbox = (
        db.query(MailboxConnection)
        .filter(MailboxConnection.id == mailbox_id, MailboxConnection.is_active.is_(True))
        .one_or_none()
    )
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    status = await start_mailbox_sync(mailbox.id)
    return {"ok": True, **status}


@router.get("/{mailbox_id}/sync-status")
def mailbox_sync_status(mailbox_id: int) -> dict:
    from app.services.mailbox_sync import get_sync_status

    return get_sync_status(mailbox_id)


@router.post("/{mailbox_id}/reclassify")
async def reclassify_mailbox(mailbox_id: int, db: Session = Depends(get_db)) -> dict:
    from app.classify.openai_classifier import classify_email
    from app.models import EmailMessage

    mailbox = (
        db.query(MailboxConnection)
        .filter(MailboxConnection.id == mailbox_id, MailboxConnection.is_active.is_(True))
        .one_or_none()
    )
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    emails = (
        db.query(EmailMessage)
        .filter(EmailMessage.mailbox_id == mailbox_id)
        .order_by(EmailMessage.id.desc())
        .all()
    )
    updated = 0
    for email in emails:
        result = await classify_email(
            subject=email.subject or "",
            sender=email.sender or "",
            body_text=email.body_text or "",
            snippet=email.snippet or "",
            force_openai=True,
        )
        if email.label != result.label or email.confidence != result.confidence:
            email.label = result.label
            email.confidence = result.confidence
            email.openai_response_id = result.response_id
            updated += 1
    db.commit()
    return {"ok": True, "updated": updated, "total": len(emails)}
