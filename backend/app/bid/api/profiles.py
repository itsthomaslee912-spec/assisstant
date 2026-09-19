from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload

from app.bid.deps import get_current_account, require_staff, require_super_admin
from app.bid.models import Account, AccountRole, Profile, ProfileAssignment
from app.bid.schemas import AssignProfileIn, ProfileCreate, ProfileOut, ProfileUpdate
from app.bid.serialize import profile_out
from app.bid.services.uploads import allowed_resume, resume_dir
from app.bid.util import dump_profile_info, parse_profile_info
from app.db import get_db

router = APIRouter(prefix="/api/profiles", tags=["bid-profiles"])


def _load_profile(db: Session, profile_id: int) -> Profile:
    profile = (
        db.query(Profile)
        .options(joinedload(Profile.assignments))
        .filter(Profile.id == profile_id)
        .one_or_none()
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _can_download(account: Account, profile: Profile) -> bool:
    if account.role in {AccountRole.SUPER_ADMIN.value, AccountRole.ADMIN.value}:
        return True
    return any(row.account_id == account.id for row in profile.assignments)


@router.get("", response_model=list[ProfileOut])
def list_profiles(
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> list[ProfileOut]:
    q = db.query(Profile).options(joinedload(Profile.assignments)).order_by(Profile.name.asc())
    rows = q.all()
    if account.role == AccountRole.USER.value:
        allowed = {row.profile_id for row in account.assignments}
        rows = [p for p in rows if p.id in allowed]
    return [profile_out(p) for p in rows]


@router.post("", response_model=ProfileOut)
def create_profile(
    body: ProfileCreate,
    _staff: Account = Depends(require_staff),
    db: Session = Depends(get_db),
) -> ProfileOut:
    profile = Profile(name=body.name.strip(), info=dump_profile_info(body.info))
    db.add(profile)
    db.commit()
    return profile_out(_load_profile(db, profile.id))


@router.patch("/{profile_id}", response_model=ProfileOut)
def update_profile(
    profile_id: int,
    body: ProfileUpdate,
    _staff: Account = Depends(require_staff),
    db: Session = Depends(get_db),
) -> ProfileOut:
    profile = _load_profile(db, profile_id)
    if body.name is not None:
        profile.name = body.name.strip()
    if body.info is not None:
        merged = parse_profile_info(profile.info)
        merged.update({k: str(v) for k, v in body.info.items() if v is not None})
        profile.info = dump_profile_info(merged)
    db.commit()
    return profile_out(_load_profile(db, profile.id))


@router.delete("/{profile_id}")
def delete_profile(
    profile_id: int,
    _staff: Account = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict:
    profile = _load_profile(db, profile_id)
    db.query(ProfileAssignment).filter(ProfileAssignment.profile_id == profile.id).delete()
    db.delete(profile)
    db.commit()
    return {"ok": True}


@router.post("/{profile_id}/assign", response_model=ProfileOut)
def assign_profile(
    profile_id: int,
    body: AssignProfileIn,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> ProfileOut:
    profile = _load_profile(db, profile_id)
    if account.role == AccountRole.USER.value:
        target_id = account.id
    else:
        if body.account_id is None:
            raise HTTPException(status_code=400, detail="account_id required")
        target = db.get(Account, body.account_id)
        if target is None or target.role != AccountRole.USER.value:
            raise HTTPException(status_code=400, detail="Target must be a bidder account")
        target_id = target.id
    existing = (
        db.query(ProfileAssignment)
        .filter(ProfileAssignment.account_id == target_id, ProfileAssignment.profile_id == profile.id)
        .one_or_none()
    )
    if existing is None:
        db.add(ProfileAssignment(account_id=target_id, profile_id=profile.id))
        db.commit()
    return profile_out(_load_profile(db, profile.id))


@router.delete("/{profile_id}/assign/{account_id}", response_model=ProfileOut)
def unassign_profile(
    profile_id: int,
    account_id: int,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> ProfileOut:
    profile = _load_profile(db, profile_id)
    if account.role == AccountRole.USER.value and account_id != account.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    db.query(ProfileAssignment).filter(
        ProfileAssignment.account_id == account_id,
        ProfileAssignment.profile_id == profile.id,
    ).delete()
    db.commit()
    return profile_out(_load_profile(db, profile.id))


@router.put("/mine", response_model=list[ProfileOut])
def set_my_profiles(
    body: AssignProfileIn,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> list[ProfileOut]:
    if account.role != AccountRole.USER.value:
        raise HTTPException(status_code=403, detail="Bidders only")
    wanted = set(body.profile_ids or [])
    db.query(ProfileAssignment).filter(ProfileAssignment.account_id == account.id).delete()
    for pid in wanted:
        if db.get(Profile, pid) is None:
            continue
        db.add(ProfileAssignment(account_id=account.id, profile_id=pid))
    db.commit()
    rows = (
        db.query(Profile)
        .options(joinedload(Profile.assignments))
        .join(ProfileAssignment)
        .filter(ProfileAssignment.account_id == account.id)
        .all()
    )
    return [profile_out(p) for p in rows]


@router.post("/{profile_id}/resume", response_model=ProfileOut)
async def upload_resume(
    profile_id: int,
    file: UploadFile = File(...),
    _super: Account = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> ProfileOut:
    profile = _load_profile(db, profile_id)
    filename = file.filename or "resume.pdf"
    if not allowed_resume(filename, file.content_type):
        raise HTTPException(status_code=400, detail="Resume must be PDF, DOC, or DOCX")
    folder = resume_dir(profile.id)
    safe_name = Path(filename).name
    dest = folder / safe_name
    content = await file.read()
    dest.write_bytes(content)
    if profile.resume_path:
        old = Path(profile.resume_path)
        if old.exists() and old.resolve() != dest.resolve():
            old.unlink(missing_ok=True)
    profile.resume_filename = safe_name
    profile.resume_path = str(dest)
    db.commit()
    return profile_out(_load_profile(db, profile.id))


@router.get("/{profile_id}/resume")
def download_resume(
    profile_id: int,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
):
    profile = _load_profile(db, profile_id)
    if not _can_download(account, profile):
        raise HTTPException(status_code=403, detail="Not allowed")
    if not profile.resume_path:
        raise HTTPException(status_code=404, detail="No resume uploaded")
    path = Path(profile.resume_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume file missing")
    return FileResponse(path, filename=profile.resume_filename or path.name)


@router.delete("/{profile_id}/resume", response_model=ProfileOut)
def delete_resume(
    profile_id: int,
    _super: Account = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> ProfileOut:
    profile = _load_profile(db, profile_id)
    if profile.resume_path:
        Path(profile.resume_path).unlink(missing_ok=True)
    profile.resume_path = None
    profile.resume_filename = None
    db.commit()
    return profile_out(_load_profile(db, profile.id))
