"""
Base interface for all communication channel adapters
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
from ..models.standardMessage import StandardMessage


class ChannelAdapterError(Exception):
    """Base exception for channel adapter errors"""
    pass


class MessageConversionError(ChannelAdapterError):
    """Raised when message conversion fails"""
    pass


class MessageSendError(ChannelAdapterError):
    """Raised when message sending fails"""
    pass


class WebhookValidationError(ChannelAdapterError):
    """Raised when webhook validation fails"""
    pass


class ChannelAdapter(ABC):
    """
    Base interface for all communication channel adapters.
    Provides a unified interface for different communication platforms (WhatsApp, web, etc.).
    """
    
    def __init__(self, channelType: str, config: Dict[str, Any]):
        self.channelType = channelType
        self.config = config
        self.isInitialized = False
    
    @abstractmethod
    async def initializeChannel(self) -> bool:
        """Initialize the channel adapter with necessary setup"""
        pass
    
    @abstractmethod
    def receiveMessage(self, rawMessage: Any) -> StandardMessage:
        """Convert platform-specific message to standardized format"""
        pass
    
    @abstractmethod
    async def sendMessage(self, content: str, channelId: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Send message through the specific communication platform"""
        pass
    
    @abstractmethod
    def validateWebhook(self, request: Any) -> bool:
        """Validate incoming webhook requests for security"""
        pass
    
    @abstractmethod
    def getSupportedMessageTypes(self) -> List[str]:
        """Get list of message types supported by this channel"""
        pass
    
    def getChannelInfo(self) -> Dict[str, Any]:
        """Get information about this channel adapter"""
        return {
            'channelType': self.channelType,
            'isInitialized': self.isInitialized,
            'supportedMessageTypes': self.getSupportedMessageTypes(),
            'config': {k: v for k, v in self.config.items() if not k.endswith('token') and not k.endswith('key')}
        }
    
    async def healthCheck(self) -> Dict[str, Any]:
        """Perform health check for the channel adapter"""
        return {
            'status': 'healthy' if self.isInitialized else 'not_initialized',
            'channelType': self.channelType,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def __str__(self) -> str:
        return f"{self.__class__.__name__}(channelType={self.channelType})"
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(channelType='{self.channelType}', isInitialized={self.isInitialized})"
