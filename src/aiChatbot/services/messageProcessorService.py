"""
Message processor service for orchestrating the message processing pipeline.
Milestone 6: Her kullanıcı mesajı ve AI cevabı PostgreSQL'e kaydedilir.
"""

import logging
from typing import Optional

from ..interfaces.messageProcessor import MessageProcessor
from ..interfaces.aiService import AIService
from ..models.standardMessage import StandardMessage
from ..utils.languageDetector import LanguageDetector
from .sessionManager import SessionManager

logger = logging.getLogger(__name__)


class MessageProcessorService(MessageProcessor):
    """
    Orchestrates the message processing pipeline.
    Integrates AI service, session management, language detection,
    and persistent message storage (PostgreSQL — Milestone 6).
    """

    def __init__(
        self,
        aiService: AIService,
        sessionManager: SessionManager,
        defaultLanguage: str = "tr",
    ):
        self.aiService = aiService
        self.sessionManager = sessionManager
        self.languageDetector = LanguageDetector()
        self.defaultLanguage = defaultLanguage

        logger.info("MessageProcessorService initialized")

    async def processMessage(self, message: StandardMessage) -> str:
        """
        Process incoming message through the complete pipeline.

        1. Get or create session (RAM + PostgreSQL)
        2. Detect language
        3. Update user language in DB
        4. Save user message to PostgreSQL
        5. Process with AI service
        6. Save assistant response to PostgreSQL
        7. Return response
        """
        try:
            # ── 1. Get or create session ──────────────────────────────────────
            session = await self.sessionManager.getOrCreateSession(
                userId=message.userId,
                channelId=message.channelId,
                channelType=message.channelType,
            )

            # ── 2. Detect language ────────────────────────────────────────────
            detectedLanguage = self.languageDetector.detectLanguage(message.content)
            session.language = detectedLanguage

            # ── 3. Update user language in PostgreSQL (fire-and-forget) ───────
            await self.sessionManager.updateUserLanguage(
                userId=message.userId,
                channelType=message.channelType,
                language=detectedLanguage,
            )

            # ── 4. Save user message to PostgreSQL ────────────────────────────
            await self.sessionManager.saveUserMessage(
                userId=message.userId,
                channelType=message.channelType,
                content=message.content,
                metadata={"messageId": message.messageId},
            )

            # ── 5. Process message with AI service ────────────────────────────
            response = await self.aiService.processMessage(
                session=session,
                message=message.content,
            )

            # ── 6. Save assistant response to PostgreSQL ──────────────────────
            await self.sessionManager.saveAssistantMessage(
                userId=message.userId,
                channelType=message.channelType,
                content=response,
            )

            logger.info(
                f"Message processed",
                extra={
                    "userId": message.userId,
                    "channelType": message.channelType,
                    "language": detectedLanguage,
                    "responseLength": len(response),
                }
            )

            return response

        except Exception as e:
            logger.error(
                f"Error processing message from {message.userId}: {e}",
                exc_info=True,
            )
            return "Üzgünüm, bir hata oluştu. Lütfen tekrar deneyin veya 📞 444 09 10 ile iletişime geçin."
