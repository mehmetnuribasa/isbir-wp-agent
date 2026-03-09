"""
Session management service for chat sessions with Gemini AI SDK.
Uses Google GenAI SDK (AI Studio) for native chat session management.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any

from google import genai
from google.genai import types

from ..models.chatSession import ChatSession

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages chat sessions for multiple users.
    Handles creation, retrieval, cleanup, and native Gemini chat sessions.
    """
    
    def __init__(
        self,
        client: genai.Client,
        modelName: str = "gemini-2.5-flash",
        systemInstruction: str = "",
        sessionTimeoutMinutes: int = 60,
        cleanupIntervalSeconds: int = 300,
    ):
        self.client = client
        self.modelName = modelName
        self.systemInstruction = systemInstruction
        self.sessionTimeoutMinutes = sessionTimeoutMinutes
        self.cleanupIntervalSeconds = cleanupIntervalSeconds
        
        self._sessions: Dict[str, ChatSession] = {}
        self._cleanupTask: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        logger.info(
            "SessionManager initialized",
            extra={
                "model": modelName,
                "timeoutMinutes": sessionTimeoutMinutes,
            }
        )
    
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
        """Get existing session or create a new one"""
        async with self._lock:
            sessionKey = f"{channelType}:{userId}"
            
            if sessionKey in self._sessions:
                session = self._sessions[sessionKey]
                if not session.isExpired(self.sessionTimeoutMinutes):
                    session.updateActivity()
                    return session
                else:
                    logger.info(
                        f"Session expired for {userId}, creating new one",
                        extra={"userId": userId, "channelType": channelType}
                    )
                    del self._sessions[sessionKey]
            
            session = await self._createSession(userId, channelId, channelType)
            self._sessions[sessionKey] = session
            return session
    
    async def _createSession(
        self,
        userId: str,
        channelId: str,
        channelType: str,
    ) -> ChatSession:
        """Create a new chat session with Gemini SDK native session"""
        try:
            # Build config for Gemini chat
            config: Dict[str, Any] = {}
            if self.systemInstruction:
                config["system_instruction"] = self.systemInstruction
            
            # Create Gemini native chat session
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
            )
            
            session = ChatSession(
                userId=userId,
                channelId=channelId,
                channelType=channelType,
                geminiSession=geminiChat,
                language="tr",
            )
            
            logger.info(
                f"New session created for {userId}",
                extra={"userId": userId, "channelType": channelType, "sessionId": session.sessionId}
            )
            
            return session
            
        except Exception as e:
            logger.error(f"Error creating session for {userId}: {e}", exc_info=True)
            raise
    
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
        """Remove all expired sessions"""
        async with self._lock:
            expired = [
                key for key, session in self._sessions.items()
                if session.isExpired(self.sessionTimeoutMinutes)
            ]
            
            for key in expired:
                session = self._sessions.pop(key)
                session.deactivate()
            
            if expired:
                logger.info(
                    f"Cleaned up {len(expired)} expired sessions",
                    extra={"expiredCount": len(expired), "remainingCount": len(self._sessions)}
                )
    
    def getActiveSessionCount(self) -> int:
        """Get count of active sessions"""
        return len(self._sessions)
    
    def getStats(self) -> Dict[str, Any]:
        """Get session manager statistics"""
        return {
            "activeSessions": len(self._sessions),
            "model": self.modelName,
            "timeoutMinutes": self.sessionTimeoutMinutes,
        }
