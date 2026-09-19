from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.bid.deps import require_staff
from app.bid.models import Account, AccountRole, Bidder, BidderRecordStatus
from app.bid.schemas import BidderCreate, BidderOut, BidderUpdate
from app.bid.security import hash_password
from app.bid.serialize import bidder_out
from app.db import get_db

router = APIRouter(prefix="/api/bidders", tags=["bid-bidders"])


def _load_bidder(db: Session, bidder_id: int) -> Bidder:
    bidder = (
        db.query(Bidder)
        .options(joinedload(Bidder.account).joinedload(Account.assignments))
        .filter(Bidder.id == bidder_id)
        .one_or_none()
    )
    if bidder is None:
        raise HTTPException(status_code=404, detail="Bidder not found")
    return bidder


@router.get("", response_model=list[BidderOut])
def list_bidders(
    _staff: Account = Depends(require_staff),
    db: Session = Depends(get_db),
) -> list[BidderOut]:
    rows = (
        db.query(Bidder)
        .options(joinedload(Bidder.account).joinedload(Account.assignments))
        .order_by(Bidder.id.desc())
        .all()
    )
    return [bidder_out(row) for row in rows]


@router.post("", response_model=BidderOut)
def create_bidder(
    body: BidderCreate,
    _staff: Account = Depends(require_staff),
    db: Session = Depends(get_db),
) -> BidderOut:
    email = body.email.strip().lower()
    if db.query(Account).filter(Account.email == email).one_or_none():
        raise HTTPException(status_code=409, detail="Email already in use")
    status = body.status if body.status in {s.value for s in BidderRecordStatus} else BidderRecordStatus.ACTIVE.value
    account = Account(
        email=email,
        password_hash=hash_password(body.password),
        role=AccountRole.USER.value,
        is_active=status == BidderRecordStatus.ACTIVE.value,
    )
    db.add(account)
    db.flush()
    bidder = Bidder(
        account_id=account.id,
        name=body.name.strip(),
        crypto_address=(body.crypto_address or "").strip(),
        pay_amount_per_apply=body.pay_amount_per_apply,
        status=status,
    )
    db.add(bidder)
    db.commit()
    return bidder_out(_load_bidder(db, bidder.id))


@router.patch("/{bidder_id}", response_model=BidderOut)
def update_bidder(
    bidder_id: int,
    body: BidderUpdate,
    _staff: Account = Depends(require_staff),
    db: Session = Depends(get_db),
) -> BidderOut:
    bidder = _load_bidder(db, bidder_id)
    account = bidder.account
    if body.name is not None:
        bidder.name = body.name.strip()
    if body.crypto_address is not None:
        bidder.crypto_address = body.crypto_address.strip()
    if body.pay_amount_per_apply is not None:
        bidder.pay_amount_per_apply = body.pay_amount_per_apply
    if body.status is not None:
        if body.status not in {s.value for s in BidderRecordStatus}:
            raise HTTPException(status_code=400, detail="Invalid status")
        bidder.status = body.status
        account.is_active = body.status == BidderRecordStatus.ACTIVE.value
    if body.is_active is not None:
        account.is_active = body.is_active
        if not body.is_active:
            bidder.status = BidderRecordStatus.INACTIVE.value
    if body.email is not None:
        email = body.email.strip().lower()
        clash = db.query(Account).filter(Account.email == email, Account.id != account.id).one_or_none()
        if clash:
            raise HTTPException(status_code=409, detail="Email already in use")
        account.email = email
    if body.password:
        account.password_hash = hash_password(body.password)
    db.commit()
    return bidder_out(_load_bidder(db, bidder.id))


@router.delete("/{bidder_id}")
def deactivate_bidder(
    bidder_id: int,
    _staff: Account = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    bidder = _load_bidder(db, bidder_id)
    bidder.status = BidderRecordStatus.INACTIVE.value
    bidder.account.is_active = False
    db.commit()
    return {"ok": True}
