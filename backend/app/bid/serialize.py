from __future__ import annotations

from datetime import datetime, timezone

from app.bid.deps import login_status_for
from app.bid.models import Account, Bidder, JobApplication, JobListing, Profile
from app.bid.schemas import (
    AccountOut,
    AdminOut,
    BidderOut,
    JobApplicationOut,
    JobListingOut,
    ProfileOut,
)
from app.bid.util import json_int_list, parse_profile_info


def account_out(account: Account) -> AccountOut:
    bidder = account.bidder
    return AccountOut(
        id=account.id,
        email=account.email,
        role=account.role,
        is_active=account.is_active,
        last_login_at=account.last_login_at,
        last_seen_at=account.last_seen_at,
        login_status=login_status_for(account),
        bidder_id=bidder.id if bidder else None,
        bidder_name=bidder.name if bidder else None,
    )


def bidder_out(bidder: Bidder) -> BidderOut:
    account = bidder.account
    profile_ids = [row.profile_id for row in account.assignments] if account else []
    return BidderOut(
        id=bidder.id,
        account_id=bidder.account_id,
        name=bidder.name,
        email=account.email if account else "",
        crypto_address=bidder.crypto_address or "",
        pay_amount_per_apply=bidder.pay_amount_per_apply or 0,
        status=bidder.status,
        is_active=account.is_active if account else True,
        login_status=login_status_for(account) if account else "offline",
        last_login_at=account.last_login_at if account else None,
        last_seen_at=account.last_seen_at if account else None,
        profile_ids=profile_ids,
        created_at=bidder.created_at,
    )


def admin_out(account: Account) -> AdminOut:
    return AdminOut(
        id=account.id,
        email=account.email,
        role=account.role,
        is_active=account.is_active,
        login_status=login_status_for(account),
        last_login_at=account.last_login_at,
        last_seen_at=account.last_seen_at,
        created_at=account.created_at,
    )


def profile_out(profile: Profile) -> ProfileOut:
    return ProfileOut(
        id=profile.id,
        name=profile.name,
        info=parse_profile_info(profile.info),
        resume_filename=profile.resume_filename,
        has_resume=bool(profile.resume_path),
        assigned_account_ids=[row.account_id for row in profile.assignments],
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def application_out(app: JobApplication) -> JobApplicationOut:
    listing = app.listing
    bidder = app.bidder
    profile = listing.profile if listing else None
    return JobApplicationOut(
        id=app.id,
        listing_id=app.listing_id,
        bidder_id=app.bidder_id,
        bidder_name=bidder.name if bidder else "",
        bidder_status=app.bidder_status,
        review_status=app.review_status,
        needs_human_review=bool(app.needs_human_review),
        reviewed_at=app.reviewed_at,
        review_notes=app.review_notes or "",
        matched_email_id=app.matched_email_id,
        candidate_email_ids=json_int_list(app.candidate_email_ids),
        applied_at=app.applied_at,
        company=listing.company if listing else "",
        title=listing.title if listing else "",
        url=listing.url if listing else "",
        profile_id=listing.profile_id if listing else None,
        profile_name=profile.name if profile else None,
    )


def listing_out(
    listing: JobListing,
    *,
    include_apps: bool = False,
    my_app: JobApplication | None = None,
) -> JobListingOut:
    profile = listing.profile
    return JobListingOut(
        id=listing.id,
        profile_id=listing.profile_id,
        profile_name=profile.name if profile else "",
        company=listing.company,
        title=listing.title,
        url=listing.url,
        created_at=listing.created_at,
        my_application=application_out(my_app) if my_app else None,
        applications=[application_out(a) for a in listing.applications] if include_apps else [],
    )
