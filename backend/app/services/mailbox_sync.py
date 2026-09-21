from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.auth.oauth_google import ensure_google_access_token
from app.auth.oauth_microsoft import ensure_microsoft_access_token
from app.config import get_settings
from app.email.gmail import (
    gmail_get_message,
    gmail_get_messages,
    gmail_list_folder_id_map,
    gmail_list_history,
    gmail_list_inbox_message_ids,
    normalize_gmail_message,
)
from app.email.folders import folder_from_outlook_well_known
from app.email.outlook import (
    normalize_outlook_message,
    outlook_attach_folder,
    outlook_get_message,
    outlook_list_recent,
)
from app.models import EmailMessage, MailboxConnection, Provider
from app.realtime.gmail_watch import start_gmail_watch
from app.realtime.outlook_subscriptions import create_outlook_subscription, parse_outlook_subscription_ids
from app.realtime.sse import publish
from app.services.ingest import ingest_normalized_message

logger = logging.getLogger(__name__)

FETCH_CHUNK = 15
GMAIL_CONCURRENCY = 4

_jobs: dict[int, dict[str, Any]] = {}
_running: set[int] = set()
_cancel_requested: set[int] = set()
_job_lock = asyncio.Lock()


def _should_stop(mailbox_id: int) -> bool:
    return mailbox_id in _cancel_requested


def get_sync_status(mailbox_id: int) -> dict[str, Any]:
    return dict(
        _jobs.get(
            mailbox_id,
            {
                "mailbox_id": mailbox_id,
                "state": "idle",
                "listed": 0,
                "skipped": 0,
                "imported": 0,
                "failed": 0,
                "total": 0,
                "message": "",
            },
        )
    )


def _set_job(mailbox_id: int, **fields: Any) -> dict[str, Any]:
    job = _jobs.get(mailbox_id) or {"mailbox_id": mailbox_id}
    job.update(fields)
    _jobs[mailbox_id] = job
    return job


async def start_mailbox_sync(mailbox_id: int) -> dict[str, Any]:
    async with _job_lock:
        current = _jobs.get(mailbox_id)
        if mailbox_id in _running or (current and current.get("state") == "running"):
            return get_sync_status(mailbox_id)
        _cancel_requested.discard(mailbox_id)
        _running.add(mailbox_id)
        job = _set_job(
            mailbox_id,
            state="running",
            listed=0,
            skipped=0,
            imported=0,
            failed=0,
            total=0,
            message="Starting inbox sync...",
        )
    asyncio.create_task(_run_sync_job(mailbox_id))
    return dict(job)


async def request_stop_sync(mailbox_id: int) -> dict[str, Any]:
    async with _job_lock:
        if mailbox_id not in _running:
            return get_sync_status(mailbox_id)
        _cancel_requested.add(mailbox_id)
        job = _set_job(mailbox_id, message="Stopping sync…")
    await publish("sync.progress", dict(job))
    return dict(job)


async def _run_sync_job(mailbox_id: int) -> None:
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        mailbox = (
            db.query(MailboxConnection)
            .filter(MailboxConnection.id == mailbox_id, MailboxConnection.is_active.is_(True))
            .one_or_none()
        )
        if mailbox is None:
            _set_job(mailbox_id, state="error", message="Mailbox not found")
            await publish("sync.done", get_sync_status(mailbox_id))
            return
        await bootstrap_mailbox(db, mailbox)
        imported = _jobs[mailbox_id].get("imported", 0)
        if _should_stop(mailbox_id):
            job = _set_job(
                mailbox_id,
                state="stopped",
                message=f"Sync stopped — imported {imported} new messages",
            )
        else:
            job = _set_job(
                mailbox_id,
                state="done",
                message=f"Synced {imported} new messages",
            )
        await publish("sync.done", dict(job))
    except Exception as exc:
        logger.exception("Mailbox sync failed for %s", mailbox_id)
        job = _set_job(mailbox_id, state="error", message=str(exc)[:300])
        await publish("sync.done", dict(job))
    finally:
        _running.discard(mailbox_id)
        _cancel_requested.discard(mailbox_id)
        db.close()


async def bootstrap_mailbox(db: Session, mailbox: MailboxConnection, *, initial_sync: int | None = None) -> None:
    limit = initial_sync if initial_sync is not None else get_settings().mail_sync_max
    if mailbox.provider == Provider.GOOGLE.value:
        await _sync_gmail(db, mailbox, limit)
        if _should_stop(mailbox.id):
            return
        try:
            token = await ensure_google_access_token(db, mailbox)
            await start_gmail_watch(db, mailbox, token)
        except Exception:
            logger.exception("Gmail watch registration failed for mailbox %s", mailbox.id)
    elif mailbox.provider == Provider.MICROSOFT.value:
        await _sync_outlook(db, mailbox, limit)
        if _should_stop(mailbox.id):
            return
        try:
            token = await ensure_microsoft_access_token(db, mailbox)
            await create_outlook_subscription(db, mailbox, token)
        except Exception:
            logger.exception("Outlook subscription failed for mailbox %s", mailbox.id)


