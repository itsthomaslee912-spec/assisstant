from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.bid.models import Account, AccountRole
from app.bid.security import hash_password
from app.bid.settings import get_bid_settings

logger = logging.getLogger(__name__)


def seed_super_admin(db: Session) -> None:
    existing = (
        db.query(Account).filter(Account.role == AccountRole.SUPER_ADMIN.value).one_or_none()
    )
    if existing is not None:
        return
    settings = get_bid_settings()
    email = (settings.superadmin_email or "superadmin@localhost").strip().lower()
    password = settings.superadmin_password or "change-me-superadmin"
    account = Account(
        email=email,
        password_hash=hash_password(password),
        role=AccountRole.SUPER_ADMIN.value,
        is_active=True,
    )
    db.add(account)
    db.commit()
    logger.info("Seeded super-admin account %s", email)
