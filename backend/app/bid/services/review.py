from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from openai import AsyncOpenAI
from sqlalchemy.orm import Session, joinedload

from app.bid.models import JobApplication, JobListing, Profile, ReviewStatus
from app.bid.util import json_int_list, profile_email, utcnow
from app.config import get_settings
from app.models import EmailMessage, MailboxConnection

logger = logging.getLogger(__name__)

FIND_SYSTEM = """You match a job application to recruiting emails.
Return JSON only:
{"matches":[{"email_id":123,"confidence":0.0,"reason":"..."}]}
Include an email only if it is about THIS specific job (same company and/or role and/or apply URL).
If none match, return {"matches":[]}.
Do not invent email_id values. Use only ids from the payload."""

PICK_SYSTEM = """Several emails might relate to a job application.
Pick the single email that is the confirmation / application-received note for THIS job.
Return JSON: {"email_id":123,"confidence":0.0,"reason":"..."} or {"email_id":null,"confidence":0,"reason":"..."} if you cannot tell.
Do not invent ids."""


def _email_payload(messages: list[EmailMessage]) -> list[dict]:
    rows = []
    for msg in messages:
        rows.append(
            {
                "email_id": msg.id,
                "subject": msg.subject,
                "sender": msg.sender,
                "received_at": msg.received_at.isoformat() if msg.received_at else None,
                "label": msg.label,
                "snippet": (msg.snippet or "")[:800],
                "body": (msg.body_text or "")[:2500],
            }
        )
    return rows


def _job_payload(listing: JobListing, profile: Profile) -> dict:
    return {
        "company": listing.company,
        "title": listing.title,
        "url": listing.url,
        "profile_name": profile.name,
        "profile_email": profile_email(profile),
    }


async def _chat_json(system: str, user: dict) -> dict:
    settings = get_settings()
    if not settings.openai_api_key:
        return {}
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user)},
        ],
    )
    content = response.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def load_mailbox_emails(db: Session, email_address: str, limit: int = 80) -> list[EmailMessage]:
    if not email_address:
        return []
    mailbox = (
        db.query(MailboxConnection)
        .filter(MailboxConnection.email_address == email_address, MailboxConnection.is_active.is_(True))
        .one_or_none()
    )
    if mailbox is None:
        mailbox = (
            db.query(MailboxConnection)
            .filter(MailboxConnection.email_address == email_address)
            .one_or_none()
        )
    if mailbox is None:
        return []
    return (
        db.query(EmailMessage)
        .filter(EmailMessage.mailbox_id == mailbox.id)
        .order_by(EmailMessage.received_at.desc().nullslast(), EmailMessage.id.desc())
        .limit(limit)
        .all()
    )


async def review_application(db: Session, application: JobApplication) -> JobApplication:
    listing = application.listing or db.get(JobListing, application.listing_id)
    if listing is None:
        application.review_status = ReviewStatus.FAILED.value
        application.review_notes = "Job listing missing"
        application.reviewed_at = utcnow()
        application.needs_human_review = False
        return application
    profile = listing.profile or db.get(Profile, listing.profile_id)
    if profile is None:
        application.review_status = ReviewStatus.FAILED.value
        application.review_notes = "Profile missing"
        application.reviewed_at = utcnow()
        return application

    address = profile_email(profile)
    emails = load_mailbox_emails(db, address)
    if not emails:
        application.review_status = ReviewStatus.FAILED.value
        application.review_notes = (
            f"No emails found for profile address {address or '(empty)'}. "
            "Connect that mailbox in Email Checker, then review again."
        )
        application.reviewed_at = utcnow()
        application.needs_human_review = False
        application.candidate_email_ids = "[]"
        application.matched_email_id = None
        return application

    settings = get_settings()
    if not settings.openai_api_key:
        application.needs_human_review = True
        application.review_status = ReviewStatus.PENDING.value
        application.review_notes = "OPENAI_API_KEY missing — queued for human review"
        application.candidate_email_ids = json.dumps([e.id for e in emails[:12]])
        application.reviewed_at = None
        return application

    found = await _chat_json(
        FIND_SYSTEM,
        {"job": _job_payload(listing, profile), "emails": _email_payload(emails)},
    )
    matches = found.get("matches") if isinstance(found.get("matches"), list) else []
    valid_ids = {msg.id for msg in emails}
    match_ids: list[int] = []
    for item in matches:
        if not isinstance(item, dict):
            continue
        try:
            eid = int(item.get("email_id"))
        except (TypeError, ValueError):
            continue
        if eid in valid_ids and eid not in match_ids:
            match_ids.append(eid)

    if not match_ids:
        application.review_status = ReviewStatus.FAILED.value
        application.needs_human_review = False
        application.matched_email_id = None
        application.candidate_email_ids = "[]"
        application.reviewed_at = utcnow()
        application.review_notes = "No matching application email found"
        return application

    if len(match_ids) == 1:
        application.review_status = ReviewStatus.PASSED.value
        application.needs_human_review = False
        application.matched_email_id = match_ids[0]
        application.candidate_email_ids = json.dumps(match_ids)
        application.reviewed_at = utcnow()
        application.review_notes = "Matched a single application email"
        return application

    picked = await _chat_json(
        PICK_SYSTEM,
        {
            "job": _job_payload(listing, profile),
            "emails": _email_payload([m for m in emails if m.id in set(match_ids)]),
        },
    )
    pick_id = picked.get("email_id")
    confidence = float(picked.get("confidence") or 0)
    try:
        pick_int = int(pick_id) if pick_id is not None else None
    except (TypeError, ValueError):
        pick_int = None

    if pick_int in set(match_ids) and confidence >= 0.6:
        application.review_status = ReviewStatus.PASSED.value
        application.needs_human_review = False
        application.matched_email_id = pick_int
        application.candidate_email_ids = json.dumps(match_ids)
        application.reviewed_at = utcnow()
        application.review_notes = str(picked.get("reason") or "Disambiguated among several emails")
        return application

    application.review_status = ReviewStatus.PENDING.value
    application.needs_human_review = True
    application.matched_email_id = None
    application.candidate_email_ids = json.dumps(match_ids)
    application.reviewed_at = None
    application.review_notes = str(picked.get("reason") or "Several emails matched; needs human review")
    return application
