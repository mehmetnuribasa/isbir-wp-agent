"""
Session management service for chat sessions with Gemini AI SDK.
Milestone 6: Hybrid approach — Gemini native sessions (RAM) + PostgreSQL persistence.

Akış:
    1. Kullanıcı mesaj gönderir
    2. PostgreSQL'den aktif oturum bulunur (veya yeni oluşturulur)
    3. Gemini native chat session RAM'de tutulur (SDK bunu gerektiriyor)
    4. Mesajlar PostgreSQL'e de kaydedilir (kalıcı)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any

from google import genai
from google.genai import types

from ..models.chatSession import ChatSession
from ..database.connection import DatabaseManager
from ..database.repository import ChatRepository

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages chat sessions for multiple users.
    Handles creation, retrieval, cleanup, and native Gemini chat sessions.

    Milestone 6: PostgreSQL entegrasyonu ile kalıcı oturum yönetimi.
    - RAM cache: Gemini SDK native session (hız için)
    - PostgreSQL: Kullanıcı, oturum ve mesaj geçmişi (kalıcılık için)
    """

    def __init__(
        self,
        client: genai.Client,
        modelName: str = "gemini-2.5-flash",
        systemInstruction: str = "",
        sessionTimeoutMinutes: int = 60,
        cleanupIntervalSeconds: int = 300,
        dbManager: Optional[DatabaseManager] = None,
    ):
        self.client = client
        self.modelName = modelName
        self.systemInstruction = systemInstruction
        self.sessionTimeoutMinutes = sessionTimeoutMinutes
        self.cleanupIntervalSeconds = cleanupIntervalSeconds
        self.dbManager = dbManager  # None ise sadece RAM (eski davranış)

        # RAM cache: sessionKey -> ChatSession (Gemini SDK session'ı içerir)
        self._sessions: Dict[str, ChatSession] = {}
        # RAM cache: sessionKey -> db session id (PostgreSQL row ID)
        self._db_session_ids: Dict[str, int] = {}

        self._cleanupTask: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        postgres_status = "✓ enabled" if dbManager and dbManager.is_initialized else "✗ disabled (RAM only)"
        logger.info(
            f"SessionManager initialized | model={modelName} | PostgreSQL={postgres_status}",
        )

    @property
    def _db_enabled(self) -> bool:
        return self.dbManager is not None and self.dbManager.is_initialized

    async def startCleanup(self) -> None:
        """Start periodic session cleanup task"""
        if self._cleanupTask is None or self._cleanupTask.done():
            self._cleanupTask = asyncio.create_task(self._periodicCleanup())
            logger.info("Session cleanup task started")

    async def stopCleanup(self) -> None:
        """Stop periodic cleanup task"""
        if self._cleanupTask and not self._cleanupTask.done():
            self._cleanupTask.cancel()
            try:
                await self._cleanupTask
            except asyncio.CancelledError:
                pass
            logger.info("Session cleanup task stopped")

    async def getOrCreateSession(
        self,
        userId: str,
        channelId: str,
        channelType: str = "whatsapp",
    ) -> ChatSession:
        """
        Get existing session or create a new one.
        PostgreSQL varsa oradan kontrol eder, yoksa RAM'e düşer.
        """
        async with self._lock:
            sessionKey = f"{channelType}:{userId}"

            # ── 1. RAM cache kontrolü ───────────────────────────────────────
            if sessionKey in self._sessions:
                session = self._sessions[sessionKey]
                if not session.isExpired(self.sessionTimeoutMinutes):
                    session.updateActivity()
                    # PostgreSQL'deki activity'yi de güncelle (fire-and-forget)
                    if self._db_enabled and sessionKey in self._db_session_ids:
                        asyncio.create_task(
                            self._updateDbActivity(self._db_session_ids[sessionKey])
                        )
                    return session
                else:
                    logger.info(f"Session expired for {userId}, creating new one")
                    # PostgreSQL'de oturumu kapat
                    if self._db_enabled and sessionKey in self._db_session_ids:
                        asyncio.create_task(
                            self._deactivateDbSession(self._db_session_ids[sessionKey])
                        )
                    del self._sessions[sessionKey]
                    self._db_session_ids.pop(sessionKey, None)

            # ── 2. PostgreSQL'den oturum ve geçmişi çek (Eğer varsa) ────────
            dbSessionId = None
            dbHistory = []
            
            if self._db_enabled:
                dbSessionId, dbHistory = await self._persistAndFetchHistory(
                    userId, channelId, channelType
                )
                if dbSessionId:
                    self._db_session_ids[sessionKey] = dbSessionId

            # ── 3. Yeni oturum oluştur (Geçmişle beraber) ───────────────────
            session = await self._createSession(userId, channelId, channelType, history=dbHistory)
            self._sessions[sessionKey] = session

            return session

    async def saveUserMessage(
        self,
        userId: str,
        channelType: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Kullanıcı mesajını PostgreSQL'e kaydet.
        PostgreSQL kapalıysa sessizce atla.
        """
        if not self._db_enabled:
            return

        sessionKey = f"{channelType}:{userId}"
        dbSessionId = self._db_session_ids.get(sessionKey)
        if dbSessionId is None:
            return

        try:
            async with self.dbManager.session() as db:
                repo = ChatRepository(db)
                await repo.save_message(dbSessionId, "user", content, metadata)
                await repo.update_session_activity(dbSessionId)
        except Exception as e:
            logger.error(f"Failed to save user message to DB: {e}", exc_info=True)

    async def saveAssistantMessage(
        self,
        userId: str,
        channelType: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        AI cevabını PostgreSQL'e kaydet.
        PostgreSQL kapalıysa sessizce atla.
        """
        if not self._db_enabled:
            return

        sessionKey = f"{channelType}:{userId}"
        dbSessionId = self._db_session_ids.get(sessionKey)
        if dbSessionId is None:
            return

        try:
            async with self.dbManager.session() as db:
                repo = ChatRepository(db)
                await repo.save_message(dbSessionId, "assistant", content, metadata)
        except Exception as e:
            logger.error(f"Failed to save assistant message to DB: {e}", exc_info=True)

    async def updateUserLanguage(
        self,
        userId: str,
        channelType: str,
        language: str,
    ) -> None:
        """Kullanıcının dilini PostgreSQL'de güncelle."""
        if not self._db_enabled:
            return

        try:
            async with self.dbManager.session() as db:
                repo = ChatRepository(db)
                # Kullanıcıyı bul ve dilini güncelle
                user = await repo.get_or_create_user(userId, channelType, language)
                await repo.update_user_language(user.id, language)
        except Exception as e:
            logger.error(f"Failed to update user language: {e}", exc_info=True)

    async def _createSession(
        self,
        userId: str,
        channelId: str,
        channelType: str,
        history: Optional[list] = None,
    ) -> ChatSession:
        """Create a new chat session with Gemini SDK native session"""
        try:
            geminiChat = self.client.chats.create(
                model=self.modelName,
                config=types.GenerateContentConfig(
                    system_instruction=self.systemInstruction or None,
                    safety_settings=[
                        types.SafetySetting(
                            category="HARM_CATEGORY_HARASSMENT",
                            threshold="BLOCK_ONLY_HIGH",
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_HATE_SPEECH",
                            threshold="BLOCK_ONLY_HIGH",
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                            threshold="BLOCK_ONLY_HIGH",
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_DANGEROUS_CONTENT",
                            threshold="BLOCK_ONLY_HIGH",
                        ),
                    ],
                    temperature=0.2,
                    max_output_tokens=800,
                ),
                history=history,
            )

            session = ChatSession(
                userId=userId,
                channelId=channelId,
                channelType=channelType,
                geminiSession=geminiChat,
                language="tr",
            )

            logger.info(
                f"New Gemini session created for {userId}",
                extra={"userId": userId, "channelType": channelType, "sessionId": session.sessionId}
            )

            return session

        except Exception as e:
            logger.error(f"Error creating session for {userId}: {e}", exc_info=True)
            raise

    async def _persistAndFetchHistory(
        self,
        userId: str,
        channelId: str,
        channelType: str,
    ) -> tuple[Optional[int], list]:
        """PostgreSQL'de oturum kaydı yapar ve varsa geçmiş mesajları Gemini formatında döner."""
        try:
            async with self.dbManager.session() as db:
                repo = ChatRepository(db)

                # Kullanıcıyı bul veya oluştur
                user = await repo.get_or_create_user(userId, channelType)

                # Aktif oturum bul veya yeni oluştur
                db_session, is_new = await repo.get_or_create_active_session(
                    user.id, channelId, self.sessionTimeoutMinutes
                )

                history = []
                if is_new:
                    logger.info(f"New DB session created: {db_session.session_uuid}")
                else:
                    # Eski mesajları çek (Gemini için)
                    messages = await repo.get_session_messages(db_session.id, limit=20)
                    for msg in messages:
                        # Gemini'nin beklediği role formatına çevir (assistant -> model)
                        role = "model" if msg.role == "assistant" else "user"
                        history.append(
                            types.Content(role=role, parts=[types.Part.from_text(text=msg.content)])
                        )
                    if history:
                        logger.info(f"Loaded {len(history)} historical messages from DB for user {userId}")

                return db_session.id, history

        except Exception as e:
            logger.error(f"Failed to persist/fetch session from DB: {e}", exc_info=True)
            return None, []

    async def _updateDbActivity(self, dbSessionId: int) -> None:
        """Arka planda DB oturumunun aktivite zamanını güncelle."""
        try:
            async with self.dbManager.session() as db:
                repo = ChatRepository(db)
                await repo.update_session_activity(dbSessionId)
        except Exception as e:
            logger.debug(f"DB activity update failed (non-critical): {e}")

    async def _deactivateDbSession(self, dbSessionId: int) -> None:
        """Arka planda DB oturumunu kapat."""
        try:
            async with self.dbManager.session() as db:
                repo = ChatRepository(db)
                await repo.deactivate_session(dbSessionId)
        except Exception as e:
            logger.debug(f"DB session deactivation failed (non-critical): {e}")

    async def getSession(self, sessionId: str) -> Optional[ChatSession]:
        """Get a session by its ID"""
        async with self._lock:
            for session in self._sessions.values():
                if session.sessionId == sessionId:
                    return session
        return None

    async def removeSession(self, userId: str, channelType: str = "whatsapp") -> None:
        """Remove a session"""
        async with self._lock:
            sessionKey = f"{channelType}:{userId}"
            if sessionKey in self._sessions:
                session = self._sessions.pop(sessionKey)
                session.deactivate()

                # PostgreSQL'de de kapat
                if self._db_enabled and sessionKey in self._db_session_ids:
                    dbSessionId = self._db_session_ids.pop(sessionKey)
                    asyncio.create_task(self._deactivateDbSession(dbSessionId))

                logger.info(f"Session removed for {userId}")

    async def _periodicCleanup(self) -> None:
        """Periodically clean up expired sessions"""
        while True:
            try:
                await asyncio.sleep(self.cleanupIntervalSeconds)
                await self._cleanupExpiredSessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}", exc_info=True)

    async def _cleanupExpiredSessions(self) -> None:
        """Remove all expired sessions from RAM cache"""
        async with self._lock:
            expired = [
                key for key, session in self._sessions.items()
                if session.isExpired(self.sessionTimeoutMinutes)
            ]

            for key in expired:
                session = self._sessions.pop(key)
                session.deactivate()

                # PostgreSQL'de de kapat
                if self._db_enabled and key in self._db_session_ids:
                    dbSessionId = self._db_session_ids.pop(key)
                    asyncio.create_task(self._deactivateDbSession(dbSessionId))

            if expired:
                logger.info(
                    f"Cleaned up {len(expired)} expired sessions",
                    extra={"expiredCount": len(expired), "remainingCount": len(self._sessions)}
                )

    def getActiveSessionCount(self) -> int:
        """Get count of active sessions in RAM"""
        return len(self._sessions)

    def getStats(self) -> Dict[str, Any]:
        """Get session manager statistics"""
        return {
            "activeSessions": len(self._sessions),
            "model": self.modelName,
            "timeoutMinutes": self.sessionTimeoutMinutes,
            "postgresEnabled": self._db_enabled,
        }
