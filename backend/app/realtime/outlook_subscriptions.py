from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MailboxConnection, Provider, WebhookSubscription

GRAPH = "https://graph.microsoft.com/v1.0"


async def create_outlook_subscription(
    db: Session, mailbox: MailboxConnection, access_token: str
) -> WebhookSubscription:
    settings = get_settings()
    notification_url = f"{settings.webhook_base_url.rstrip('/')}/api/webhooks/outlook"
    expiration = datetime.now(timezone.utc) + timedelta(hours=70)

    payload = {
        "changeType": "created",
        "notificationUrl": notification_url,
        "resource": "me/mailFolders('Inbox')/messages",
        "expirationDateTime": expiration.strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
        "clientState": settings.microsoft_webhook_client_state,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GRAPH}/subscriptions",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=payload,
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"Outlook subscription failed: {resp.text}")
        data = resp.json()

    webhook = mailbox.webhook
    if webhook is None:
        webhook = WebhookSubscription(mailbox_id=mailbox.id, provider=Provider.MICROSOFT.value)
        db.add(webhook)

    webhook.provider = Provider.MICROSOFT.value
    webhook.external_id = data.get("id")
    webhook.resource = data.get("resource")
    exp = data.get("expirationDateTime")
    if exp:
        webhook.expires_at = datetime.fromisoformat(exp.replace("Z", "+00:00"))
    else:
        webhook.expires_at = expiration
    db.commit()
    db.refresh(webhook)
    return webhook


async def renew_outlook_subscription(access_token: str, subscription_id: str) -> dict:
    expiration = datetime.now(timezone.utc) + timedelta(hours=70)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.patch(
            f"{GRAPH}/subscriptions/{subscription_id}",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={"expirationDateTime": expiration.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")},
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"Outlook renew failed: {resp.text}")
        return resp.json()


async def delete_outlook_subscription(access_token: str, subscription_id: str) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        await client.delete(
            f"{GRAPH}/subscriptions/{subscription_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
