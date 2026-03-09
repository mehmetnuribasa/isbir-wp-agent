"""
AI service interface for Gemini integration
"""

from abc import ABC, abstractmethod
from typing import Optional
from ..models.chatSession import ChatSession


class AIService(ABC):
    """Interface for AI processing services"""
    
    @abstractmethod
    async def createSession(self, userId: str, channelType: str) -> ChatSession:
        """Create a new chat session
        
        Args:
            userId: Unique user identifier
            channelType: Type of communication channel
            
        Returns:
            ChatSession: New chat session object
        """
        pass
    
    @abstractmethod
    async def processMessage(
        self,
        session: ChatSession,
        message: str,
    ) -> str:
        """Process user message and generate AI response
        
        Args:
            session: Active chat session
            message: User message content
            
        Returns:
            str: AI-generated response
        """
        pass
    
    @abstractmethod
    async def getSession(self, sessionId: str) -> Optional[ChatSession]:
        """Retrieve existing chat session
        
        Args:
            sessionId: Session identifier
            
        Returns:
            Optional[ChatSession]: Session if found, None otherwise
        """
        pass
