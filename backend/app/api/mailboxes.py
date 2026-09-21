from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.oauth_google import ensure_google_access_token
from app.auth.oauth_microsoft import ensure_microsoft_access_token
from app.db import get_db
from app.models import EmailLabel, EmailMessage, MailboxConnection, Provider
from app.realtime.gmail_watch import stop_gmail_watch
from app.realtime.outlook_subscriptions import (
    delete_outlook_subscriptions,
    parse_outlook_subscription_ids,
)
from app.realtime.sse import publish
from app.schemas import MailboxLabelStatsOut, MailboxOut
from app.services.mailbox_cleanup import delete_emails_for_mailbox

router = APIRouter(prefix="/api/mailboxes", tags=["mailboxes"])


@router.get("", response_model=list[MailboxOut])
def list_mailboxes(db: Session = Depends(get_db)) -> list[MailboxConnection]:
    return (
        db.query(MailboxConnection)
        .filter(MailboxConnection.is_active.is_(True))
        .order_by(MailboxConnection.created_at.desc())
        .all()
    )


@router.get("/{mailbox_id}/label-stats", response_model=MailboxLabelStatsOut)
def mailbox_label_stats(
    mailbox_id: int,
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: Session = Depends(get_db),
) -> MailboxLabelStatsOut:
    mailbox = (
        db.query(MailboxConnection)
        .filter(MailboxConnection.id == mailbox_id, MailboxConnection.is_active.is_(True))
        .one_or_none()
    )
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be on or before date_to")

    start = datetime(date_from.year, date_from.month, date_from.day)
    end = datetime(date_to.year, date_to.month, date_to.day) + timedelta(days=1)
    valid = {item.value for item in EmailLabel}
    label_counts = {item: 0 for item in valid}
    rows = (
        db.query(EmailMessage.label, func.count(EmailMessage.id))
        .filter(
            EmailMessage.mailbox_id == mailbox_id,
            EmailMessage.received_at.is_not(None),
            EmailMessage.received_at >= start,
            EmailMessage.received_at < end,
        )
        .group_by(EmailMessage.label)
        .all()
    )
    total = 0
    for lab, count in rows:
        key = lab if lab in valid else EmailLabel.OTHERS.value
        n = int(count)
        label_counts[key] = label_counts.get(key, 0) + n
        total += n
    return MailboxLabelStatsOut(
        mailbox_id=mailbox_id,
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        total=total,
        label_counts=label_counts,
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
            await delete_outlook_subscriptions(
                token,
                parse_outlook_subscription_ids(mailbox.webhook.external_id),
            )
    except Exception:
        # Still disconnect locally even if remote cleanup fails.
        pass

    try:
        from app.services.mailbox_sync import request_stop_sync
        from app.services.reclassify import request_stop_reclassify

        await request_stop_sync(mailbox_id)
        await request_stop_reclassify(mailbox_id)
    except Exception:
        pass

    deleted_emails = delete_emails_for_mailbox(db, mailbox_id)
    mailbox.is_active = False
    db.commit()
    await publish("mailbox.disconnected", {"mailbox_id": mailbox_id, "deleted_emails": deleted_emails})
    return {"ok": True, "deleted_emails": deleted_emails}


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


@router.post("/{mailbox_id}/sync/stop")
async def stop_mailbox_sync(mailbox_id: int, db: Session = Depends(get_db)) -> dict:
    from app.services.mailbox_sync import request_stop_sync

    mailbox = (
        db.query(MailboxConnection)
        .filter(MailboxConnection.id == mailbox_id, MailboxConnection.is_active.is_(True))
        .one_or_none()
    )
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    status = await request_stop_sync(mailbox.id)
    return {"ok": True, **status}


@router.get("/{mailbox_id}/sync-status")
def mailbox_sync_status(mailbox_id: int) -> dict:
    from app.services.mailbox_sync import get_sync_status

    return get_sync_status(mailbox_id)


@router.post("/{mailbox_id}/reclassify")
async def reclassify_mailbox(mailbox_id: int, db: Session = Depends(get_db)) -> dict:
    from app.services.reclassify import start_mailbox_reclassify

    mailbox = (
        db.query(MailboxConnection)
        .filter(MailboxConnection.id == mailbox_id, MailboxConnection.is_active.is_(True))
        .one_or_none()
    )
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    status = await start_mailbox_reclassify(mailbox.id)
    return {"ok": True, **status}


@router.post("/{mailbox_id}/reclassify/stop")
async def stop_mailbox_reclassify(mailbox_id: int, db: Session = Depends(get_db)) -> dict:
    from app.services.reclassify import request_stop_reclassify

    mailbox = (
        db.query(MailboxConnection)
        .filter(MailboxConnection.id == mailbox_id, MailboxConnection.is_active.is_(True))
        .one_or_none()
    )
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")
    status = await request_stop_reclassify(mailbox.id)
    return {"ok": True, **status}


@router.get("/{mailbox_id}/reclassify-status")
def mailbox_reclassify_status(mailbox_id: int) -> dict:
    from app.services.reclassify import get_reclassify_status

    return get_reclassify_status(mailbox_id)
