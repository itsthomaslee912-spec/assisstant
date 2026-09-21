from __future__ import annotations

import base64
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.services.mailbox_sync import process_gmail_notification, process_outlook_notification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/gmail")
async def gmail_pubsub_push(request: Request, background_tasks: BackgroundTasks) -> dict:
    body = await request.json()
    message = body.get("message") or {}
    data_b64 = message.get("data")
    if not data_b64:
        return {"ok": True, "skipped": True}

    try:
        decoded = base64.b64decode(data_b64).decode("utf-8")
        payload = json.loads(decoded)
    except Exception:
        logger.exception("Invalid Gmail Pub/Sub payload")
        return {"ok": False}

    email_address = payload.get("emailAddress") or ""
    history_id = str(payload.get("historyId") or "") or None
    background_tasks.add_task(_handle_gmail, email_address, history_id)
    return {"ok": True}


async def _handle_gmail(email_address: str, history_id: str | None) -> None:
    db = SessionLocal()
    try:
        await process_gmail_notification(db, email_address, history_id)
    except Exception:
        logger.exception("Gmail notification processing failed")
    finally:
        db.close()


@router.post("/outlook")
async def outlook_graph_webhook(request: Request, background_tasks: BackgroundTasks) -> Response:
    # Graph validation handshake
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        return Response(content=validation_token, media_type="text/plain", status_code=200)

    settings = get_settings()
    body = await request.json()
    notifications = body.get("value") or []
    for note in notifications:
        if note.get("clientState") != settings.microsoft_webhook_client_state:
            logger.warning("Rejected Outlook notification with bad clientState")
            continue
        subscription_id = note.get("subscriptionId") or ""
        resource_data = note.get("resourceData") or {}
        message_id = resource_data.get("id")
        if not message_id and note.get("resource"):
            # resource like Users/{id}/Messages/{id}
            parts = str(note["resource"]).rstrip("/").split("/")
            if parts:
                message_id = parts[-1]
        if subscription_id and message_id:
            background_tasks.add_task(_handle_outlook, subscription_id, message_id)

    return Response(status_code=202)


async def _handle_outlook(subscription_id: str, message_id: str) -> None:
    db = SessionLocal()
    try:
        await process_outlook_notification(db, subscription_id, message_id)
    except Exception:
        logger.exception("Outlook notification processing failed")
    finally:
        db.close()
