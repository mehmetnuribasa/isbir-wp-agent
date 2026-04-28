"""
Intent detection and echo removal utilities.
Adapted from İşbir-Whatsapp-Chatbot.
"""

import re
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=50)
def isSimpleGreeting(text: str) -> bool:
    """Check if the message is a simple greeting with nothing else."""
    text_lower = text.lower().strip()
    greetings = ["merhaba", "selam", "hello", "hi", "günaydın", "iyi günler"]
    
    return text_lower in greetings or (
        any(g in text_lower for g in greetings) and len(text_lower.split()) <= 2
    )


@lru_cache(maxsize=50)
def isPurePriceQuestion(text: str) -> bool:
    """Check if the message is purely about pricing."""
    text_lower = text.lower()
    price_words = ["fiyat", "kaç para", "ücret", "maliyeti"]
    
    has_price = any(pw in text_lower for pw in price_words)
    
    feature_words = ["özellik", "teknik", "nasıl", "hangi", "bilgi", "güç", "kva"]
    has_feature = any(fw in text_lower for fw in feature_words)
    
    return has_price and not has_feature


def isGoodbye(text: str) -> bool:
    """Detect goodbye messages."""
    goodbye_words = [
        "teşekkür", "tesekkur", "sağol", "sagol",
        "thanks", "bye", "güle güle", "hoşça kal"
    ]
    return any(gw in text.lower() for gw in goodbye_words)


def removeEchoOpening(text: str) -> str:
    """
    Remove the first sentence if it merely echoes the user's intent.
    Patterns like: 'X hakkında bilgi almak istiyorsunuz.'
    """
    echo_patterns = [
        r'^[^.!?\n]*(?:hakkında|ile ilgili)[^.!?\n]*(?:istiyorsunuz|ister misiniz|almak istiyorsunuz)[.!?]?\s*',
        r'^(?:tabii[,.]?|anladım[,.]?|elbette[,.]?)\s*[^.!?\n]*(?:hakkında|ile ilgili)[^.!?\n]*[.!?]\s*',
        r'^[^.!?\n]*(?:bilgi almak istiyorsunuz|bilgi vermekten memnuniyet)[^.!?\n]*[.!?]\s*',
    ]
    for pattern in echo_patterns:
        cleaned = re.sub(pattern, '', text, flags=re.IGNORECASE)
        if cleaned and cleaned != text:
            logger.debug("Echo opening removed")
            return cleaned.strip()
    return text


def getPriceResponse() -> str:
    """Get the standard price inquiry response."""
    return (
        "Fiyatlarımız donanım ve projeye göre değişmektedir.\n\n"
        "Detaylı teklif için:\n"
        "📞 444 09 10\n"
        "📧 isbir@isbirelektrik.com.tr\n\n"
        "Satış ekibimiz size en uygun çözümü sunacaktır."
    )


def getGoodbyeResponse() -> str:
    """Get the standard goodbye response."""
    return "Rica ederim, her zaman buradayım!"
