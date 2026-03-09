"""
Message processor interface for orchestrating the processing pipeline
"""

from abc import ABC, abstractmethod
from ..models.standardMessage import StandardMessage


class MessageProcessor(ABC):
    """Interface for message processing orchestration"""
    
    @abstractmethod
    async def processMessage(self, message: StandardMessage) -> str:
        """Process incoming message through the complete pipeline
        
        Args:
            message: Standardized message from any channel
            
        Returns:
            str: Generated response to send back
        """
        pass
