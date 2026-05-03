"""
Service factory for building and wiring core services.
Milestone 6: PostgreSQL DatabaseManager entegrasyonu eklendi.
"""

import logging
from pathlib import Path
from typing import Tuple, Optional

from google import genai

from ..models.botConfig import BotConfig
from ..utils.promptManager import PromptManager, getPromptManager
from ..database.connection import DatabaseManager, init_database
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

    Milestone 6 değişiklikleri:
        - PostgreSQL DatabaseManager oluşturulur ve başlatılır
        - SessionManager'a dbManager enjekte edilir

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
    # ── PostgreSQL Bağlantısı (Milestone 6) ───────────────────────────────────
    dbManager: Optional[DatabaseManager] = None

    if config.databaseUrl:
        try:
            dbManager = DatabaseManager()
            await dbManager.init(config.databaseUrl, echo=config.databaseEcho)
            await dbManager.create_tables()
            logger.info("PostgreSQL connected and tables verified ✓")
        except Exception as e:
            logger.error(
                f"PostgreSQL connection failed — falling back to RAM-only mode: {e}",
                exc_info=True,
            )
            dbManager = None
    else:
        logger.warning("DATABASE_URL not set — running in RAM-only session mode (no persistence)")

    # ── Load prompts ───────────────────────────────────────────────────────────
    promptManager = getPromptManager()

    # ── Create Gemini client (AI Studio) ───────────────────────────────────────
    client = genai.Client(api_key=config.geminiApiKey)
    logger.info("Gemini AI Studio client created")

    # ── RAG veya Keyword KB seçimi ─────────────────────────────────────────────
    ragService: Optional[RAGService] = None
    knowledgeBase: Optional[LightweightKnowledgeBase] = None

    kbPath = _resolveDataPath(config.knowledgeBasePath)

    if config.ragEnabled:
        logger.info("RAG mode enabled — initializing embedding and vector DB")

        embeddingService = EmbeddingService(client=client)

        chromaDbPath = _resolveDataPath(config.chromaDbPath)
        ragService = RAGService(
            embeddingService=embeddingService,
            chromaDbPath=chromaDbPath,
        )

        if Path(kbPath).exists():
            indexedCount = ragService.indexKnowledgeBase(kbPath)
            logger.info(f"RAG indexed {indexedCount} chunks from {kbPath}")
        else:
            logger.warning(f"Knowledge base not found for RAG: {kbPath}")
    else:
        logger.info("RAG disabled — using keyword-based knowledge base")

        if Path(kbPath).exists():
            knowledgeBase = LightweightKnowledgeBase(kbPath)
            logger.info(f"Knowledge base loaded from {kbPath}")
        else:
            logger.warning(f"Knowledge base file not found: {kbPath}")

    # ── Build system instruction ────────────────────────────────────────────────
    systemInstruction = promptManager.getSystemInstruction()

    # ── Create session manager (with optional PostgreSQL) ──────────────────────
    sessionManager = SessionManager(
        client=client,
        modelName="gemini-2.5-flash",
        systemInstruction=systemInstruction,
        sessionTimeoutMinutes=1440,  # 24 saat — endüstriyel destek gün boyu sürebilir
        dbManager=dbManager,  # Milestone 6: PostgreSQL bağlantısı
    )

    # Start session cleanup
    await sessionManager.startCleanup()

    # ── Create AI service ──────────────────────────────────────────────────────
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
            "postgresEnabled": dbManager is not None,
        },
    )

    return aiService, ragService
