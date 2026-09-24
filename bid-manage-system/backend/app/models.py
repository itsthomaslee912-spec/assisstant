from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Table, Text, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


user_profiles = Table(
    "user_profiles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("profile_id", ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    role: Mapped[str] = mapped_column(String(16), default="bidder", index=True)
    per_bid_pay_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    crypto_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    profiles: Mapped[list[Profile]] = relationship(secondary=user_profiles, back_populates="bidders")
    sessions: Mapped[list[AuthSession]] = relationship(cascade="all, delete-orphan")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), index=True)
    last_name: Mapped[str] = mapped_column(String(100), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    phone_number: Mapped[str] = mapped_column(String(50), default="")
    linkedin: Mapped[str] = mapped_column(String(500), default="")
    github: Mapped[str] = mapped_column(String(500), default="")
    personal_website: Mapped[str] = mapped_column(String(500), default="")
    portfolio: Mapped[str] = mapped_column(String(500), default="")
    race: Mapped[str] = mapped_column(String(100), default="")
    asian_region: Mapped[str] = mapped_column(String(40), default="")
    salary: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    street: Mapped[str] = mapped_column(String(255), default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    state: Mapped[str] = mapped_column(String(120), default="")
    zipcode: Mapped[str] = mapped_column(String(20), default="")
    current_company: Mapped[str] = mapped_column(String(255), default="")
    gender: Mapped[str] = mapped_column(String(80), default="")
    visa_status: Mapped[str] = mapped_column(String(120), default="")
    origin_ethnicity: Mapped[str] = mapped_column(String(150), default="")
    veteran_status: Mapped[str] = mapped_column(String(100), default="")
    disability_status: Mapped[str] = mapped_column(String(100), default="")
    university: Mapped[str] = mapped_column(String(255), default="")
    degree: Mapped[str] = mapped_column(String(150), default="")
    major: Mapped[str] = mapped_column(String(150), default="")
    duration: Mapped[str] = mapped_column(String(100), default="")
    availability: Mapped[str] = mapped_column(String(100), default="")
    resume_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    bidders: Mapped[list[User]] = relationship(secondary=user_profiles, back_populates="profiles")
    jobs: Mapped[list[JobApplication]] = relationship(cascade="all, delete-orphan", back_populates="profile")


class JobApplication(Base):
    __tablename__ = "job_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    company_name: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(255), index=True)
    job_link: Mapped[str] = mapped_column(String(1000), default="")
    work_model: Mapped[str] = mapped_column(String(20), default="remote", index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    bot_check_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    bot_check_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    application_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Recorded only when the assigned bidder moves the job to Applied or Canceled.
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    profile: Mapped[Profile] = relationship(back_populates="jobs")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
