from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.auth.oauth_google import ensure_google_access_token
from app.auth.oauth_microsoft import ensure_microsoft_access_token
from app.db import get_db
from app.email.gmail import gmail_get_message, gmail_send_message, split_mixed_plain_html
from app.email.outlook import outlook_get_message, outlook_send_message
from app.models import EmailLabel, EmailMessage, MailboxConnection, Provider
from app.schemas import EmailDetailOut, EmailOut, EmailPageOut, SendEmailIn, SendEmailOut

router = APIRouter(prefix="/api/emails", tags=["emails"])


@router.get("", response_model=EmailPageOut)
def list_emails(
    label: str | None = Query(default=None),
    mailbox_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None),
    before_received_at: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> EmailPageOut:
    valid = {item.value for item in EmailLabel}
    filtered = db.query(EmailMessage)
    if mailbox_id is not None:
        filtered = filtered.filter(EmailMessage.mailbox_id == mailbox_id)
    if label and label != "all" and label in valid:
        filtered = filtered.filter(EmailMessage.label == label)

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

    label_q = db.query(EmailMessage.label, func.count(EmailMessage.id))
    if mailbox_id is not None:
        label_q = label_q.filter(EmailMessage.mailbox_id == mailbox_id)
    label_counts = {item: 0 for item in valid}
    for lab, count in label_q.group_by(EmailMessage.label):
        key = lab if lab in valid else EmailLabel.OTHERS.value
        label_counts[key] = label_counts.get(key, 0) + int(count)

    mailbox_counts = {
        str(mid): int(count)
        for mid, count in db.query(EmailMessage.mailbox_id, func.count(EmailMessage.id)).group_by(
            EmailMessage.mailbox_id
        )
    }
    mailbox_unread_counts = {
        str(mid): int(count)
        for mid, count in db.query(EmailMessage.mailbox_id, func.count(EmailMessage.id))
        .filter(EmailMessage.is_read.is_not(True))
        .group_by(EmailMessage.mailbox_id)
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
    )


@router.get("/{email_id}", response_model=EmailDetailOut)
async def get_email(email_id: int, db: Session = Depends(get_db)) -> EmailMessage:
    email = db.query(EmailMessage).filter(EmailMessage.id == email_id).one_or_none()
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
                elif mailbox.provider == Provider.MICROSOFT.value:
                    token = await ensure_microsoft_access_token(db, mailbox)
                    raw = await outlook_get_message(token, email.provider_message_id)
                    from app.email.outlook import normalize_outlook_message

                    normalized = normalize_outlook_message(raw)
                    email.body_text = normalized.get("body_text") or email.body_text or ""
                    email.body_html = normalized.get("body_html") or email.body_html or ""
                    if normalized.get("snippet"):
                        email.snippet = normalized["snippet"][:1000]
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Could not load email body: {exc}") from exc

    if not email.is_read:
        email.is_read = True
    db.commit()
    db.refresh(email)
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
