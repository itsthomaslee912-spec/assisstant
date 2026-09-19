from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.bid.deps import require_super_admin
from app.bid.models import Account, AccountRole
from app.bid.schemas import AdminCreate, AdminOut, AdminUpdate
from app.bid.security import hash_password
from app.bid.serialize import admin_out
from app.db import get_db

router = APIRouter(prefix="/api/admins", tags=["bid-admins"])


@router.get("", response_model=list[AdminOut])
def list_admins(
    _super: Account = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> list[AdminOut]:
    rows = (
        db.query(Account)
        .filter(Account.role == AccountRole.ADMIN.value)
        .order_by(Account.id.desc())
        .all()
    )
    return [admin_out(row) for row in rows]


@router.post("", response_model=AdminOut)
def create_admin(
    body: AdminCreate,
    _super: Account = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> AdminOut:
    email = body.email.strip().lower()
    if db.query(Account).filter(Account.email == email).one_or_none():
        raise HTTPException(status_code=409, detail="Email already in use")
    account = Account(
        email=email,
        password_hash=hash_password(body.password),
        role=AccountRole.ADMIN.value,
        is_active=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return admin_out(account)


@router.patch("/{admin_id}", response_model=AdminOut)
def update_admin(
    admin_id: int,
    body: AdminUpdate,
    _super: Account = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> AdminOut:
    account = db.get(Account, admin_id)
    if account is None or account.role != AccountRole.ADMIN.value:
        raise HTTPException(status_code=404, detail="Admin not found")
    if body.email is not None:
        email = body.email.strip().lower()
        clash = db.query(Account).filter(Account.email == email, Account.id != account.id).one_or_none()
        if clash:
            raise HTTPException(status_code=409, detail="Email already in use")
        account.email = email
    if body.password:
        account.password_hash = hash_password(body.password)
    if body.is_active is not None:
        account.is_active = body.is_active
    db.commit()
    db.refresh(account)
    return admin_out(account)


@router.delete("/{admin_id}")
def delete_admin(
    admin_id: int,
    _super: Account = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> dict:
    account = db.get(Account, admin_id)
    if account is None or account.role != AccountRole.ADMIN.value:
        raise HTTPException(status_code=404, detail="Admin not found")
    account.is_active = False
    db.commit()
    return {"ok": True}
