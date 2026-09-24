from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import current_user
from app.models import JobApplication, Profile, User
from app.schemas import AdminBidderPay, AdminDashboard, BidderDashboard, ProfileSummary, SeriesPoint

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _series(db: Session, profile_ids: list[int], date_from: date, date_to: date) -> list[SeriesPoint]:
    query = db.query(JobApplication).filter(
        JobApplication.profile_id.in_(profile_ids or [-1]),
        JobApplication.status == "applied",
    )
    if date_from == date_to:
        rows = query.filter(JobApplication.application_date == date_from).all()
        buckets = [0] * 24
        for row in rows:
            hour = (row.submitted_at or row.updated_at or row.created_at).hour
            buckets[hour] += 1
        def hour_label(hour: int) -> str:
            suffix = "AM" if hour < 12 else "PM"
            display = hour % 12 or 12
            return f"{display}{suffix}"
        return [SeriesPoint(label=hour_label(h), value=value) for h, value in enumerate(buckets)]
    day_count = (date_to - date_from).days + 1
    rows = query.filter(JobApplication.application_date.between(date_from, date_to)).all()
    buckets = [0] * day_count
    for row in rows:
        buckets[(row.application_date - date_from).days] += 1
    return [SeriesPoint(label=f"{current.strftime('%b')} {current.day}", value=buckets[index]) for index in range(day_count) for current in [date_from + timedelta(days=index)]]


@router.get("/bidder", response_model=BidderDashboard)
def bidder_dashboard(
    profile_id: int | None = None,
    date_from: date = Query(default_factory=date.today),
    date_to: date = Query(default_factory=date.today),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role != "bidder":
        raise HTTPException(status_code=403, detail="Bidder access required")
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="From date must be on or before To date")
    allowed = [profile.id for profile in user.profiles]
    if profile_id is not None and profile_id not in allowed:
        raise HTTPException(status_code=403, detail="Profile is not assigned to you")
    selected = [profile_id] if profile_id is not None else allowed
    applied = db.query(JobApplication).filter(
        JobApplication.profile_id.in_(selected or [-1]), JobApplication.status == "applied",
        JobApplication.application_date.between(date_from, date_to),
    ).count()
    bot_check_pass_count = db.query(JobApplication).filter(
        JobApplication.profile_id.in_(selected or [-1]), JobApplication.bot_check_status == "pass",
        JobApplication.application_date.between(date_from, date_to),
    ).count()
    rate = Decimal(user.per_bid_pay_amount or 0)
    return BidderDashboard(
        profiles=[ProfileSummary.model_validate(item) for item in user.profiles],
        applied_count=applied,
        bot_check_pass_count=bot_check_pass_count,
        paid_amount=rate * bot_check_pass_count,
        series=_series(db, selected, date_from, date_to),
    )


@router.get("/admin", response_model=AdminDashboard)
def admin_dashboard(
    date_from: date = Query(default_factory=date.today),
    date_to: date = Query(default_factory=date.today),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="From date must be on or before To date")
    bidders = db.query(User).filter(User.role == "bidder", User.status == "active").all()
    pay_cards: list[AdminBidderPay] = []
    total_paid = Decimal("0")
    for bidder in bidders:
        profile_ids = [item.id for item in bidder.profiles]
        bot_check_pass_count = db.query(JobApplication).filter(
            JobApplication.profile_id.in_(profile_ids or [-1]), JobApplication.bot_check_status == "pass",
            JobApplication.application_date.between(date_from, date_to),
        ).count()
        rate = Decimal(bidder.per_bid_pay_amount or 0)
        amount = rate * bot_check_pass_count
        total_paid += amount
        pay_cards.append(AdminBidderPay(
            user_id=bidder.id, bidder_name=bidder.user_id, bot_check_pass_count=bot_check_pass_count,
            per_bid_pay_amount=rate, paid_amount=amount,
        ))
    profiles = db.query(Profile).order_by(Profile.first_name, Profile.last_name).all()
    profile_series = {str(profile.id): _series(db, [profile.id], date_from, date_to) for profile in profiles}
    return AdminDashboard(
        total_profiles=len(profiles),
        active_bidders=len(bidders),
        applications_count=db.query(JobApplication).filter(JobApplication.application_date.between(date_from, date_to)).count(),
        paid_amount_total=total_paid,
        pay_cards=pay_cards,
        profiles=[ProfileSummary.model_validate(profile) for profile in profiles],
        profile_series=profile_series,
    )
