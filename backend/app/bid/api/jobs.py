from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.bid.deps import get_current_account, get_bidder_or_404, require_staff
from app.bid.models import (
    Account,
    AccountRole,
    BidderJobStatus,
    JobApplication,
    JobListing,
    Profile,
    ProfileAssignment,
    ReviewStatus,
)
from app.bid.schemas import (
    BidderStatusIn,
    JobImportIn,
    JobListingOut,
    ManualReviewIn,
    ProfileGroupOut,
    ReviewResultOut,
)
from app.bid.serialize import application_out, listing_out, profile_out
from app.bid.services.job_import import parse_job_text
from app.bid.services.review import review_application
from app.bid.util import utcnow
from app.db import get_db

router = APIRouter(prefix="/api/jobs", tags=["bid-jobs"])


def _listing_query(db: Session):
    return db.query(JobListing).options(
        joinedload(JobListing.profile).joinedload(Profile.assignments),
        joinedload(JobListing.applications).joinedload(JobApplication.bidder),
    )


@router.get("/grouped", response_model=list[ProfileGroupOut])
def jobs_grouped(
    _staff: Account = Depends(require_staff),
    db: Session = Depends(get_db),
) -> list[ProfileGroupOut]:
    profiles = (
        db.query(Profile)
        .options(joinedload(Profile.assignments), joinedload(Profile.listings).joinedload(JobListing.applications).joinedload(JobApplication.bidder))
        .order_by(Profile.name.asc())
        .all()
    )
    groups: list[ProfileGroupOut] = []
    for profile in profiles:
        groups.append(
            ProfileGroupOut(
                profile=profile_out(profile),
                listings=[listing_out(item, include_apps=True) for item in profile.listings],
            )
        )
    return groups


