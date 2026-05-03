"""
Chat repository — CRUD operations for Users, Sessions, and Messages.

Bu katman doğrudan SQL bilmeden veri erişimi sağlar.
Tüm public metodlar async'tir ve AsyncSession alır.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import MessageModel, SessionModel, UserModel

logger = logging.getLogger(__name__)


class ChatRepository:
    """
    Veritabanı CRUD işlemlerini saran repository katmanı.

    Kullanım:
        repo = ChatRepository(session)
        user = await repo.get_or_create_user("905551234567", "whatsapp")
        session = await repo.get_or_create_active_session(user.id, "905551234567")
        await repo.save_message(session.id, "user", "Merhaba!")
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── Kullanıcı İşlemleri ─────────────────────────────────────────────────

    async def get_or_create_user(
        self,
        phone_number: str,
        channel_type: str = "whatsapp",
        language: str = "tr",
    ) -> UserModel:
        """
        Verilen telefon numarasına ait kullanıcıyı döndürür.
        Yoksa yeni kayıt oluşturur.
        """
        stmt = select(UserModel).where(
            UserModel.phone_number == phone_number,
            UserModel.channel_type == channel_type,
        )
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            user = UserModel(
                phone_number=phone_number,
                channel_type=channel_type,
                language=language,
            )
            self.session.add(user)
            await self.session.flush()  # ID üretmek için flush (commit olmadan)
            logger.info(f"New user created: {phone_number} ({channel_type})")
        else:
            # Son görülme zamanını güncelle
            user.last_seen_at = datetime.now(timezone.utc)

        return user

    async def update_user_language(self, user_id: int, language: str) -> None:
        """Kullanıcının tercih ettiği dili güncelle."""
        stmt = (
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(language=language)
        )
        await self.session.execute(stmt)

    # ─── Oturum İşlemleri ────────────────────────────────────────────────────

    async def get_active_session(
        self,
        user_id: int,
        timeout_minutes: int = 60,
    ) -> Optional[SessionModel]:
        """
        Kullanıcının aktif ve süresi dolmamış oturumunu döndürür.
        Yoksa None döner.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

        stmt = (
            select(SessionModel)
            .where(
                SessionModel.user_id == user_id,
                SessionModel.is_active == True,
                SessionModel.last_activity >= cutoff,
            )
            .order_by(SessionModel.last_activity.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_session(
        self,
        user_id: int,
        channel_id: str,
    ) -> SessionModel:
        """Yeni bir oturum oluştur ve kaydet."""
        db_session = SessionModel(
            user_id=user_id,
            channel_id=channel_id,
            is_active=True,
        )
        self.session.add(db_session)
        await self.session.flush()
        logger.info(f"New session created: {db_session.session_uuid} for user_id={user_id}")
        return db_session

    async def update_session_activity(self, session_id: int) -> None:
        """Oturumun son aktivite zamanını ve mesaj sayısını güncelle."""
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                last_activity=datetime.now(timezone.utc),
                message_count=SessionModel.message_count + 1,
            )
        )
        await self.session.execute(stmt)

    async def deactivate_session(self, session_id: int) -> None:
        """Oturumu pasif yap (timeout veya kullanıcı vedası)."""
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(is_active=False)
        )
        await self.session.execute(stmt)
        logger.info(f"Session deactivated: id={session_id}")

    async def deactivate_all_user_sessions(self, user_id: int) -> None:
        """Bir kullanıcının tüm aktif oturumlarını kapat."""
        stmt = (
            update(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.is_active == True)
            .values(is_active=False)
        )
        await self.session.execute(stmt)

    # ─── Mesaj İşlemleri ─────────────────────────────────────────────────────

    async def save_message(
        self,
        session_id: int,
        role: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> MessageModel:
        """
        Bir mesajı veritabanına kaydet.

        Args:
            session_id: Bağlı oturum ID'si
            role: 'user' veya 'assistant'
            content: Mesaj metni
            metadata: Opsiyonel ekstra bilgiler (örn: mesaj_id, intent)
        """
        message = MessageModel(
            session_id=session_id,
            role=role,
            content=content,
            metadata_json=metadata or None,
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def get_session_messages(
        self,
        session_id: int,
        limit: int = 20,
    ) -> list[MessageModel]:
        """
        Oturumdaki son N mesajı tarihe göre sıralı döndür.
        Gemini'ye bağlam olarak verilecek.
        """
        stmt = (
            select(MessageModel)
            .where(MessageModel.session_id == session_id)
            .order_by(MessageModel.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        messages = result.scalars().all()
        # Kronolojiik sıraya çevir (en eski başta)
        return list(reversed(messages))

    async def get_message_count(self, session_id: int) -> int:
        """Oturumdaki toplam mesaj sayısını döndür."""
        from sqlalchemy import func as sqlfunc
        stmt = select(sqlfunc.count()).select_from(MessageModel).where(
            MessageModel.session_id == session_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one() or 0

    # ─── Toplu İşlemler ──────────────────────────────────────────────────────

    async def get_or_create_active_session(
        self,
        user_id: int,
        channel_id: str,
        timeout_minutes: int = 60,
    ) -> tuple[SessionModel, bool]:
        """
        Aktif oturum bul veya yeni oluştur.

        Returns:
            (session, is_new) — is_new=True ise yeni oluşturuldu
        """
        existing = await self.get_active_session(user_id, timeout_minutes)
        if existing:
            return existing, False

        # Eski oturumları kapat
        await self.deactivate_all_user_sessions(user_id)
        new_session = await self.create_session(user_id, channel_id)
        return new_session, True
