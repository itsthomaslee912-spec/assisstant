from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.auth.oauth_google import ensure_google_access_token
from app.auth.oauth_microsoft import ensure_microsoft_access_token
from app.db import get_db
from app.email.gmail import (
    gmail_get_message,
    gmail_mark_read,
    gmail_mark_read_many,
    gmail_send_message,
    split_mixed_plain_html,
)
from app.email.outlook import (
    outlook_attach_folder,
    outlook_get_message,
    outlook_mark_read,
    outlook_send_message,
)
from app.email.folders import VALID_FOLDERS
from app.models import ClassifyCorrection, EmailLabel, EmailMessage, MailboxConnection, MailFolder, Provider
from app.realtime.sse import publish
from app.schemas import (
    EmailDetailOut,
    EmailLabelUpdateIn,
    EmailOut,
    EmailPageOut,
    MarkAllReadOut,
    SendEmailIn,
    SendEmailOut,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/emails", tags=["emails"])


def _from_active_mailbox(query):
    return query.join(
        MailboxConnection, MailboxConnection.id == EmailMessage.mailbox_id
    ).filter(MailboxConnection.is_active.is_(True))


def _email_from_active_mailbox(db: Session, email_id: int) -> EmailMessage | None:
    return (
        _from_active_mailbox(db.query(EmailMessage))
        .filter(EmailMessage.id == email_id)
        .one_or_none()
    )


@router.get("", response_model=EmailPageOut)
def list_emails(
    label: str | None = Query(default=None),
    mailbox_id: int | None = Query(default=None),
    folder: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None),
    before_received_at: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> EmailPageOut:
    valid = {item.value for item in EmailLabel}
    filtered = _from_active_mailbox(db.query(EmailMessage))
    if mailbox_id is not None:
        filtered = filtered.filter(EmailMessage.mailbox_id == mailbox_id)
    if label and label != "all" and label in valid:
        filtered = filtered.filter(EmailMessage.label == label)
    if folder and folder != "all" and folder in VALID_FOLDERS:
        filtered = filtered.filter(EmailMessage.folder == folder)

    total = filtered.count()
    page_q = filtered.order_by(EmailMessage.received_at.desc(), EmailMessage.id.desc())
    if before_id is not None:
        if before_received_at is not None:
            cursor_at = before_received_at
            if cursor_at.tzinfo is not None:
                cursor_at = cursor_at.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                cursor_at = cursor_at.replace(tzinfo=None)
            page_q = page_q.filter(
                or_(
                    EmailMessage.received_at < cursor_at,
                    and_(EmailMessage.received_at == cursor_at, EmailMessage.id < before_id),
                    EmailMessage.received_at.is_(None),
                )
            )
        else:
            page_q = page_q.filter(
                and_(EmailMessage.received_at.is_(None), EmailMessage.id < before_id)
            )
    rows = page_q.limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    for row in rows:
        if row.label not in valid:
            row.label = EmailLabel.OTHERS.value
        if row.folder not in VALID_FOLDERS:
            row.folder = MailFolder.INBOX.value

    label_q = _from_active_mailbox(db.query(EmailMessage.label, func.count(EmailMessage.id)))
    if mailbox_id is not None:
        label_q = label_q.filter(EmailMessage.mailbox_id == mailbox_id)
    label_counts = {item: 0 for item in valid}
    for lab, count in label_q.group_by(EmailMessage.label):
        key = lab if lab in valid else EmailLabel.OTHERS.value
        label_counts[key] = label_counts.get(key, 0) + int(count)

    folder_q = _from_active_mailbox(db.query(EmailMessage.folder, func.count(EmailMessage.id)))
    if mailbox_id is not None:
        folder_q = folder_q.filter(EmailMessage.mailbox_id == mailbox_id)
    folder_counts = {item: 0 for item in VALID_FOLDERS}
    for fold, count in folder_q.group_by(EmailMessage.folder):
        key = fold if fold in VALID_FOLDERS else MailFolder.INBOX.value
        folder_counts[key] = folder_counts.get(key, 0) + int(count)

    mailbox_count_q = _from_active_mailbox(
        db.query(EmailMessage.mailbox_id, func.count(EmailMessage.id))
    )
    mailbox_counts = {
        str(mid): int(count) for mid, count in mailbox_count_q.group_by(EmailMessage.mailbox_id)
    }
    mailbox_unread_q = _from_active_mailbox(
        db.query(EmailMessage.mailbox_id, func.count(EmailMessage.id))
    ).filter(EmailMessage.is_read.is_not(True))
    mailbox_unread_counts = {
        str(mid): int(count) for mid, count in mailbox_unread_q.group_by(EmailMessage.mailbox_id)
    }

    return EmailPageOut(
        items=[EmailOut.model_validate(row) for row in rows],
        next_cursor=rows[-1].id if rows else None,
        next_received_at=rows[-1].received_at if rows else None,
        has_more=has_more,
        total=total,
        label_counts=label_counts,
        mailbox_counts=mailbox_counts,
        mailbox_unread_counts=mailbox_unread_counts,
        folder_counts=folder_counts,
    )


@router.post("/mark-all-read", response_model=MarkAllReadOut)
async def mark_all_read(
    mailbox_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> MarkAllReadOut:
    filtered = _from_active_mailbox(db.query(EmailMessage)).filter(EmailMessage.is_read.is_not(True))
    if mailbox_id is not None:
        filtered = filtered.filter(EmailMessage.mailbox_id == mailbox_id)
    unread = filtered.all()
    if not unread:
        return MarkAllReadOut(marked=0)

    mailbox_ids = {row.mailbox_id for row in unread}
    mailboxes = {
        row.id: row
        for row in db.query(MailboxConnection).filter(MailboxConnection.id.in_(mailbox_ids)).all()
    }
    grouped: dict[int, list[str]] = {}
    for row in unread:
        grouped.setdefault(row.mailbox_id, []).append(row.provider_message_id)

    for mid, message_ids in grouped.items():
        mailbox = mailboxes.get(mid)
        if mailbox is None:
            continue
        try:
            if mailbox.provider == Provider.GOOGLE.value:
                token = await ensure_google_access_token(db, mailbox)
                await gmail_mark_read_many(token, message_ids)
            elif mailbox.provider == Provider.MICROSOFT.value:
                token = await ensure_microsoft_access_token(db, mailbox)
                for message_id in message_ids:
                    await outlook_mark_read(token, message_id)
        except Exception:
            logger.exception(
                "Failed to mark provider messages read mailbox_id=%s count=%s",
                mid,
                len(message_ids),
            )

    for row in unread:
        row.is_read = True
    db.commit()
    return MarkAllReadOut(marked=len(unread))


@router.get("/{email_id}", response_model=EmailDetailOut)
async def get_email(email_id: int, db: Session = Depends(get_db)) -> EmailMessage:
    email = _email_from_active_mailbox(db, email_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    html = (email.body_html or "").strip()
    text = (email.body_text or "").strip()
    if text and not html:
        plain, extracted = split_mixed_plain_html(text)
        if extracted:
            email.body_text = plain
            email.body_html = extracted
            html = extracted
            text = plain

    has_body = bool(html or text)
    if not has_body:
        mailbox = (
            db.query(MailboxConnection)
            .filter(MailboxConnection.id == email.mailbox_id, MailboxConnection.is_active.is_(True))
            .one_or_none()
        )
        if mailbox is not None:
            try:
                if mailbox.provider == Provider.GOOGLE.value:
                    token = await ensure_google_access_token(db, mailbox)
                    raw = await gmail_get_message(token, email.provider_message_id)
                    from app.email.gmail import normalize_gmail_message

                    normalized = normalize_gmail_message(raw)
                    email.body_text = normalized.get("body_text") or email.body_text or ""
                    email.body_html = normalized.get("body_html") or email.body_html or ""
                    if normalized.get("snippet"):
                        email.snippet = normalized["snippet"][:1000]
                    if normalized.get("folder"):
                        email.folder = normalized["folder"]
                elif mailbox.provider == Provider.MICROSOFT.value:
                    token = await ensure_microsoft_access_token(db, mailbox)
                    raw = await outlook_get_message(token, email.provider_message_id)
                    raw = await outlook_attach_folder(token, raw)
                    from app.email.outlook import normalize_outlook_message

                    normalized = normalize_outlook_message(raw)
                    email.body_text = normalized.get("body_text") or email.body_text or ""
                    email.body_html = normalized.get("body_html") or email.body_html or ""
                    if normalized.get("snippet"):
                        email.snippet = normalized["snippet"][:1000]
                    if normalized.get("folder"):
                        email.folder = normalized["folder"]
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Could not load email body: {exc}") from exc

    if not email.is_read:
        mailbox = (
            db.query(MailboxConnection)
            .filter(MailboxConnection.id == email.mailbox_id, MailboxConnection.is_active.is_(True))
            .one_or_none()
        )
        if mailbox is not None:
            try:
                if mailbox.provider == Provider.GOOGLE.value:
                    token = await ensure_google_access_token(db, mailbox)
                    await gmail_mark_read(token, email.provider_message_id)
                elif mailbox.provider == Provider.MICROSOFT.value:
                    token = await ensure_microsoft_access_token(db, mailbox)
                    await outlook_mark_read(token, email.provider_message_id)
            except Exception:
                logger.exception(
                    "Failed to mark provider message read email_id=%s mailbox_id=%s",
                    email.id,
                    email.mailbox_id,
                )
        email.is_read = True
    if email.label not in {item.value for item in EmailLabel}:
        email.label = EmailLabel.OTHERS.value
    db.commit()
    db.refresh(email)
    return email


TRAINING_BODY_CAP = 4000


@router.patch("/{email_id}/label", response_model=EmailDetailOut)
async def update_email_label(
    email_id: int,
    payload: EmailLabelUpdateIn,
    db: Session = Depends(get_db),
) -> EmailMessage:
    email = _email_from_active_mailbox(db, email_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    previous_label = email.label
    new_label = payload.label
    if previous_label != new_label:
        if payload.save_training:
            body = (email.body_text or email.snippet or "")[:TRAINING_BODY_CAP]
            db.add(
                ClassifyCorrection(
                    email_id=email.id,
                    previous_label=previous_label,
                    corrected_label=new_label,
                    subject=email.subject or "",
                    sender=email.sender or "",
                    snippet=email.snippet or "",
                    body_text=body,
                )
            )
        email.label = new_label

    email.human_corrected = True
    db.commit()
    db.refresh(email)

    payload_out = EmailOut.model_validate(email).model_dump()
    payload_out["previous_label"] = previous_label
    payload_out["updated"] = previous_label != new_label
    await publish("email.classified", payload_out)
    return email


@router.post("/send", response_model=SendEmailOut)
async def send_email(payload: SendEmailIn, db: Session = Depends(get_db)) -> SendEmailOut:
    mailbox = (
        db.query(MailboxConnection)
        .filter(
            MailboxConnection.id == payload.mailbox_id,
            MailboxConnection.is_active.is_(True),
        )
        .one_or_none()
    )
    if mailbox is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    to_address = payload.to_address.strip()
    if "@" not in to_address:
        raise HTTPException(status_code=400, detail="Invalid recipient email")

    if mailbox.provider == Provider.GOOGLE.value:
        token = await ensure_google_access_token(db, mailbox)
        result = await gmail_send_message(
            token,
            to_address=to_address,
            subject=payload.subject.strip() or "(no subject)",
            body_text=payload.body_text,
            from_name=mailbox.display_name,
            from_email=mailbox.email_address,
        )
        return SendEmailOut(ok=True, provider_message_id=result.get("id"))

    if mailbox.provider == Provider.MICROSOFT.value:
        token = await ensure_microsoft_access_token(db, mailbox)
        await outlook_send_message(
            token,
            to_address=to_address,
            subject=payload.subject.strip() or "(no subject)",
            body_text=payload.body_text,
        )
        return SendEmailOut(ok=True, provider_message_id=None)

    raise HTTPException(status_code=400, detail="Unsupported provider")
