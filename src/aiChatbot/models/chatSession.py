"""
Chat session data model with session management capabilities
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict
import uuid


def _current_time() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


class ChatSession(BaseModel):
    """
    Represents an active chat session with comprehensive session management.
    Handles conversation state, history, and metadata for ongoing chat interactions.
    """
    sessionId: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique session identifier")
    userId: str = Field(..., min_length=1, description="User identifier")
    channelId: str = Field(..., min_length=1, description="Channel or chat identifier")
    channelType: str = Field(..., description="Channel type (whatsapp, web, api, etc.)")
    geminiSession: Optional[Any] = Field(None, description="Google GenAI SDK session object")
    createdAt: datetime = Field(default_factory=_current_time, description="Session creation timestamp")
    lastActivity: datetime = Field(default_factory=_current_time, description="Last activity timestamp")
    messageCount: int = Field(default=0, description="Number of messages in this session")
    language: str = Field(default="tr", description="Detected or preferred language")
    isActive: bool = Field(default=True, description="Whether session is currently active")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional session metadata")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator('channelType')
    @classmethod
    def validateChannelType(cls, value: str) -> str:
        """Validate channel type"""
        supportedTypes = {'whatsapp', 'web', 'api'}
        if value.lower() not in supportedTypes:
            raise ValueError(f"Channel type must be one of: {supportedTypes}")
        return value.lower()

    @field_validator('language')
    @classmethod
    def validateLanguage(cls, value: str) -> str:
        """Validate language code"""
        supportedLanguages = {'en', 'tr'}
        if value.lower() not in supportedLanguages:
            return 'tr'  # Default to Turkish for İşbir
        return value.lower()

    def updateActivity(self) -> None:
        """Update last activity timestamp and increment message count"""
        self.lastActivity = _current_time()
        self.messageCount += 1

    def isExpired(self, timeoutMinutes: int = 60) -> bool:
        """Check if session has expired based on inactivity"""
        if not self.isActive:
            return True

        timeout = timedelta(minutes=timeoutMinutes)
        now = _current_time()
        if now - self.lastActivity > timeout:
            return True

        return now - self.createdAt > timeout

    def getSessionDuration(self) -> timedelta:
        """Get total session duration"""
        return self.lastActivity - self.createdAt

    def deactivate(self) -> None:
        """Deactivate the session"""
        self.isActive = False
        self.lastActivity = _current_time()

    def addMetadata(self, key: str, value: Any) -> None:
        """Add metadata to the session"""
        self.metadata[key] = value
        self.updateActivity()

    def getMetadata(self, key: str, default: Any = None) -> Any:
        """Get metadata value by key"""
        return self.metadata.get(key, default)

    def toDict(self) -> Dict[str, Any]:
        """Convert session to dictionary format"""
        return {
            'sessionId': self.sessionId,
            'userId': self.userId,
            'channelId': self.channelId,
            'channelType': self.channelType,
            'createdAt': self.createdAt.isoformat(),
            'lastActivity': self.lastActivity.isoformat(),
            'messageCount': self.messageCount,
            'language': self.language,
            'isActive': self.isActive,
            'metadata': self.metadata
        }

    def __str__(self) -> str:
        return f"ChatSession(sessionId={self.sessionId[:8]}..., userId={self.userId}, channelType={self.channelType})"
