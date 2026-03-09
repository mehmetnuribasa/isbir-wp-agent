"""
Service factory for building and wiring core services.
"""

import logging
from pathlib import Path
from typing import Tuple, Optional

from google import genai

from ..models.botConfig import BotConfig
from ..utils.promptManager import PromptManager, getPromptManager
from .geminiAIService import GeminiAIService
from .sessionManager import SessionManager
from .knowledgeBase import LightweightKnowledgeBase

logger = logging.getLogger(__name__)


async def buildGeminiService(
    config: BotConfig,
) -> Tuple[GeminiAIService, Optional[LightweightKnowledgeBase]]:
    """
    Build and configure the Gemini AI service with all dependencies.
    
    Args:
        config: Bot configuration
        
    Returns:
        Tuple of (GeminiAIService, LightweightKnowledgeBase or None)
    """
    # Load knowledge base
    knowledgeBase: Optional[LightweightKnowledgeBase] = None
    kbPath = config.knowledgeBasePath
    
    if kbPath:
        # Resolve relative paths
        if not Path(kbPath).is_absolute():
            projectRoot = Path(__file__).parent.parent.parent.parent
            kbPath = str(projectRoot / kbPath)
        
        if Path(kbPath).exists():
            knowledgeBase = LightweightKnowledgeBase(kbPath)
            logger.info(f"Knowledge base loaded from {kbPath}")
        else:
            logger.warning(f"Knowledge base file not found: {kbPath}")
    
    # Load prompts
    promptManager = getPromptManager()
    
    # Create Gemini client (AI Studio)
    client = genai.Client(api_key=config.geminiApiKey)
    logger.info("Gemini AI Studio client created")
    
    # Build system instruction
    systemInstruction = promptManager.getSystemInstruction()
    
    # Create session manager
    sessionManager = SessionManager(
        client=client,
        modelName="gemini-2.5-flash",
        systemInstruction=systemInstruction,
        sessionTimeoutMinutes=60,
    )
    
    # Start session cleanup
    await sessionManager.startCleanup()
    
    # Create AI service
    aiService = GeminiAIService(
        config=config,
        sessionManager=sessionManager,
        knowledgeBase=knowledgeBase,
        promptManager=promptManager,
    )
    
    logger.info("GeminiAIService built and configured")
    
    return aiService, knowledgeBase