async def _existing_ids(db: Session, mailbox_id: int) -> set[str]:
    rows = db.query(EmailMessage.provider_message_id).filter(EmailMessage.mailbox_id == mailbox_id).all()
    return {row[0] for row in rows if row[0]}


def _stamp_listed_outlook_folders(db: Session, mailbox_id: int, messages: list[dict]) -> None:
    id_to_folder = {
        str(raw["id"]): folder_from_outlook_well_known(str(raw.get("_mail_folder") or "inbox"))
        for raw in messages
        if raw.get("id")
    }
    _apply_folder_stamps(db, mailbox_id, id_to_folder)


def _stamp_listed_gmail_folders(db: Session, mailbox_id: int, id_to_folder: dict[str, str]) -> None:
    _apply_folder_stamps(db, mailbox_id, id_to_folder)


def _apply_folder_stamps(db: Session, mailbox_id: int, id_to_folder: dict[str, str]) -> None:
    if not id_to_folder:
        return
    ids = list(id_to_folder)
    changed = False
    for start in range(0, len(ids), 400):
        chunk = ids[start : start + 400]
        rows = (
            db.query(EmailMessage)
            .filter(
                EmailMessage.mailbox_id == mailbox_id,
                EmailMessage.provider_message_id.in_(chunk),
            )
            .all()
        )
        for row in rows:
            next_folder = id_to_folder.get(row.provider_message_id)
            if next_folder and row.folder != next_folder:
                row.folder = next_folder
                changed = True
    if changed:
        db.commit()


async def _publish_progress(mailbox_id: int, **fields: Any) -> None:
    job = _set_job(mailbox_id, **fields)
    await publish("sync.progress", dict(job))


async def _sync_gmail(db: Session, mailbox: MailboxConnection, limit: int) -> None:
    token = await ensure_google_access_token(db, mailbox)
    await _publish_progress(mailbox.id, state="running", message="Listing Inbox, Spam, Trash, and Archive...")
    ids, estimate = await gmail_list_inbox_message_ids(token, max_results=limit)
    existing = await _existing_ids(db, mailbox.id)
    if existing:
        folder_map = await gmail_list_folder_id_map(token, max_results=limit)
        _stamp_listed_gmail_folders(db, mailbox.id, folder_map)
    new_ids = [mid for mid in ids if mid not in existing]
    imported = 0
    failed = 0
    await _publish_progress(
        mailbox.id,
        listed=len(ids),
        skipped=len(ids) - len(new_ids),
        imported=0,
        failed=0,
        total=max(estimate, len(ids)),
        message=f"Downloading {len(new_ids)} new messages...",
    )
    logger.info(
        "Gmail sync mailbox=%s listed=%s new=%s skipped=%s estimate=%s",
        mailbox.id,
        len(ids),
        len(new_ids),
        len(ids) - len(new_ids),
        estimate,
    )

    for start in range(0, len(new_ids), FETCH_CHUNK):
        if _should_stop(mailbox.id):
            await _publish_progress(
                mailbox.id,
                imported=imported,
                failed=failed,
                skipped=len(ids) - len(new_ids),
                listed=len(ids),
                total=max(estimate, len(ids)),
                message="Stopping sync…",
            )
            return
        token = await ensure_google_access_token(db, mailbox)
        chunk = new_ids[start : start + FETCH_CHUNK]
        raws = await gmail_get_messages(token, chunk, concurrency=GMAIL_CONCURRENCY)
        got = {raw.get("id"): raw for raw in raws if raw.get("id")}
        for mid in chunk:
            raw = got.get(mid)
            if raw is None:
                failed += 1
                continue
            email = await ingest_normalized_message(
                db, mailbox, normalize_gmail_message(raw)
            )
            if email:
                imported += 1
            if (imported + failed) % 10 == 0 or imported + failed == len(new_ids):
                await _publish_progress(
                    mailbox.id,
                    imported=imported,
                    failed=failed,
                    skipped=len(ids) - len(new_ids),
                    listed=len(ids),
                    total=max(estimate, len(ids)),
                    message=f"Imported {imported} of {len(new_ids)} new messages",
                )
        await asyncio.sleep(0.8)
    await _publish_progress(
        mailbox.id,
        imported=imported,
        failed=failed,
        skipped=len(ids) - len(new_ids),
        listed=len(ids),
        total=max(estimate, len(ids)),
        message=f"Imported {imported} of {len(new_ids)} new messages",
    )


