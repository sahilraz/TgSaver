"""SQLAlchemy async database models with multi-user isolation constraints."""

from datetime import datetime, timezone
import uuid
from typing import Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(64), nullable=True)
    first_name = Column(String(128), nullable=True)
    is_connected = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    session = relationship("UserSession", back_populates="user", uselist=False, cascade="all, delete-orphan")
    auth_state = relationship("AuthState", back_populates="user", uselist=False, cascade="all, delete-orphan")
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    mappings = relationship("ArchiveMapping", back_populates="user", cascade="all, delete-orphan")
    batches = relationship("BatchJob", back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"

    telegram_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True)
    encrypted_session = Column(Text, nullable=True)
    phone_number = Column(String(32), nullable=True)
    account_id = Column(BigInteger, nullable=True)
    account_first_name = Column(String(128), nullable=True)
    connected_at = Column(DateTime(timezone=True), nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="session")


class AuthState(Base):
    __tablename__ = "auth_states"

    telegram_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True)
    state = Column(String(32), default="IDLE", nullable=False)  # IDLE, AWAITING_PHONE, AWAITING_CODE, AWAITING_PASSWORD
    phone_number = Column(String(32), nullable=True)
    phone_code_hash = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="auth_state")


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True)
    is_paused = Column(Boolean, default=False, nullable=False)
    prefer_copy = Column(Boolean, default=True, nullable=False)
    auto_create_channels = Column(Boolean, default=True, nullable=False)

    user = relationship("User", back_populates="settings")


class ArchiveMapping(Base):
    __tablename__ = "archive_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    source_channel_ref = Column(String(128), nullable=False, index=True)
    source_title = Column(String(256), nullable=True)
    destination_channel_id = Column(BigInteger, nullable=False)
    destination_title = Column(String(256), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "source_channel_ref", name="uq_user_source_channel"),
    )

    user = relationship("User", back_populates="mappings")


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), default="QUEUED", nullable=False, index=True)  # QUEUED, RUNNING, COMPLETED, PARTIALLY_COMPLETED, FAILED, CANCELLED
    total_items = Column(Integer, default=0, nullable=False)
    completed_items = Column(Integer, default=0, nullable=False)
    failed_items = Column(Integer, default=0, nullable=False)
    skipped_items = Column(Integer, default=0, nullable=False)
    bytes_transferred = Column(BigInteger, default=0, nullable=False)
    status_message_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    user = relationship("User", back_populates="batches")
    items = relationship("ArchiveItem", back_populates="batch", cascade="all, delete-orphan")


class ArchiveItem(Base):
    __tablename__ = "archive_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(36), ForeignKey("batch_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    source_url = Column(String(512), nullable=False)
    source_channel_ref = Column(String(128), nullable=False, index=True)
    source_message_id = Column(Integer, nullable=False, index=True)
    destination_channel_id = Column(BigInteger, nullable=True)
    destination_message_id = Column(Integer, nullable=True)
    status = Column(String(32), default="QUEUED", nullable=False)  # QUEUED, RUNNING, COMPLETED, FAILED, SKIPPED, CANCELLED
    method = Column(String(32), default="NONE", nullable=False)  # COPY, TRANSFER, NONE
    file_name = Column(String(256), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    error_category = Column(String(64), nullable=True)
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "source_channel_ref", "source_message_id", name="uq_user_source_message"),
    )

    batch = relationship("BatchJob", back_populates="items")
