from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class PostingMode(StrEnum):
    APPROVAL = "approval"
    AUTO = "auto"
    DRY_RUN = "dry_run"


class PostJobStatus(StrEnum):
    RECEIVED = "received"
    VALIDATING = "validating"
    VALIDATED = "validated"
    PROCESSING = "processing"
    PROCESSED = "processed"
    CAPTIONING = "captioning"
    CAPTIONED = "captioned"
    PREVIEW_SENT = "preview_sent"
    WAITING_APPROVAL = "waiting_approval"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    REJECTED = "rejected"
    FAILED = "failed"


class MediaAssetStatus(StrEnum):
    RECEIVED = "received"
    VALIDATED = "validated"
    PROCESSED = "processed"
    REJECTED = "rejected"
    FAILED = "failed"


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


class PostJob(Base):
    __tablename__ = "post_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default=PostingMode.APPROVAL.value)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=PostJobStatus.RECEIVED.value)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    alt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    x_post_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    media_assets: Mapped[list[MediaAsset]] = relationship(
        back_populates="post_job",
        cascade="all, delete-orphan",
    )
    post_attempts: Mapped[list[PostAttempt]] = relationship(
        back_populates="post_job",
        cascade="all, delete-orphan",
    )


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_job_id: Mapped[int] = mapped_column(ForeignKey("post_jobs.id"), nullable=False, index=True)
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    processed_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=MediaAssetStatus.RECEIVED.value)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    post_job: Mapped[PostJob] = relationship(back_populates="media_assets")


class PostAttempt(Base):
    __tablename__ = "post_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_job_id: Mapped[int] = mapped_column(ForeignKey("post_jobs.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    request_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    post_job: Mapped[PostJob] = relationship(back_populates="post_attempts")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
