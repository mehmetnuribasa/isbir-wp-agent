"""
SQLAlchemy ORM models for PostgreSQL (Milestone 6).

Tables:
    users    — WhatsApp kullanıcı kaydı (phone_number bazlı)
    sessions — Her kullanıcının sohbet oturumları
    messages — Oturum içindeki tüm mesajlar (user + assistant)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """SQLAlchemy base class for all ORM models."""
    pass


class UserModel(Base):
    """
    WhatsApp kullanıcı kaydı.
    Her kullanıcı phone_number + channel_type kombinasyonuyla eşsiz tanımlanır.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False, default="whatsapp")
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="tr")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Her (phone_number, channel_type) çifti benzersiz olmalı
    __table_args__ = (
        UniqueConstraint("phone_number", "channel_type", name="uq_user_phone_channel"),
    )

    # İlişkiler
    sessions: Mapped[list["SessionModel"]] = relationship(
        "SessionModel", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} phone={self.phone_number} lang={self.language}>"


class SessionModel(Base):
    """
    Kullanıcının bir sohbet oturumu.
    Bir kullanıcının birden fazla (tarihsel) oturumu olabilir,
    ancak her an yalnızca bir tanesi is_active=True'dur.
    """
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_uuid: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # İlişkiler
    user: Mapped["UserModel"] = relationship("UserModel", back_populates="sessions")
    messages: Mapped[list["MessageModel"]] = relationship(
        "MessageModel", back_populates="session", cascade="all, delete-orphan",
        order_by="MessageModel.created_at"
    )

    def __repr__(self) -> str:
        return f"<Session id={self.id} uuid={self.session_uuid[:8]}... active={self.is_active}>"


class MessageModel(Base):
    """
    Bir oturumdaki tek bir mesaj.
    role: 'user' veya 'assistant'
    metadata_json: Ekstra bilgiler (örn: intent tipi, RAG bağlamı, mesaj ID)
    """
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    # Ekstra metadata (opsiyonel): mesaj ID, dil, hata kodu vs.
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=None)

    # İlişkiler
    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="messages")

    def __repr__(self) -> str:
        preview = self.content[:40].replace("\n", " ") if self.content else ""
        return f"<Message id={self.id} role={self.role} preview='{preview}...'>"
