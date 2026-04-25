"""
Gemini Embedding Service

Google Gemini text-embedding-004 modeli ile metin vektörleri oluşturur.
RAG pipeline'ında hem indeksleme hem de sorgu embedding'leri için kullanılır.
"""

import logging
import time
from typing import Optional

from google import genai

logger = logging.getLogger(__name__)

# Gemini embedding model
EMBEDDING_MODEL = "gemini-embedding-001"
# Embedding boyutu
EMBEDDING_DIMENSION = 768


class EmbeddingService:
    """
    Gemini text-embedding-004 modeli ile metin embedding'leri oluşturur.
    
    Bu servis hem bilgi tabanı chunk'larının indekslenmesinde
    hem de kullanıcı sorgularının vektöre dönüştürülmesinde kullanılır.
    """

    def __init__(self, client: genai.Client):
        self.client = client
        logger.info(
            f"EmbeddingService initialized",
            extra={"model": EMBEDDING_MODEL, "dimension": EMBEDDING_DIMENSION},
        )

    def embedText(self, text: str) -> list[float]:
        """
        Tek bir metni embedding vektörüne dönüştürür.

        Args:
            text: Embedding oluşturulacak metin

        Returns:
            Embedding vektörü (float listesi)
        """
        return self._embedWithRetry(text)

    def embedTexts(self, texts: list[str]) -> list[list[float]]:
        """
        Birden fazla metni tek tek embedding vektörlerine dönüştürür.
        Her istek arasında kısa bekleme yaparak rate limit'i aşmaz.
        
        Args:
            texts: Embedding oluşturulacak metinler
            
        Returns:
            Her metin için embedding vektörü listesi
        """
        if not texts:
            return []

        embeddings = []
        for i, text in enumerate(texts):
            embedding = self._embedWithRetry(text)
            embeddings.append(embedding)
            
            # Rate limit koruması: her istek arasında kısa bekleme
            if i < len(texts) - 1:
                time.sleep(0.7)  # ~85 istek/dakika — güvenli aralık

        logger.info(
            f"Batch embedding completed: {len(embeddings)} texts",
            extra={"count": len(embeddings)},
        )
        return embeddings

    def _embedWithRetry(self, text: str, maxRetries: int = 3) -> list[float]:
        """
        Tek bir metni embedding'e dönüştürür, rate limit'te otomatik retry yapar.
        """
        for attempt in range(maxRetries):
            try:
                result = self.client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=text,
                )
                return list(result.embeddings[0].values)
            except Exception as e:
                errorStr = str(e)
                if "429" in errorStr or "RESOURCE_EXHAUSTED" in errorStr:
                    waitTime = 60 * (attempt + 1)  # 60, 120, 180 sn
                    logger.warning(
                        f"Rate limit hit (attempt {attempt + 1}/{maxRetries}), "
                        f"waiting {waitTime}s..."
                    )
                    time.sleep(waitTime)
                else:
                    logger.error(f"Embedding error: {e}", exc_info=True)
                    raise
        
        raise RuntimeError(f"Embedding failed after {maxRetries} retries")