@router.get("/mine", response_model=list[JobListingOut])
def my_jobs(
    profile_id: int | None = None,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> list[JobListingOut]:
    bidder = get_bidder_or_404(account, db)
    assigned = [row.profile_id for row in account.assignments]
    if profile_id is not None:
        if profile_id not in assigned and account.role == AccountRole.USER.value:
            raise HTTPException(status_code=403, detail="Profile is not assigned")
        assigned = [profile_id]
    if not assigned:
        return []
    listings = (
        _listing_query(db)
        .filter(JobListing.profile_id.in_(assigned))
        .order_by(JobListing.id.desc())
        .all()
    )
    out: list[JobListingOut] = []
    for listing in listings:
        mine = next((a for a in listing.applications if a.bidder_id == bidder.id), None)
        out.append(listing_out(listing, my_app=mine))
    return out


@router.post("/import", response_model=list[JobListingOut])
async def import_jobs(
    body: JobImportIn | None = None,
    profile_id: int | None = Form(default=None),
    text: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    _staff: Account = Depends(require_staff),
    db: Session = Depends(get_db),
) -> list[JobListingOut]:
    pid = profile_id or (body.profile_id if body else None)
    blob = text or (body.text if body else "") or ""
    if file is not None:
        blob = (await file.read()).decode("utf-8-sig", errors="replace") + "\n" + blob
    if pid is None:
        raise HTTPException(status_code=400, detail="profile_id required")
    profile = db.get(Profile, pid)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    parsed = parse_job_text(blob)
    if not parsed:
        raise HTTPException(status_code=400, detail="No job links found")
    created: list[JobListing] = []
    for job in parsed:
        existing = (
            db.query(JobListing)
            .filter(JobListing.profile_id == pid, JobListing.url == job.url)
            .one_or_none()
        )
        if existing:
            if job.company:
                existing.company = job.company
            if job.title:
                existing.title = job.title
            created.append(existing)
            continue
        listing = JobListing(
            profile_id=pid,
            company=job.company,
            title=job.title,
            url=job.url,
        )
        db.add(listing)
        db.flush()
        created.append(listing)
    db.commit()
    ids = [row.id for row in created]
    rows = _listing_query(db).filter(JobListing.id.in_(ids)).all()
    return [listing_out(row, include_apps=True) for row in rows]


@router.patch("/{listing_id}/bidder-status", response_model=JobListingOut)
def set_bidder_status(
    listing_id: int,
    body: BidderStatusIn,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> JobListingOut:
    bidder = get_bidder_or_404(account, db)
    if body.bidder_status not in {BidderJobStatus.PENDING.value, BidderJobStatus.CANCEL.value, BidderJobStatus.APPLIED.value}:
        raise HTTPException(status_code=400, detail="Invalid bidder_status")
    listing = _listing_query(db).filter(JobListing.id == listing_id).one_or_none()
    if listing is None:
        raise HTTPException(status_code=404, detail="Job not found")
    assigned = {row.profile_id for row in account.assignments}
    if listing.profile_id not in assigned:
        raise HTTPException(status_code=403, detail="Profile is not assigned")
    app = next((a for a in listing.applications if a.bidder_id == bidder.id), None)
    if app is None:
        app = JobApplication(
            listing_id=listing.id,
            bidder_id=bidder.id,
            bidder_status=BidderJobStatus.PENDING.value,
            review_status=ReviewStatus.PENDING.value,
        )
        db.add(app)
        db.flush()
    if app.review_status in {ReviewStatus.PASSED.value, ReviewStatus.FAILED.value}:
        raise HTTPException(status_code=400, detail="Review already finished")
    app.bidder_status = body.bidder_status
    if body.bidder_status == BidderJobStatus.APPLIED.value:
        app.applied_at = utcnow()
    db.commit()
    listing = _listing_query(db).filter(JobListing.id == listing_id).one()
    mine = next((a for a in listing.applications if a.bidder_id == bidder.id), None)
    return listing_out(listing, my_app=mine)


@router.post("/applications/{application_id}/review", response_model=ReviewResultOut)
async def review_one(
    application_id: int,
    _staff: Account = Depends(require_staff),
    db: Session = Depends(get_db),
) -> ReviewResultOut:
    app = (
        db.query(JobApplication)
        .options(
            joinedload(JobApplication.listing).joinedload(JobListing.profile),
            joinedload(JobApplication.bidder),
        )
        .filter(JobApplication.id == application_id)
        .one_or_none()
    )
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.bidder_status != BidderJobStatus.APPLIED.value:
        raise HTTPException(status_code=400, detail="Bidder has not marked this job applied")
    if app.review_status != ReviewStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="Already reviewed")
    await review_application(db, app)
    db.commit()
    db.refresh(app)
    return ReviewResultOut(application=application_out(app), outcome=app.review_status, notes=app.review_notes or "")


@router.post("/review-bulk", response_model=list[ReviewResultOut])
async def review_bulk(
    profile_id: int | None = None,
    _staff: Account = Depends(require_staff),
    db: Session = Depends(get_db),
) -> list[ReviewResultOut]:
    q = (
        db.query(JobApplication)
        .options(
            joinedload(JobApplication.listing).joinedload(JobListing.profile),
            joinedload(JobApplication.bidder),
        )
        .filter(
            JobApplication.bidder_status == BidderJobStatus.APPLIED.value,
            JobApplication.review_status == ReviewStatus.PENDING.value,
        )
    )
    if profile_id is not None:
        q = q.join(JobListing).filter(JobListing.profile_id == profile_id)
    rows = q.all()
    results: list[ReviewResultOut] = []
    for app in rows:
        await review_application(db, app)
        results.append(
            ReviewResultOut(application=application_out(app), outcome=app.review_status, notes=app.review_notes or "")
        )
    db.commit()
    return results


@router.patch("/applications/{application_id}/review-status", response_model=ReviewResultOut)
def manual_review(
    application_id: int,
    body: ManualReviewIn,
    _staff: Account = Depends(require_staff),
    db: Session = Depends(get_db),
) -> ReviewResultOut:
    if body.review_status not in {ReviewStatus.PASSED.value, ReviewStatus.FAILED.value}:
        raise HTTPException(status_code=400, detail="review_status must be passed or failed")
    app = (
        db.query(JobApplication)
        .options(
            joinedload(JobApplication.listing).joinedload(JobListing.profile),
            joinedload(JobApplication.bidder),
        )
        .filter(JobApplication.id == application_id)
        .one_or_none()
    )
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    app.review_status = body.review_status
    app.needs_human_review = False
    app.reviewed_at = utcnow()
    if body.notes:
        app.review_notes = body.notes
    db.commit()
    db.refresh(app)
    return ReviewResultOut(application=application_out(app), outcome=app.review_status, notes=app.review_notes or "")


@router.get("/human-review", response_model=list)
def human_queue(
    _staff: Account = Depends(require_staff),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(JobApplication)
        .options(
            joinedload(JobApplication.listing).joinedload(JobListing.profile),
            joinedload(JobApplication.bidder),
        )
        .filter(JobApplication.needs_human_review.is_(True))
        .order_by(JobApplication.id.desc())
        .all()
    )
    return [application_out(row) for row in rows]
