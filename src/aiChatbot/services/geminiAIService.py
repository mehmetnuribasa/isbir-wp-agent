"""
Gemini AI Service implementation using Google GenAI SDK (AI Studio).
Combines template's clean architecture with İşbir's knowledge base and intent features.
Supports both RAG (semantic search) and keyword-based knowledge base.
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
from .ragService import RAGService

logger = logging.getLogger(__name__)


class GeminiAIService(AIService):
    """
    AI service using Google GenAI SDK (AI Studio) for Gemini integration.
    Combines template architecture with İşbir's knowledge base and intent detection.
    Uses RAG (ChromaDB + Gemini Embeddings) for semantic search.
    """
    
    def __init__(
        self,
        config: BotConfig,
        sessionManager: SessionManager,
        ragService: Optional[RAGService] = None,
        promptManager: Optional[PromptManager] = None,
    ):
        self.config = config
        self.sessionManager = sessionManager
        self.ragService = ragService
        self.promptManager = promptManager or PromptManager()
        self.languageDetector = LanguageDetector()
        
        logger.info("GeminiAIService initialized with RAG support")
    
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
            # Tüm mesajlar Gemini AI'a gönderiliyor — doğal ve bağlama uygun cevaplar için
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
        """Generate response using Gemini AI native session with Tool Calling"""
        try:
            # Use native Gemini chat session for response
            geminiChat = session.geminiSession
            if geminiChat is None:
                logger.warning("No Gemini session found, creating new one")
                session = await self.createSession(session.userId, session.channelType)
                geminiChat = session.geminiSession
            
            # Agentic RAG: Tool (araç) kullanımı Gemini tarafından otomatik yönetilir
            response = geminiChat.send_message(message)
            
            if not response or not response.text:
                logger.warning("Empty response from Gemini")
                return self.promptManager.getErrorMessage(session.language)
            
            # Doğrudan AI'ın cevabını kullanıyoruz
            answer = response.text.strip()
            
            # Update session activity
            session.updateActivity()
            
            logger.info(
                f"Gemini response generated",
                extra={
                    "userId": session.userId,
                    "responseLength": len(answer),
                }
            )
            
            return answer
            
        except Exception as e:
            logger.error(f"Gemini response error: {e}", exc_info=True)
            raise
    

