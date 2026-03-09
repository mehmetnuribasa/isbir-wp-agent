"""İşbir WhatsApp AI Chatbot — Clean architecture with Gemini AI."""

__version__ = "1.0.0"

# Core interfaces
from .interfaces.channelAdapter import ChannelAdapter
from .interfaces.aiService import AIService
from .interfaces.messageProcessor import MessageProcessor

# Data models
from .models.standardMessage import StandardMessage
from .models.chatSession import ChatSession
from .models.botConfig import BotConfig, ServerConfig, LoggingConfig

# Utilities
from .utils.languageDetector import LanguageDetector

__all__ = [
    "ChannelAdapter",
    "AIService",
    "MessageProcessor",
    "StandardMessage",
    "ChatSession",
    "BotConfig",
    "ServerConfig",
    "LoggingConfig",
    "LanguageDetector",
]
