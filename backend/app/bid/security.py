from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.bid.settings import get_bid_settings
from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(*, account_id: int, email: str, role: str) -> str:
    settings = get_settings()
    bid = get_bid_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(account_id),
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=bid.jwt_expire_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.session_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.session_secret, algorithms=[ALGORITHM])
