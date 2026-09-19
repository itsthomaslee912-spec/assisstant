from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.bid.models import Account, AccountRole, Bidder
from app.bid.security import decode_access_token
from app.db import get_db

bearer = HTTPBearer(auto_error=False)

ONLINE_WINDOW = timedelta(minutes=5)


def login_status_for(account: Account, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    seen = account.last_seen_at or account.last_login_at
    if seen is None:
        return "offline"
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return "online" if now - seen <= ONLINE_WINDOW else "offline"


def get_current_account(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Account:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    try:
        payload = decode_access_token(creds.credentials)
        account_id = int(payload.get("sub", "0"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    account = db.get(Account, account_id)
    if account is None or not account.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account inactive")
    account.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(account)
    return account


def require_roles(*roles: str) -> Callable[..., Account]:
    def _dep(account: Account = Depends(get_current_account)) -> Account:
        if account.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
        return account

    return _dep


require_staff = require_roles(AccountRole.SUPER_ADMIN.value, AccountRole.ADMIN.value)
require_super_admin = require_roles(AccountRole.SUPER_ADMIN.value)
require_bidder = require_roles(AccountRole.USER.value)


def get_bidder_or_404(account: Account, db: Session) -> Bidder:
    if account.bidder is None:
        bidder = db.query(Bidder).filter(Bidder.account_id == account.id).one_or_none()
        if bidder is None:
            raise HTTPException(status_code=400, detail="This account is not a bidder")
        return bidder
    return account.bidder
