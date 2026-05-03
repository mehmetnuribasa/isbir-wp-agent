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

    RAG (Zorunlu):
        - EmbeddingService + RAGService oluşturulur
        - Knowledge base ChromaDB'ye indekslenir
        - GeminiAIService sadece RAG servisiyle çalışır

    Args:
        config: Bot configuration

    Returns:
        Tuple of (GeminiAIService, RAGService or None)
    """
    # ── PostgreSQL Bağlantısı  ───────────────────────────────────
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

    # ── RAG Servisinin Başlatılması ─────────────────────────────────
    ragService: Optional[RAGService] = None
    kbPath = _resolveDataPath(config.knowledgeBasePath)

    logger.info("Initializing RAG (semantic search) mode with embedding and vector DB")

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

    # ── LLM Araçları (Tools) Tanımlama ──────────────────────────────────────────
    def search_isbir_knowledge_base(query: str) -> str:
        """İşbir Elektrik jeneratörleri, özellikleri, fiyatları, hizmetleri ve iletişim bilgileri hakkında veritabanında arama yapar.

        Args:
            query: Aranacak teknik konu veya soru (örn: '100 kVA jeneratör yakıt tüketimi', 'iletişim numarası', 'marin jeneratör nedir')
        """
        logger.info(f"GenAI Tool called: search_isbir_knowledge_base(query='{query}')")
        context = ragService.findRelevantContent(query)
        if context:
            return f"Arama Sonuçları:\n{context}"
        return "Veritabanında bu konuya ait bir bilgi bulunamadı."

    llm_tools = [search_isbir_knowledge_base] if ragService else None

    # ── Build system instruction ────────────────────────────────────────────────
    systemInstruction = promptManager.getSystemInstruction()

    # ── Create session manager (with optional PostgreSQL) ──────────────────────
    sessionManager = SessionManager(
        client=client,
        modelName="gemini-2.5-flash",
        systemInstruction=systemInstruction,
        sessionTimeoutMinutes=1440,  # 24 saat — endüstriyel destek gün boyu sürebilir
        dbManager=dbManager,  # PostgreSQL bağlantısı
        tools=llm_tools,      # Agentic RAG Araçları
    )

    # Start session cleanup
    await sessionManager.startCleanup()

    aiService = GeminiAIService(
        config=config,
        sessionManager=sessionManager,
        ragService=ragService,
        promptManager=promptManager,
    )

    logger.info(
        "GeminiAIService built and configured",
        extra={
            "hasRAG": ragService is not None,
            "postgresEnabled": dbManager is not None,
        },
    )

    return aiService, ragService
