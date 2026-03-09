"""
Lightweight Knowledge Base Service (Non-RAG)
Simple, deterministic knowledge injection without embeddings or vector databases.
Adapted from İşbir-Whatsapp-Chatbot into clean architecture.
"""

import logging
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeSection:
    """Represents a section in the knowledge base"""
    title: str
    keywords: List[str]
    content: str


class LightweightKnowledgeBase:
    """
    Simple knowledge base using keyword matching.
    No embeddings, no vector DB — just fast keyword search.
    """
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.sections: List[KnowledgeSection] = []
        self.raw_content: str = ""
        
        if Path(filepath).exists():
            self._loadKnowledgeBase()
            logger.info(
                f"Knowledge base loaded: {len(self.sections)} sections",
                extra={"filepath": filepath, "sectionCount": len(self.sections)}
            )
        else:
            logger.warning(f"Knowledge base file not found: {filepath}")
    
    def _loadKnowledgeBase(self) -> None:
        """Load and parse knowledge base file"""
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                self.raw_content = f.read()
            
            current_section = None
            current_content: List[str] = []
            
            for line in self.raw_content.split('\n'):
                line = line.strip()
                
                if line.startswith('###'):
                    if current_section:
                        self.sections.append(KnowledgeSection(
                            title=current_section,
                            keywords=self._extractKeywords(current_section),
                            content='\n'.join(current_content).strip()
                        ))
                    
                    current_section = line.replace('###', '').strip()
                    current_content = []
                elif line and current_section:
                    current_content.append(line)
            
            # Save last section
            if current_section:
                self.sections.append(KnowledgeSection(
                    title=current_section,
                    keywords=self._extractKeywords(current_section),
                    content='\n'.join(current_content).strip()
                ))
            
        except Exception as e:
            logger.error(f"Error loading knowledge base: {e}", exc_info=True)
            raise
    
    def _extractKeywords(self, text: str) -> List[str]:
        """Extract keywords from text for matching"""
        words = text.lower().split()
        stop_words = {'ve', 'veya', 'ile', 'için', 'bu', 'bir', 'the', 'and', 'or', 'for', 'with'}
        return [w for w in words if w not in stop_words and len(w) > 2]
    
    def findRelevantContent(self, query: str, maxSections: int = 3) -> Optional[str]:
        """
        Find relevant content based on keyword matching.
        
        Args:
            query: User query
            maxSections: Maximum number of sections to return
            
        Returns:
            Relevant content or None if nothing found
        """
        if not self.sections:
            return None
        
        query_lower = query.lower()
        query_keywords = self._extractKeywords(query)
        
        section_scores = []
        for section in self.sections:
            score = 0
            
            # Exact title match
            if section.title.lower() in query_lower:
                score += 10
            
            # Keyword matches
            for keyword in section.keywords:
                if keyword in query_lower:
                    score += 2
            
            # Query keyword matches
            for query_kw in query_keywords:
                if query_kw in section.title.lower():
                    score += 3
                if query_kw in section.content.lower():
                    score += 1
            
            if score > 0:
                section_scores.append((section, score))
        
        section_scores.sort(key=lambda x: x[1], reverse=True)
        
        if not section_scores:
            return None
        
        top_sections = section_scores[:maxSections]
        content_parts = []
        for section, score in top_sections:
            content_parts.append(f"**{section.title}**\n{section.content}")
            logger.debug(f"Matched section: {section.title} (score={score})")
        
        result = "\n\n".join(content_parts)
        logger.info(f"Found {len(top_sections)} relevant sections for query")
        return result
    
    def getAllContent(self) -> str:
        """Get all knowledge base content"""
        return self.raw_content
    
    def reload(self) -> None:
        """Reload knowledge base from file"""
        self.sections = []
        self.raw_content = ""
        self._loadKnowledgeBase()
        logger.info("Knowledge base reloaded")
