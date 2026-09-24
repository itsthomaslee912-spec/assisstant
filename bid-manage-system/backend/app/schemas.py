from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

Role = Literal["admin", "bidder"]
UserStatus = Literal["active", "deactive"]
JobStatus = Literal["pending", "applied", "canceled"]
WorkModel = Literal["", "on-site", "hybrid", "remote"]
BotCheckStatus = Literal["pending", "pass", "failure"]


class LoginIn(BaseModel):
    identity: str = Field(min_length=1)
    password: str = Field(min_length=1)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def password_must_change(self):
        if self.current_password == self.new_password:
            raise ValueError("New password must be different from the current password")
        return self


class ProfileSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    first_name: str
    last_name: str
    email: EmailStr


class UserBase(BaseModel):
    email: EmailStr
    user_id: str = Field(min_length=3, max_length=80)
    status: UserStatus = "active"
    role: Role = "bidder"
    per_bid_pay_amount: Decimal | None = Field(default=None, ge=0)
    crypto_address: str | None = None
    profile_ids: list[int] = []

    @model_validator(mode="after")
    def validate_role_fields(self):
        if self.role == "bidder":
            if self.per_bid_pay_amount is None:
                raise ValueError("Per-bid pay amount is required for bidders")
            if not (self.crypto_address or "").strip():
                raise ValueError("Crypto address is required for bidders")
        else:
            self.per_bid_pay_amount = None
            self.crypto_address = None
            self.profile_ids = []
        return self


class UserCreate(UserBase):
    password: str = Field(min_length=8)


class UserUpdate(UserBase):
    password: str | None = Field(default=None, min_length=8)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    user_id: str
    status: UserStatus
    role: Role
    per_bid_pay_amount: Decimal | None
    crypto_address: str | None
    profiles: list[ProfileSummary]
    created_at: datetime


class LoginOut(BaseModel):
    token: str
    user: UserOut


class ProfileBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone_number: str = ""
    linkedin: str = ""
    github: str = ""
    personal_website: str = ""
    portfolio: str = ""
    race: str = ""
    asian_region: str = ""
    salary: Decimal | None = Field(default=None, ge=0)
    date_of_birth: date | None = None
    street: str = ""
    city: str = ""
    state: str = ""
    zipcode: str = ""
    current_company: str = ""
    gender: str = ""
    visa_status: str = ""
    origin_ethnicity: str = ""
    veteran_status: str = ""
    disability_status: str = ""
    university: str = ""
    degree: str = ""
    major: str = ""
    duration: str = ""
    availability: str = ""


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(ProfileBase):
    pass


class ProfileOut(ProfileBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    resume_path: str | None
    created_at: datetime
    updated_at: datetime


class JobBase(BaseModel):
    profile_id: int
    company_name: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=255)
    job_link: str = ""
    work_model: WorkModel = "remote"
    status: JobStatus = "pending"
    bot_check_status: BotCheckStatus = "pending"
    application_date: date = Field(default_factory=date.today)


class JobCreate(JobBase):
    pass


class JobUpdate(JobBase):
    pass


class BidderJobUpdate(BaseModel):
    status: JobStatus
    work_model: WorkModel


class JobOut(JobBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    submitted_at: datetime | None
    updated_at: datetime


class BulkJobIn(BaseModel):
    profile_id: int
    text: str = Field(min_length=1)


class Page(BaseModel):
    items: list
    total: int
    page: int
    page_size: int


class SeriesPoint(BaseModel):
    label: str
    value: int


class BidderDashboard(BaseModel):
    profiles: list[ProfileSummary]
    applied_count: int
    bot_check_pass_count: int
    paid_amount: Decimal
    series: list[SeriesPoint]


class AdminBidderPay(BaseModel):
    user_id: int
    bidder_name: str
    bot_check_pass_count: int
    per_bid_pay_amount: Decimal
    paid_amount: Decimal


class AdminDashboard(BaseModel):
    total_profiles: int
    active_bidders: int
    applications_count: int
    paid_amount_total: Decimal
    pay_cards: list[AdminBidderPay]
    profiles: list[ProfileSummary]
    profile_series: dict[str, list[SeriesPoint]]
