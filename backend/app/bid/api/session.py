from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.bid.deps import get_current_account
from app.bid.models import Account
from app.bid.schemas import AccountOut, LoginIn, TokenOut
from app.bid.security import create_access_token, verify_password
from app.bid.serialize import account_out
from app.db import get_db

router = APIRouter(prefix="/api/session", tags=["bid-session"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    email = body.email.strip().lower()
    account = db.query(Account).options(joinedload(Account.bidder)).filter(Account.email == email).one_or_none()
    if account is None or not verify_password(body.password, account.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not account.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    now = datetime.now(timezone.utc)
    account.last_login_at = now
    account.last_seen_at = now
    db.commit()
    db.refresh(account)
    token = create_access_token(account_id=account.id, email=account.email, role=account.role)
    return TokenOut(access_token=token, account=account_out(account))


@router.get("/me", response_model=AccountOut)
def me(account: Account = Depends(get_current_account)) -> AccountOut:
    return account_out(account)
