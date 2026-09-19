from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AccountRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    USER = "user"


class BidderRecordStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class BidderJobStatus(str, Enum):
    PENDING = "pending"
    CANCEL = "cancel"
    APPLIED = "applied"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bidder: Mapped[Bidder | None] = relationship(back_populates="account", uselist=False)
    assignments: Mapped[list[ProfileAssignment]] = relationship(back_populates="account")


class Bidder(Base):
    __tablename__ = "bidders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    crypto_address: Mapped[str] = mapped_column(String(255), default="")
    pay_amount_per_apply: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(32), default=BidderRecordStatus.ACTIVE.value, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    account: Mapped[Account] = relationship(back_populates="bidder")
    applications: Mapped[list[JobApplication]] = relationship(back_populates="bidder")
    payouts: Mapped[list[WeeklyPayout]] = relationship(back_populates="bidder")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    info: Mapped[str] = mapped_column(Text, default="{}")
    resume_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resume_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    assignments: Mapped[list[ProfileAssignment]] = relationship(back_populates="profile")
    listings: Mapped[list[JobListing]] = relationship(back_populates="profile")


class ProfileAssignment(Base):
    __tablename__ = "profile_assignments"
    __table_args__ = (UniqueConstraint("account_id", "profile_id", name="uq_account_profile"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[Account] = relationship(back_populates="assignments")
    profile: Mapped[Profile] = relationship(back_populates="assignments")


class JobListing(Base):
    __tablename__ = "job_listings"
    __table_args__ = (UniqueConstraint("profile_id", "url", name="uq_profile_job_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    company: Mapped[str] = mapped_column(String(255), default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    url: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profile: Mapped[Profile] = relationship(back_populates="listings")
    applications: Mapped[list[JobApplication]] = relationship(back_populates="listing")


class JobApplication(Base):
    __tablename__ = "job_applications"
    __table_args__ = (UniqueConstraint("listing_id", "bidder_id", name="uq_listing_bidder"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("job_listings.id"), index=True)
    bidder_id: Mapped[int] = mapped_column(ForeignKey("bidders.id"), index=True)
    bidder_status: Mapped[str] = mapped_column(
        String(32), default=BidderJobStatus.PENDING.value, index=True
    )
    review_status: Mapped[str] = mapped_column(
        String(32), default=ReviewStatus.PENDING.value, index=True
    )
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str] = mapped_column(Text, default="")
    matched_email_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_email_ids: Mapped[str] = mapped_column(Text, default="[]")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    listing: Mapped[JobListing] = relationship(back_populates="applications")
    bidder: Mapped[Bidder] = relationship(back_populates="applications")


class WeeklyPayout(Base):
    __tablename__ = "weekly_payouts"
    __table_args__ = (UniqueConstraint("bidder_id", "week_start", name="uq_bidder_week"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bidder_id: Mapped[int] = mapped_column(ForeignKey("bidders.id"), index=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Float, default=0)
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    slack_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    slack_error: Mapped[str] = mapped_column(Text, default="")

    bidder: Mapped[Bidder] = relationship(back_populates="payouts")
