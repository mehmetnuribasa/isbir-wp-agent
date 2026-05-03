"""
Response cleanup utilities.
Simplified: Intent shortcuts removed — all messages go through Gemini AI.
Only echo removal is kept to clean up Gemini's occasional parroting behavior.
"""

import re
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=50)
def isSimpleGreeting(text: str) -> bool:
    """Sadece selamlama olup olmadığını kontrol eder (WhatsApp menüsü için)."""
    text_lower = text.lower().strip()
    greetings = ["merhaba", "selam", "hello", "hi", "günaydın", "iyi günler", "iyi akşamlar", "good morning", "good evening", "good night", "good day", "good afternoon"]
    
    return text_lower in greetings or (
        any(g in text_lower for g in greetings) and len(text_lower.split()) <= 2
    )
