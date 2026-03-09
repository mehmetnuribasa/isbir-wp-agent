"""
Embedding service interface for generating text embeddings (future RAG support)
"""

from abc import ABC, abstractmethod
import numpy as np


class EmbeddingService(ABC):
    """Abstract interface for embedding services"""
    
    @abstractmethod
    async def embedDocuments(self, texts: list[str]) -> np.ndarray:
        """Embed documents for indexing"""
        pass
    
    @abstractmethod
    async def embedQuery(self, query: str) -> np.ndarray:
        """Embed query for search"""
        pass
    
    @abstractmethod
    def getDimensions(self) -> int:
        """Get the dimensionality of embeddings"""
        pass
