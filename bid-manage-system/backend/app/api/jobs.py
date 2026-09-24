from __future__ import annotations

import csv
import io
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import JobApplication, Profile, User, utcnow
from app.schemas import BidderJobUpdate, BulkJobIn, JobCreate, JobOut, JobUpdate, Page

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _clean_import_link(value: str) -> str:
    """Convert pasted Markdown links to a plain, usable URL."""
    value = value.strip()
    markdown_link = re.fullmatch(r"\[[^\]]*\]\((.+)\)", value)
    if markdown_link:
        value = markdown_link.group(1)
    return value.replace("\\", "")


def _parse_import_line(line: str) -> list[str]:
    # Spreadsheet/text-list exports are normally tab separated. Keep support
    # for the original pipe-separated format as well.
    if "\t" in line:
        return [cell.strip() for cell in line.split("\t")]
    return [cell.strip() for cell in next(csv.reader(io.StringIO(line), delimiter="|"))]


def _parse_import_options(cells: list[str]) -> tuple[str, str]:
    work_model = ""
    job_status = "pending"
    for raw_value in cells[3:]:
        value = raw_value.strip().lower()
        if not value:
            continue
        if value in {"on-site", "hybrid", "remote"}:
            work_model = value
        elif value in {"pending", "applied", "canceled"}:
            job_status = value
        else:
            raise ValueError(f"invalid optional value '{raw_value.strip()}'")
    return work_model, job_status


def _can_access_profile(user: User, profile_id: int) -> bool:
    return user.role == "admin" or any(profile.id == profile_id for profile in user.profiles)


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("", response_model=Page)
def list_jobs(
    profile_id: int,
    status: str = "all",
    date_from: date | None = None,
    date_to: date | None = None,
    search: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if not _can_access_profile(user, profile_id):
        raise HTTPException(status_code=403, detail="Profile is not assigned to you")
    query = db.query(JobApplication).filter(JobApplication.profile_id == profile_id)
    if status in {"pending", "applied", "canceled"}:
        query = query.filter(JobApplication.status == status)
    if date_from:
        query = query.filter(JobApplication.application_date >= date_from)
    if date_to:
        query = query.filter(JobApplication.application_date <= date_to)
    if search.strip():
        needle = f"%{search.strip()}%"
        query = query.filter(or_(JobApplication.company_name.ilike(needle), JobApplication.role.ilike(needle)))
    total = query.count()
    rows = query.order_by(JobApplication.application_date.desc(), JobApplication.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=[JobOut.model_validate(row).model_dump() for row in rows], total=total, page=page, page_size=page_size)


@router.post("", response_model=JobOut)
def create_job(payload: JobCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _require_admin(user)
    if db.get(Profile, payload.profile_id) is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    # A job starts as an assignment. Only a later status update can mark it
    # applied or canceled.
    row = JobApplication(**payload.model_dump(exclude={"status", "bot_check_status"}), status="pending", bot_check_status="pending")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{job_id}", response_model=JobOut)
def update_job(job_id: int, payload: JobUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _require_admin(user)
    row = db.get(JobApplication, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job application not found")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{job_id}/bidder", response_model=JobOut)
def bidder_update_job(job_id: int, payload: BidderJobUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(JobApplication, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job application not found")
    if not _can_access_profile(user, row.profile_id):
        raise HTTPException(status_code=403, detail="Profile is not assigned to you")
    status_changed = row.status != payload.status
    row.status = payload.status
    row.work_model = payload.work_model
    if status_changed and payload.status in {"applied", "canceled"}:
        row.submitted_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _require_admin(user)
    row = db.get(JobApplication, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job application not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/bulk")
def bulk_create(payload: BulkJobIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _require_admin(user)
    if db.get(Profile, payload.profile_id) is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    created = 0
    errors: list[str] = []
    for line_no, line in enumerate(payload.text.splitlines(), start=1):
        cells = _parse_import_line(line)
        if not cells or not any(cells):
            continue
        if len(cells) < 2:
            errors.append(f"Line {line_no}: expected at least Company and Role")
            continue
        company, role = cells[0], cells[1]
        if not company or not role:
            errors.append(f"Line {line_no}: company and role are required")
            continue
        link = _clean_import_link(cells[2]) if len(cells) > 2 else ""
        try:
            work_model, job_status = _parse_import_options(cells)
        except ValueError as error:
            errors.append(f"Line {line_no}: {error}")
            continue
        db.add(JobApplication(
            profile_id=payload.profile_id, company_name=company, role=role,
            job_link=link, work_model=work_model, status=job_status,
        ))
        created += 1
    db.commit()
    return {"created": created, "errors": errors}