async def _sync_outlook(db: Session, mailbox: MailboxConnection, limit: int) -> None:
    token = await ensure_microsoft_access_token(db, mailbox)
    await _publish_progress(mailbox.id, state="running", message="Listing Inbox, Junk, Deleted Items, and Archive...")
    messages = await outlook_list_recent(token, top=limit)
    existing = await _existing_ids(db, mailbox.id)
    _stamp_listed_outlook_folders(db, mailbox.id, messages)
    new_messages = [raw for raw in messages if (raw.get("id") or "") not in existing]
    imported = 0
    await _publish_progress(
        mailbox.id,
        listed=len(messages),
        skipped=len(messages) - len(new_messages),
        imported=0,
        failed=0,
        total=len(messages),
        message=f"Importing {len(new_messages)} new messages...",
    )
    for raw in new_messages:
        if _should_stop(mailbox.id):
            await _publish_progress(
                mailbox.id,
                imported=imported,
                skipped=len(messages) - len(new_messages),
                listed=len(messages),
                total=len(messages),
                message="Stopping sync…",
            )
            return
        email = await ingest_normalized_message(
            db, mailbox, normalize_outlook_message(raw)
        )
        if email:
            imported += 1
        if imported % 20 == 0:
            await _publish_progress(
                mailbox.id,
                imported=imported,
                skipped=len(messages) - len(new_messages),
                listed=len(messages),
                total=len(messages),
                message=f"Imported {imported} of {len(new_messages)} new messages",
            )
    await _publish_progress(
        mailbox.id,
        imported=imported,
        skipped=len(messages) - len(new_messages),
        listed=len(messages),
        total=len(messages),
        message=f"Imported {imported} of {len(new_messages)} new messages",
    )


async def process_gmail_notification(db: Session, email_address: str, history_id: str | None) -> int:
    mailbox = (
        db.query(MailboxConnection)
        .filter(
            MailboxConnection.provider == Provider.GOOGLE.value,
            MailboxConnection.email_address == email_address,
            MailboxConnection.is_active.is_(True),
        )
        .one_or_none()
    )
    if mailbox is None:
        mailbox = (
            db.query(MailboxConnection)
            .filter(
                MailboxConnection.provider == Provider.GOOGLE.value,
                MailboxConnection.is_active.is_(True),
            )
            .first()
        )
    if mailbox is None:
        logger.warning("No Google mailbox for notification email=%s", email_address)
        return 0

    token = await ensure_google_access_token(db, mailbox)
    start_id = mailbox.sync_cursor
    created = 0
    if start_id:
        history = await gmail_list_history(token, start_id)
        message_ids: list[str] = []
        for item in history.get("history") or []:
            for added in item.get("messagesAdded") or []:
                msg = added.get("message") or {}
                labels = {str(label).upper() for label in (msg.get("labelIds") or [])}
                if labels & {"SENT", "DRAFT"}:
                    continue
                mid = msg.get("id")
                if mid:
                    message_ids.append(mid)
        for mid in dict.fromkeys(message_ids):
            raw = await gmail_get_message(token, mid)
            email = await ingest_normalized_message(db, mailbox, normalize_gmail_message(raw))
            if email:
                created += 1
        if history.get("historyId"):
            mailbox.sync_cursor = str(history["historyId"])
            db.commit()
    elif history_id:
        mailbox.sync_cursor = str(history_id)
        db.commit()
    return created


async def process_outlook_notification(db: Session, subscription_id: str, message_id: str) -> int:
    mailbox = None
    for conn in db.query(MailboxConnection).filter(MailboxConnection.is_active.is_(True)).all():
        if conn.webhook and subscription_id in parse_outlook_subscription_ids(conn.webhook.external_id):
            mailbox = conn
            break
    if mailbox is None:
        mailbox = (
            db.query(MailboxConnection)
            .filter(
                MailboxConnection.provider == Provider.MICROSOFT.value,
                MailboxConnection.is_active.is_(True),
            )
            .first()
        )
    if mailbox is None:
        logger.warning("No Outlook mailbox for subscription %s", subscription_id)
        return 0

    token = await ensure_microsoft_access_token(db, mailbox)
    raw = await outlook_get_message(token, message_id)
    raw = await outlook_attach_folder(token, raw)
    email = await ingest_normalized_message(db, mailbox, normalize_outlook_message(raw))
    return 1 if email else 0
