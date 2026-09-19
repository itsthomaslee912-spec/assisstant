from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.bid.models import Account, Bidder, JobApplication, JobListing, Profile, ProfileAssignment
from app.bid.schemas import PROFILE_INFO_KEYS, ProfileInfo


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def monday_on_or_before(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_window(now: datetime | None = None) -> tuple[date, date]:
    """Current Monday (inclusive) and next Monday (exclusive)."""
    now = now or utcnow()
    start = monday_on_or_before(now.date())
    return start, start + timedelta(days=7)


def last_week_window(now: datetime | None = None) -> tuple[date, date]:
    this_start, _ = week_window(now)
    return this_start - timedelta(days=7), this_start


def parse_profile_info(raw: str | None) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                data = loaded
        except json.JSONDecodeError:
            data = {}
    out = {key: "" for key in PROFILE_INFO_KEYS}
    for key in PROFILE_INFO_KEYS:
        value = data.get(key)
        if value is not None:
            out[key] = str(value)
    return out


def dump_profile_info(info: dict[str, Any] | None) -> str:
    base = {key: "" for key in PROFILE_INFO_KEYS}
    if info:
        for key in PROFILE_INFO_KEYS:
            if key in info and info[key] is not None:
                base[key] = str(info[key])
    return json.dumps(base)


def profile_email(profile: Profile) -> str:
    info = parse_profile_info(profile.info)
    return (info.get("email") or "").strip().lower()


def json_int_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[int] = []
    for item in data:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def assigned_profile_ids(account: Account) -> list[int]:
    return [row.profile_id for row in account.assignments]
