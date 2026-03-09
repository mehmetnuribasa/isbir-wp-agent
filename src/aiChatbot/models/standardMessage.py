"""
Unified message format across all channels with validation
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
import uuid


class StandardMessage(BaseModel):
    """Unified message format across all channels with validation"""
    userId: str = Field(..., min_length=1, description="Unique identifier for the user")
    channelId: str = Field(..., min_length=1, description="Channel or chat identifier")
    content: str = Field(..., min_length=1, description="Message content")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Message timestamp")
    messageId: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique message identifier")
    channelType: str = Field(..., description="Channel type (whatsapp, web, api, etc.)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator('channelType')
    @classmethod
    def validateChannelType(cls, value: str) -> str:
        """Validate channel type is one of supported types"""
        supportedTypes = {'whatsapp', 'web', 'api'}
        if value.lower() not in supportedTypes:
            raise ValueError(f"Channel type must be one of: {supportedTypes}")
        return value.lower()

    @field_validator('content')
    @classmethod
    def validateContent(cls, value: str) -> str:
        """Validate and clean message content"""
        if not value or not value.strip():
            raise ValueError("Message content cannot be empty")
        return value.strip()

    def toDict(self) -> Dict[str, Any]:
        """Convert message to dictionary format"""
        return {
            'userId': self.userId,
            'channelId': self.channelId,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'messageId': self.messageId,
            'channelType': self.channelType,
            'metadata': self.metadata
        }

    @classmethod
    def fromDict(cls, data: Dict[str, Any]) -> 'StandardMessage':
        """Create StandardMessage from dictionary"""
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
        return cls(**data)

    def createReply(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> 'StandardMessage':
        """Create a reply message to this message"""
        replyMetadata = self.metadata.copy()
        if metadata:
            replyMetadata.update(metadata)
        replyMetadata['replyTo'] = self.messageId
        
        return StandardMessage(
            userId='bot',
            channelId=self.channelId,
            content=content,
            channelType=self.channelType,
            metadata=replyMetadata
        )
