"""
Gemini AI Service implementation using Google GenAI SDK (AI Studio).
Combines template's clean architecture with İşbir's knowledge base and intent features.
"""

import logging
from typing import Optional

from google import genai

from ..interfaces.aiService import AIService
from ..models.chatSession import ChatSession
from ..models.botConfig import BotConfig
from ..utils.promptManager import PromptManager
from ..utils.languageDetector import LanguageDetector
from .sessionManager import SessionManager
from .knowledgeBase import LightweightKnowledgeBase
from .intentDetector import (
    isSimpleGreeting,
    isPurePriceQuestion,
    isGoodbye,
    removeEchoOpening,
    getPriceResponse,
    getGoodbyeResponse,
)
from .businessHours import isOutsideBusinessHours, getOutOfHoursMessage

logger = logging.getLogger(__name__)


class GeminiAIService(AIService):
    """
    AI service using Google GenAI SDK (AI Studio) for Gemini integration.
    Combines template architecture with İşbir's knowledge base and intent detection.
    """
    
    def __init__(
        self,
        config: BotConfig,
        sessionManager: SessionManager,
        knowledgeBase: Optional[LightweightKnowledgeBase] = None,
        promptManager: Optional[PromptManager] = None,
    ):
        self.config = config
        self.sessionManager = sessionManager
        self.knowledgeBase = knowledgeBase
        self.promptManager = promptManager or PromptManager()
        self.languageDetector = LanguageDetector()
        
        logger.info(
            "GeminiAIService initialized",
            extra={
                "hasKnowledgeBase": knowledgeBase is not None,
            }
        )
    
    async def createSession(self, userId: str, channelType: str) -> ChatSession:
        """Create a new chat session"""
        return await self.sessionManager.getOrCreateSession(
            userId=userId,
            channelId=userId,
            channelType=channelType,
        )
    
    async def getSession(self, sessionId: str) -> Optional[ChatSession]:
        """Retrieve an existing chat session"""
        return await self.sessionManager.getSession(sessionId)
    
    async def processMessage(
        self,
        session: ChatSession,
        message: str,
    ) -> str:
        """
        Process a user message and generate AI response.
        Handles intent detection shortcuts and Gemini AI responses.
        """
        try:
            # 0. Business hours check
            if isOutsideBusinessHours(
                hoursStart=self.config.businessHoursStart,
                hoursEnd=self.config.businessHoursEnd,
                timezone_name=self.config.businessTimezone,
                businessDays=self.config.businessDays,
            ):
                logger.info("Outside business hours — OOH message sent", extra={"userId": session.userId})
                return getOutOfHoursMessage()
            
            # 1. Goodbye shortcut
            if isGoodbye(message):
                return getGoodbyeResponse()
            
            # 2. Pure price question shortcut
            if isPurePriceQuestion(message):
                return getPriceResponse()
            
            # 3. Normal Gemini AI processing (greetings also go through AI for richer response)
            return await self._generateGeminiResponse(session, message)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            language = session.language or "tr"
            return self.promptManager.getErrorMessage(language)
    
    async def _generateGeminiResponse(
        self,
        session: ChatSession,
        message: str,
    ) -> str:
        """Generate response using Gemini AI with knowledge base context"""
        try:
            # Get knowledge base context if available
            kbContext = ""
            if self.knowledgeBase:
                kbContext = self.knowledgeBase.findRelevantContent(message) or ""
            
            # Build the user prompt with knowledge context
            userPrompt = self._buildUserPrompt(message, kbContext)
            
            # Use native Gemini chat session for response
            geminiChat = session.geminiSession
            if geminiChat is None:
                logger.warning("No Gemini session found, creating new one")
                session = await self.createSession(session.userId, session.channelType)
                geminiChat = session.geminiSession
            
            response = geminiChat.send_message(userPrompt)
            
            if not response or not response.text:
                logger.warning("Empty response from Gemini")
                return self.promptManager.getErrorMessage(session.language)
            
            # Clean up echoes from the response
            answer = removeEchoOpening(response.text.strip())
            
            # Update session activity
            session.updateActivity()
            
            logger.info(
                f"Gemini response generated",
                extra={
                    "userId": session.userId,
                    "responseLength": len(answer),
                    "hasKBContext": bool(kbContext),
                }
            )
            
            return answer
            
        except Exception as e:
            logger.error(f"Gemini response error: {e}", exc_info=True)
            raise
    
    def _buildUserPrompt(self, message: str, kbContext: str) -> str:
        """Build the user prompt with knowledge base context"""
        parts = [f"Kullanıcı Sorusu: {message}"]
        
        if kbContext:
            parts.append(f"\nBilgi Bankası:\n{kbContext}")
        
        return "\n".join(parts)
