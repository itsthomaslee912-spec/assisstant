from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer


def _as_utc(value: Any) -> Any:
    if value is None or not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = _as_utc(value)
    return aware.isoformat().replace("+00:00", "Z")


UtcDateTime = Annotated[
    datetime,
    BeforeValidator(_as_utc),
    PlainSerializer(_json_utc, when_used="json"),
]

EmailLabelLiteral = Literal[
    "available",
    "interview",
    "assessment",
    "rejected",
    "applied",
    "alert",
    "others",
]
ProviderLiteral = Literal["google", "microsoft"]


class MailboxOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: ProviderLiteral
    email_address: str
    display_name: str | None = None
    is_active: bool
    created_at: UtcDateTime | None = None


class EmailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mailbox_id: int
    provider_message_id: str
    subject: str
    sender: str
    received_at: UtcDateTime | None = None
    snippet: str
    label: str
    confidence: float | None = None
    is_read: bool = False
    created_at: UtcDateTime | None = None


class EmailPageOut(BaseModel):
    items: list[EmailOut]
    next_cursor: int | None = None
    next_received_at: UtcDateTime | None = None
    has_more: bool = False
    total: int = 0
    label_counts: dict[str, int]
    mailbox_counts: dict[str, int]
    mailbox_unread_counts: dict[str, int] = {}


class EmailDetailOut(EmailOut):
    body_text: str = ""
    body_html: str = ""


class SendEmailIn(BaseModel):
    mailbox_id: int
    to_address: str
    subject: str
    body_text: str


class SendEmailOut(BaseModel):
    ok: bool
    provider_message_id: str | None = None


class HealthOut(BaseModel):
    status: str
    service: str = "auto-ai-email-checker"


class ClassificationResult(BaseModel):
    label: EmailLabelLiteral
    confidence: float | None = None
    response_id: str | None = None
