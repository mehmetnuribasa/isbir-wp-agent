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
        results = self._embedBatchWithRetry([text])
        return results[0]

    def embedTexts(self, texts: list[str]) -> list[list[float]]:
        """
        Birden fazla metni TEK BİR API İSTEĞİ ile embedding vektörlerine dönüştürür.
        Günlük 1500 istek limitinden 20 kat tasarruf sağlar.
        """
        if not texts:
            return []

        # Listeyi tek seferde gönder
        return self._embedBatchWithRetry(texts)

    def _embedBatchWithRetry(self, texts: list[str], maxRetries: int = 4) -> list[list[float]]:
        """
        Bir metin listesini tek seferde gönderir ve hata durumunda bekleyip tekrar dener.
        """
        for attempt in range(maxRetries):
            try:
                result = self.client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=texts,
                )
                
                embeddings = [list(e.values) for e in result.embeddings]
                
                logger.info(
                    f"Batch embedding successful: {len(embeddings)} texts in 1 API call",
                    extra={"count": len(embeddings)},
                )
                return embeddings
                
            except Exception as e:
                errorStr = str(e)
                if any(x in errorStr for x in ["429", "RESOURCE_EXHAUSTED", "503", "500"]):
                    waitTime = 60 * (attempt + 1)  # 60, 120, 180, 240 sn
                    logger.warning(
                        f"Rate limit or API error (attempt {attempt + 1}/{maxRetries}), "
                        f"waiting {waitTime}s before retry..."
                    )
                    time.sleep(waitTime)
                else:
                    logger.error(f"Embedding batch error: {e}", exc_info=True)
                    raise
        
        raise RuntimeError(f"Batch embedding failed after {maxRetries} retries")
