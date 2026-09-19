from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import HTTPException

GRAPH = "https://graph.microsoft.com/v1.0"


def _strip_html(html: str) -> str:
    # Lightweight strip without extra deps
    out: list[str] = []
    in_tag = False
    for ch in html:
        if ch == "<":
            in_tag = True
            continue
        if ch == ">":
            in_tag = False
            continue
        if not in_tag:
            out.append(ch)
    return "".join(out)


async def outlook_list_delta(access_token: str, delta_link: str | None = None) -> dict:
    url = delta_link or f"{GRAPH}/me/mailFolders/inbox/messages/delta"
    params = None
    if not delta_link:
        params = {
            "$select": "id,subject,from,receivedDateTime,bodyPreview,body,conversationId",
            "$top": "25",
        }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"Outlook delta failed: {resp.text}")
        return resp.json()


async def outlook_get_message(access_token: str, message_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GRAPH}/me/messages/{message_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "$select": "id,subject,from,receivedDateTime,bodyPreview,body,conversationId",
            },
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"Outlook get message failed: {resp.text}")
        return resp.json()


async def outlook_list_recent(access_token: str, top: int = 500) -> list[dict]:
    messages: list[dict] = []
    url = f"{GRAPH}/me/mailFolders/inbox/messages"
    params = {
        "$top": min(50, max(1, top)),
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,receivedDateTime,bodyPreview,body,conversationId",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        while len(messages) < top:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params if url.endswith("/messages") else None,
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=400, detail=f"Outlook list messages failed: {resp.text}")
            data = resp.json()
            batch = data.get("value") or []
            if not batch:
                break
            messages.extend(batch)
            next_link = data.get("@odata.nextLink")
            if not next_link:
                break
            url = next_link
            params = None
    return messages[:top]


def normalize_outlook_message(raw: dict) -> dict:
    sender_obj = ((raw.get("from") or {}).get("emailAddress") or {})
    sender = sender_obj.get("address") or sender_obj.get("name") or ""
    received_raw = raw.get("receivedDateTime")
    received_at = None
    if received_raw:
        try:
            received_at = datetime.fromisoformat(received_raw.replace("Z", "+00:00"))
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)
        except Exception:
            received_at = None

    body = raw.get("body") or {}
    content = body.get("content") or ""
    body_html = ""
    if (body.get("contentType") or "").lower() == "html":
        body_html = content
        body_text = _strip_html(content)
    else:
        body_text = content

    snippet = (raw.get("bodyPreview") or body_text[:280]).strip()
    return {
        "provider_message_id": raw["id"],
        "thread_id": raw.get("conversationId"),
        "subject": raw.get("subject") or "",
        "sender": sender,
        "received_at": received_at,
        "snippet": snippet,
        "body_text": body_text[:20000],
        "body_html": body_html[:200000],
    }


async def outlook_send_message(
    access_token: str,
    *,
    to_address: str,
    subject: str,
    body_text: str,
) -> None:
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body_text},
            "toRecipients": [{"emailAddress": {"address": to_address}}],
        },
        "saveToSentItems": True,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GRAPH}/me/sendMail",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=payload,
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"Outlook send failed: {resp.text}")
