from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


PROFILE_INFO_KEYS = [
    "first_name",
    "middle_name",
    "last_name",
    "email",
    "phone",
    "linkedin",
    "github",
    "personal_website",
    "portfolio",
    "race",
    "salary",
    "date_of_birth",
    "asian_region",
    "street",
    "city",
    "state",
    "zipcode",
    "current_company",
    "gender",
    "visa_status",
    "origin_or_ethnicity",
    "veteran_status",
    "disability_status",
    "university",
    "degree",
    "major",
    "duration",
    "availability",
]


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    account: "AccountOut"


class AccountOut(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    last_login_at: datetime | None = None
    last_seen_at: datetime | None = None
    login_status: str
    bidder_id: int | None = None
    bidder_name: str | None = None

    model_config = {"from_attributes": True}


class BidderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=4)
    crypto_address: str = ""
    pay_amount_per_apply: float = Field(default=0, ge=0)
    status: str = "active"


class BidderUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    password: str | None = None
    crypto_address: str | None = None
    pay_amount_per_apply: float | None = Field(default=None, ge=0)
    status: str | None = None
    is_active: bool | None = None


class BidderOut(BaseModel):
    id: int
    account_id: int
    name: str
    email: str
    crypto_address: str
    pay_amount_per_apply: float
    status: str
    is_active: bool
    login_status: str
    last_login_at: datetime | None = None
    last_seen_at: datetime | None = None
    profile_ids: list[int] = []
    created_at: datetime | None = None


class AdminCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=4)


class AdminUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = None
    is_active: bool | None = None


class AdminOut(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    login_status: str
    last_login_at: datetime | None = None
    last_seen_at: datetime | None = None
    created_at: datetime | None = None


class ProfileInfo(BaseModel):
    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""
    personal_website: str = ""
    portfolio: str = ""
    race: str = ""
    salary: str = ""
    date_of_birth: str = ""
    asian_region: str = ""
    street: str = ""
    city: str = ""
    state: str = ""
    zipcode: str = ""
    current_company: str = ""
    gender: str = ""
    visa_status: str = ""
    origin_or_ethnicity: str = ""
    veteran_status: str = ""
    disability_status: str = ""
    university: str = ""
    degree: str = ""
    major: str = ""
    duration: str = ""
    availability: str = ""


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    info: dict[str, Any] = Field(default_factory=dict)


class ProfileUpdate(BaseModel):
    name: str | None = None
    info: dict[str, Any] | None = None


class ProfileOut(BaseModel):
    id: int
    name: str
    info: dict[str, Any]
    resume_filename: str | None = None
    has_resume: bool = False
    assigned_account_ids: list[int] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AssignProfileIn(BaseModel):
    account_id: int | None = None
    profile_ids: list[int] | None = None


class JobImportIn(BaseModel):
    profile_id: int
    text: str = ""


class JobListingOut(BaseModel):
    id: int
    profile_id: int
    profile_name: str
    company: str
    title: str
    url: str
    created_at: datetime | None = None
    my_application: "JobApplicationOut | None" = None
    applications: list["JobApplicationOut"] = []


class JobApplicationOut(BaseModel):
    id: int
    listing_id: int
    bidder_id: int
    bidder_name: str
    bidder_status: str
    review_status: str
    needs_human_review: bool
    reviewed_at: datetime | None = None
    review_notes: str = ""
    matched_email_id: int | None = None
    candidate_email_ids: list[int] = []
    applied_at: datetime | None = None
    company: str = ""
    title: str = ""
    url: str = ""
    profile_id: int | None = None
    profile_name: str | None = None


class BidderStatusIn(BaseModel):
    bidder_status: str


class ManualReviewIn(BaseModel):
    review_status: str
    notes: str = ""


class ProfileGroupOut(BaseModel):
    profile: ProfileOut
    listings: list[JobListingOut]


class DashboardBidderRow(BaseModel):
    bidder_id: int
    name: str
    apply_count: int
    interview_count: int
    passed_count: int
    failed_count: int
    pay_amount: float
    pay_amount_per_apply: float
    last_week_passed: int
    last_week_pay: float
    this_week_passed: int
    this_week_pay: float
    last_week_paid: bool


class ChartPoint(BaseModel):
    date: str
    job_apply: int = 0
    interview: int = 0


class PayoutAlert(BaseModel):
    is_monday: bool
    week_start: date
    week_end: date
    total_amount: float
    total_passed: int
    rows: list[DashboardBidderRow]


class DashboardOut(BaseModel):
    role: str
    is_monday: bool
    payout_alert: PayoutAlert | None = None
    bidders: list[DashboardBidderRow] = []
    chart: list[ChartPoint] = []
    this_week_pay: float = 0
    this_week_passed: int = 0
    apply_count: int = 0
    interview_count: int = 0
    passed_count: int = 0
    pay_amount: float = 0


class MarkPaidIn(BaseModel):
    bidder_id: int | None = None
    week_start: date | None = None


class PayoutOut(BaseModel):
    id: int
    bidder_id: int
    bidder_name: str
    week_start: date
    amount: float
    passed_count: int
    paid_at: datetime
    slack_sent: bool
    slack_error: str = ""


class MarkPaidOut(BaseModel):
    payouts: list[PayoutOut]
    slack_warning: str | None = None


class ReviewResultOut(BaseModel):
    application: JobApplicationOut
    outcome: str
    notes: str = ""


TokenOut.model_rebuild()
JobListingOut.model_rebuild()
