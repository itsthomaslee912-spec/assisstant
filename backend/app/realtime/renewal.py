from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.auth.oauth_google import ensure_google_access_token
from app.auth.oauth_microsoft import ensure_microsoft_access_token
from app.db import SessionLocal
from app.models import MailboxConnection, Provider, WebhookSubscription
from app.realtime.gmail_watch import start_gmail_watch
from app.realtime.outlook_subscriptions import renew_outlook_subscription

logger = logging.getLogger(__name__)


async def renew_expiring_subscriptions() -> None:
    db: Session = SessionLocal()
    try:
        soon = datetime.now(timezone.utc) + timedelta(hours=12)
        webhooks = (
            db.query(WebhookSubscription)
            .filter(WebhookSubscription.expires_at.isnot(None))
            .filter(WebhookSubscription.expires_at < soon)
            .all()
        )
        for webhook in webhooks:
            mailbox = db.query(MailboxConnection).filter(MailboxConnection.id == webhook.mailbox_id).one_or_none()
            if mailbox is None or not mailbox.is_active:
                continue
            try:
                if mailbox.provider == Provider.GOOGLE.value:
                    token = await ensure_google_access_token(db, mailbox)
                    await start_gmail_watch(db, mailbox, token)
                elif mailbox.provider == Provider.MICROSOFT.value and webhook.external_id:
                    token = await ensure_microsoft_access_token(db, mailbox)
                    data = await renew_outlook_subscription(token, webhook.external_id)
                    exp = data.get("expirationDateTime")
                    if exp:
                        webhook.expires_at = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                        db.commit()
            except Exception:
                logger.exception("Failed renewing webhook for mailbox %s", mailbox.id)
    finally:
        db.close()


async def renewal_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await renew_expiring_subscriptions()
        except Exception:
            logger.exception("Renewal loop error")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=3600)
        except TimeoutError:
            continue
