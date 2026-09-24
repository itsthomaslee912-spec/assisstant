from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import admin_user, current_user
from app.models import Profile, User
from app.schemas import Page, ProfileCreate, ProfileOut, ProfileUpdate

router = APIRouter(prefix="/api/profiles", tags=["profiles"])
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "resumes"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _allowed_profile(db: Session, user: User, profile_id: int) -> Profile:
    profile = db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if user.role != "admin" and all(item.id != profile_id for item in user.profiles):
        raise HTTPException(status_code=403, detail="Profile is not assigned to you")
    return profile


@router.get("", response_model=Page)
def list_profiles(
    search: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    query = db.query(Profile)
    if user.role != "admin":
        allowed = [item.id for item in user.profiles]
        query = query.filter(Profile.id.in_(allowed or [-1]))
    if search.strip():
        needle = f"%{search.strip()}%"
        query = query.filter(or_(
            Profile.first_name.ilike(needle), Profile.last_name.ilike(needle),
            Profile.email.ilike(needle), Profile.current_company.ilike(needle),
        ))
    total = query.count()
    rows = query.order_by(Profile.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=[ProfileOut.model_validate(row).model_dump() for row in rows], total=total, page=page, page_size=page_size)


@router.get("/options", response_model=list[ProfileOut])
def profile_options(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role == "admin":
        return db.query(Profile).order_by(Profile.first_name, Profile.last_name).all()
    return sorted(user.profiles, key=lambda item: (item.first_name.lower(), item.last_name.lower()))


@router.post("", response_model=ProfileOut)
def create_profile(payload: ProfileCreate, db: Session = Depends(get_db), _admin: User = Depends(admin_user)):
    profile = Profile(**payload.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.put("/{profile_id}", response_model=ProfileOut)
def update_profile(profile_id: int, payload: ProfileUpdate, db: Session = Depends(get_db), _admin: User = Depends(admin_user)):
    profile = db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


@router.delete("/{profile_id}")
def delete_profile(profile_id: int, db: Session = Depends(get_db), _admin: User = Depends(admin_user)):
    profile = db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    db.delete(profile)
    db.commit()
    return {"ok": True}


@router.post("/{profile_id}/resume", response_model=ProfileOut)
def upload_resume(
    profile_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(admin_user),
):
    profile = db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    suffix = Path(file.filename or "resume.pdf").suffix.lower()
    if suffix not in {".pdf", ".doc", ".docx"}:
        raise HTTPException(status_code=400, detail="Resume must be PDF, DOC, or DOCX")
    target = UPLOAD_DIR / f"profile-{profile.id}{suffix}"
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    profile.resume_path = str(target.relative_to(UPLOAD_DIR.parent.parent))
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/{profile_id}/resume")
def download_resume(profile_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    profile = _allowed_profile(db, user, profile_id)
    if not profile.resume_path:
        raise HTTPException(status_code=404, detail="Resume not uploaded")
    path = Path(__file__).resolve().parents[2] / profile.resume_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume file not found")
    return FileResponse(path, filename=path.name)

