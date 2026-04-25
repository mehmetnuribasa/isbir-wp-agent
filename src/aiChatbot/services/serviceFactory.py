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
from .embeddingService import EmbeddingService
from .ragService import RAGService

logger = logging.getLogger(__name__)


def _resolveDataPath(relativePath: str) -> str:
    """Relative path'i proje kökünden çözümler."""
    if Path(relativePath).is_absolute():
        return relativePath
    projectRoot = Path(__file__).parent.parent.parent.parent
    return str(projectRoot / relativePath)


async def buildGeminiService(
    config: BotConfig,
) -> Tuple[GeminiAIService, Optional[RAGService]]:
    """
    Build and configure the Gemini AI service with all dependencies.
    
    RAG modu etkinse (varsayılan):
        - EmbeddingService + RAGService oluşturulur
        - Knowledge base ChromaDB'ye indekslenir
        - GeminiAIService RAG servisiyle çalışır
    
    RAG modu devre dışıysa:
        - Eski LightweightKnowledgeBase kullanılır (keyword arama)
    
    Args:
        config: Bot configuration
        
    Returns:
        Tuple of (GeminiAIService, RAGService or None)
    """
    # Load prompts
    promptManager = getPromptManager()
    
    # Create Gemini client (AI Studio)
    client = genai.Client(api_key=config.geminiApiKey)
    logger.info("Gemini AI Studio client created")
    
    # ── RAG veya Keyword KB seçimi ──
    ragService: Optional[RAGService] = None
    knowledgeBase: Optional[LightweightKnowledgeBase] = None
    
    kbPath = _resolveDataPath(config.knowledgeBasePath)
    
    if config.ragEnabled:
        # RAG modunu kullan
        logger.info("RAG mode enabled — initializing embedding and vector DB")
        
        embeddingService = EmbeddingService(client=client)
        
        chromaDbPath = _resolveDataPath(config.chromaDbPath)
        ragService = RAGService(
            embeddingService=embeddingService,
            chromaDbPath=chromaDbPath,
        )
        
        # Knowledge base'i indeksle (ilk çalıştırmada)
        if Path(kbPath).exists():
            indexedCount = ragService.indexKnowledgeBase(kbPath)
            logger.info(f"RAG indexed {indexedCount} chunks from {kbPath}")
        else:
            logger.warning(f"Knowledge base not found for RAG: {kbPath}")
    else:
        # Eski keyword arama modunu kullan (fallback)
        logger.info("RAG disabled — using keyword-based knowledge base")
        
        if Path(kbPath).exists():
            knowledgeBase = LightweightKnowledgeBase(kbPath)
            logger.info(f"Knowledge base loaded from {kbPath}")
        else:
            logger.warning(f"Knowledge base file not found: {kbPath}")
    
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
        ragService=ragService,
        promptManager=promptManager,
    )
    
    logger.info(
        "GeminiAIService built and configured",
        extra={
            "ragEnabled": config.ragEnabled,
            "hasRAG": ragService is not None,
            "hasKeywordKB": knowledgeBase is not None,
        },
    )
    
    return aiService, ragService
