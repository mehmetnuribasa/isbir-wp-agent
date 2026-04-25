"""
RAG (Retrieval Augmented Generation) Service

Knowledge base dosyasını chunk'lara ayırır, ChromaDB'de vektör olarak indeksler
ve kullanıcı sorgularına en alakalı bağlamı semantik arama ile bulur.
"""

import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from .embeddingService import EmbeddingService

logger = logging.getLogger(__name__)

# ─── Sabitler ──────────────────────────────────────────────────────────────────
COLLECTION_NAME = "isbir_knowledge"
CHUNK_SIZE = 500         # Karakter — her chunk'ın maksimum uzunluğu
CHUNK_OVERLAP = 100      # Karakter — ardışık chunk'lar arasındaki örtüşme
TOP_K_RESULTS = 5        # Sorgu başına döndürülecek en alakalı chunk sayısı
MIN_CHUNK_LENGTH = 30    # Çok kısa chunk'ları atla
BATCH_SIZE = 20          # Embedding batch boyutu (API rate limit için küçük tutuldu)
BATCH_DELAY = 4.0        # Saniye — batch'ler arası bekleme (rate limit: 100 req/min)


class RAGService:
    """
    RAG pipeline servisi.
    
    Akış:
    1. Knowledge base dosyasını oku
    2. Section'lara ayır (### başlıkları)
    3. Her section'ı chunk'lara böl (CHUNK_SIZE karakter)
    4. Chunk'ları Gemini Embedding ile vektörleştir
    5. ChromaDB'de sakla
    6. Sorgu geldiğinde → embedding → similarity search → bağlam döndür
    """

    def __init__(
        self,
        embeddingService: EmbeddingService,
        chromaDbPath: str = "data/chroma_db",
        collectionName: str = COLLECTION_NAME,
    ):
        self.embeddingService = embeddingService
        self.collectionName = collectionName
        self._isIndexed = False

        # ChromaDB persistent client
        dbPath = Path(chromaDbPath)
        dbPath.mkdir(parents=True, exist_ok=True)

        self.chromaClient = chromadb.PersistentClient(
            path=str(dbPath),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # Collection oluştur veya var olanı al
        self.collection = self.chromaClient.get_or_create_collection(
            name=self.collectionName,
            metadata={"hnsw:space": "cosine"},  # Kosinüs benzerliği
        )

        existingCount = self.collection.count()
        if existingCount > 0:
            self._isIndexed = True
            logger.info(
                f"RAG collection loaded: {existingCount} chunks",
                extra={"collection": self.collectionName, "chunkCount": existingCount},
            )
        else:
            logger.info("RAG collection empty — indexing needed")

    @property
    def isIndexed(self) -> bool:
        """Vektör indeksinin dolu olup olmadığını kontrol eder."""
        return self._isIndexed

    # ─── İndeksleme ────────────────────────────────────────────────────────────

    def indexKnowledgeBase(self, filepath: str, forceReindex: bool = False) -> int:
        """
        Knowledge base dosyasını parse edip ChromaDB'ye indeksler.

        Args:
            filepath: knowledge-base.txt dosya yolu
            forceReindex: True ise mevcut indeksi silip baştan oluşturur

        Returns:
            İndekslenen chunk sayısı
        """
        if not Path(filepath).exists():
            logger.error(f"Knowledge base file not found: {filepath}")
            return 0

        # 1) Dosyayı oku
        with open(filepath, "r", encoding="utf-8") as f:
            rawContent = f.read()

        # 2) Content hash kontrolü — değişti mi?
        contentHash = hashlib.md5(rawContent.encode()).hexdigest()
        
        # Koleksiyon metadatasından eski hash'i kontrol et
        collectionMeta = self.collection.metadata or {}
        oldHash = collectionMeta.get("content_hash")

        if self._isIndexed and not forceReindex:
            if oldHash == contentHash:
                logger.info("Knowledge base unchanged, skipping re-index")
                return self.collection.count()
            else:
                logger.info("Knowledge base file changed! Starting auto-reindex...")
                forceReindex = True

        # Force reindex — mevcut collection'ı sil
        if forceReindex and self._isIndexed:
            logger.info("Clearing existing collection for re-index")
            self.chromaClient.delete_collection(self.collectionName)
            self.collection = self.chromaClient.get_or_create_collection(
                name=self.collectionName,
                metadata={"hnsw:space": "cosine"},
            )
            self._isIndexed = False

        # 3) Section'lara ayır
        sections = self._parseSections(rawContent)
        logger.info(f"Parsed {len(sections)} sections from knowledge base")

        # 4) Chunk'lara böl
        chunks = []
        for title, content in sections:
            sectionChunks = self._chunkText(content, title)
            chunks.extend(sectionChunks)

        logger.info(f"Created {len(chunks)} chunks for indexing")

        if not chunks:
            logger.warning("No chunks created — nothing to index")
            return 0

        # 5) Batch halinde embedding oluştur ve ChromaDB'ye ekle
        totalIndexed = 0
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i : i + BATCH_SIZE]
            batchTexts = [c["text"] for c in batch]
            batchIds = [c["id"] for c in batch]
            batchMeta = [c["metadata"] for c in batch]

            try:
                embeddings = self.embeddingService.embedTexts(batchTexts)

                self.collection.add(
                    ids=batchIds,
                    embeddings=embeddings,
                    documents=batchTexts,
                    metadatas=batchMeta,
                )

                totalIndexed += len(batch)
                logger.info(
                    f"Indexed batch {i // BATCH_SIZE + 1}: "
                    f"{totalIndexed}/{len(chunks)} chunks"
                )

                # Rate limit bekleme
                if i + BATCH_SIZE < len(chunks):
                    time.sleep(BATCH_DELAY)

            except Exception as e:
                logger.error(f"Indexing batch error: {e}", exc_info=True)
                # Rate limit hatasıysa ekstra bekle
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    logger.info("Rate limit hit — waiting 60s before retry...")
                    time.sleep(60)
                    # Tekrar dene
                    try:
                        embeddings = self.embeddingService.embedTexts(batchTexts)
                        self.collection.add(
                            ids=batchIds,
                            embeddings=embeddings,
                            documents=batchTexts,
                            metadatas=batchMeta,
                        )
                        totalIndexed += len(batch)
                        logger.info(f"Retry successful: {totalIndexed}/{len(chunks)}")
                    except Exception as retryErr:
                        logger.error(f"Retry also failed: {retryErr}")
                continue

        # 6) Hash değerini collection metadatasına kaydet
        self.collection.modify(metadata={"hnsw:space": "cosine", "content_hash": contentHash})
        
        self._isIndexed = True
        logger.info(
            f"✅ Knowledge base indexing complete: {totalIndexed} chunks",
            extra={
                "totalChunks": totalIndexed,
                "totalSections": len(sections),
                "contentHash": contentHash,
            },
        )

        return totalIndexed

    # ─── Sorgu ─────────────────────────────────────────────────────────────────

    def findRelevantContent(
        self, query: str, topK: int = TOP_K_RESULTS
    ) -> Optional[str]:
        """
        Kullanıcı sorgusuna en alakalı bilgi tabanı bağlamını döndürür.
        
        Args:
            query: Kullanıcı sorusu
            topK: Döndürülecek maksimum chunk sayısı
            
        Returns:
            Birleştirilmiş alakalı bağlam metni veya None
        """
        if not self._isIndexed:
            logger.warning("RAG index empty — cannot search")
            return None

        try:
            # Sorgu embedding'i oluştur
            queryEmbedding = self.embeddingService.embedText(query)

            # ChromaDB'de similarity search
            results = self.collection.query(
                query_embeddings=[queryEmbedding],
                n_results=topK,
                include=["documents", "metadatas", "distances"],
            )

            if not results or not results["documents"] or not results["documents"][0]:
                return None

            # Sonuçları formatla
            contextParts = []
            for doc, meta, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                sectionTitle = meta.get("section", "Genel")
                # Kosinüs mesafesi: 0 = en yakın, 2 = en uzak
                similarity = 1 - distance  # Benzerlik skoru
                
                # Çok düşük benzerlikli sonuçları filtrele
                if similarity < 0.3:
                    continue

                contextParts.append(f"**{sectionTitle}**\n{doc}")

                logger.debug(
                    f"RAG result: {sectionTitle} (similarity={similarity:.3f})"
                )

            if not contextParts:
                return None

            result = "\n\n".join(contextParts)
            logger.info(
                f"RAG found {len(contextParts)} relevant chunks",
                extra={
                    "queryLength": len(query),
                    "resultCount": len(contextParts),
                },
            )

            return result

        except Exception as e:
            logger.error(f"RAG query error: {e}", exc_info=True)
            return None

    # ─── Dahili Yardımcı Metodlar ──────────────────────────────────────────────

    def _parseSections(self, rawContent: str) -> list[tuple[str, str]]:
        """
        Knowledge base dosyasını ### başlıklarına göre section'lara ayırır.

        Returns:
            (başlık, içerik) tuple'ları listesi
        """
        sections: list[tuple[str, str]] = []
        currentTitle: Optional[str] = None
        currentLines: list[str] = []

        for line in rawContent.split("\n"):
            stripped = line.strip()

            if stripped.startswith("###"):
                # Önceki section'ı kaydet
                if currentTitle and currentLines:
                    content = "\n".join(currentLines).strip()
                    if len(content) >= MIN_CHUNK_LENGTH:
                        sections.append((currentTitle, content))

                currentTitle = stripped.replace("###", "").strip()
                currentLines = []
            elif stripped and currentTitle:
                currentLines.append(stripped)

        # Son section
        if currentTitle and currentLines:
            content = "\n".join(currentLines).strip()
            if len(content) >= MIN_CHUNK_LENGTH:
                sections.append((currentTitle, content))

        return sections

    def _chunkText(
        self, text: str, sectionTitle: str
    ) -> list[dict]:
        """
        Metni belirli boyutta, örtüşen chunk'lara böler.

        Args:
            text: Bölünecek metin
            sectionTitle: Section başlığı (metadata için)

        Returns:
            Chunk dict'leri listesi (id, text, metadata)
        """
        chunks = []

        # Kısa metinler — tek chunk
        if len(text) <= CHUNK_SIZE:
            chunkId = self._generateChunkId(sectionTitle, 0)
            chunks.append({
                "id": chunkId,
                "text": f"{sectionTitle}: {text}",
                "metadata": {
                    "section": sectionTitle,
                    "chunkIndex": 0,
                    "totalChunks": 1,
                },
            })
            return chunks

        # Uzun metinler — örtüşen parçalara böl
        # Cümle sınırlarında bölmeye çalış
        sentences = re.split(r"(?<=[.!?\n])\s+", text)
        
        currentChunk: list[str] = []
        currentLength = 0
        chunkIndex = 0

        for sentence in sentences:
            sentenceLen = len(sentence)

            if currentLength + sentenceLen > CHUNK_SIZE and currentChunk:
                # Mevcut chunk'ı kaydet
                chunkText = " ".join(currentChunk)
                chunkId = self._generateChunkId(sectionTitle, chunkIndex)

                chunks.append({
                    "id": chunkId,
                    "text": f"{sectionTitle}: {chunkText}",
                    "metadata": {
                        "section": sectionTitle,
                        "chunkIndex": chunkIndex,
                    },
                })
                chunkIndex += 1

                # Overlap: son birkaç cümleyi tut
                overlapChars = 0
                overlapSentences: list[str] = []
                for s in reversed(currentChunk):
                    overlapChars += len(s)
                    overlapSentences.insert(0, s)
                    if overlapChars >= CHUNK_OVERLAP:
                        break

                currentChunk = overlapSentences
                currentLength = sum(len(s) for s in currentChunk)

            currentChunk.append(sentence)
            currentLength += sentenceLen

        # Son kalan chunk
        if currentChunk:
            chunkText = " ".join(currentChunk)
            if len(chunkText) >= MIN_CHUNK_LENGTH:
                chunkId = self._generateChunkId(sectionTitle, chunkIndex)
                chunks.append({
                    "id": chunkId,
                    "text": f"{sectionTitle}: {chunkText}",
                    "metadata": {
                        "section": sectionTitle,
                        "chunkIndex": chunkIndex,
                    },
                })

        # totalChunks metadata'sını güncelle
        totalChunks = len(chunks)
        for chunk in chunks:
            chunk["metadata"]["totalChunks"] = totalChunks

        return chunks

    @staticmethod
    def _generateChunkId(sectionTitle: str, chunkIndex: int) -> str:
        """Section başlığı ve chunk index'inden benzersiz ID üretir."""
        raw = f"{sectionTitle}:{chunkIndex}"
        return hashlib.md5(raw.encode()).hexdigest()

    def getStats(self) -> dict:
        """RAG indeks istatistiklerini döndürür."""
        return {
            "isIndexed": self._isIndexed,
            "totalChunks": self.collection.count() if self._isIndexed else 0,
            "collectionName": self.collectionName,
        }
