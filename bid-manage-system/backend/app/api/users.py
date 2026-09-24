from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import admin_user
from app.models import Profile, User
from app.schemas import Page, UserCreate, UserOut, UserUpdate
from app.security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


def _profiles(db: Session, ids: list[int]) -> list[Profile]:
    rows = db.query(Profile).filter(Profile.id.in_(ids)).all() if ids else []
    if len(rows) != len(set(ids)):
        raise HTTPException(status_code=400, detail="One or more selected profiles do not exist")
    return rows


@router.get("", response_model=Page)
def list_users(
    search: str = "", role: str = "all", status: str = "all",
    page: int = Query(default=1, ge=1), page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db), _admin: User = Depends(admin_user),
):
    query = db.query(User)
    if search.strip():
        needle = f"%{search.strip()}%"
        query = query.filter(or_(User.email.ilike(needle), User.user_id.ilike(needle), User.crypto_address.ilike(needle)))
    if role in {"admin", "bidder"}:
        query = query.filter(User.role == role)
    if status in {"active", "deactive"}:
        query = query.filter(User.status == status)
    total = query.count()
    rows = query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=[UserOut.model_validate(row).model_dump() for row in rows], total=total, page=page, page_size=page_size)


@router.post("", response_model=UserOut)
def create_user(payload: UserCreate, db: Session = Depends(get_db), _admin: User = Depends(admin_user)):
    data = payload.model_dump(exclude={"password", "profile_ids"})
    user = User(**data, password_hash=hash_password(payload.password))
    user.profiles = _profiles(db, payload.profile_ids) if payload.role == "bidder" else []
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email or user ID already exists")
    db.refresh(user)
    return user


@router.put("/{user_pk}", response_model=UserOut)
def update_user(user_pk: int, payload: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    user = db.get(User, user_pk)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and payload.status != "active":
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    data = payload.model_dump(exclude={"password", "profile_ids"})
    for key, value in data.items():
        setattr(user, key, value)
    if payload.password:
        user.password_hash = hash_password(payload.password)
    user.profiles = _profiles(db, payload.profile_ids) if payload.role == "bidder" else []
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email or user ID already exists")
    db.refresh(user)
    return user


@router.delete("/{user_pk}")
def delete_user(user_pk: int, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    user = db.get(User, user_pk)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    db.delete(user)
    db.commit()
    return {"ok": True}

