"""Minimal language detection helper for English and Turkish text."""

from __future__ import annotations
from typing import Dict, List


class LanguageDetector:
    """Very small language detector focused on English and Turkish."""

    def __init__(self) -> None:
        self.supportedLanguages: List[str] = ["en", "tr"]
        self._turkish_characters = set("çğıöşüÇĞİÖŞÜ")

    def detectLanguage(self, text: str) -> str:
        """Detect the language of the provided text."""
        if not text or len(text.strip()) < 3:
            return "tr"  # Default to Turkish for İşbir

        if any(char in self._turkish_characters for char in text):
            return "tr"

        lowered = text.lower()
        turkish_keywords = {"merhaba", "bilgi", "ürün", "teşekkür", "nasıl", "lütfen", "selam", "günaydın"}
        if any(word in lowered for word in turkish_keywords):
            return "tr"

        return "en"

    def detectLanguageWithConfidence(self, text: str) -> Dict[str, float]:
        """Return a simple confidence distribution."""
        lang = self.detectLanguage(text)
        return {lang: 0.9, ("tr" if lang == "en" else "en"): 0.1}

    def isSupportedLanguage(self, languageCode: str) -> bool:
        return languageCode.lower() in self.supportedLanguages

    def getSupportedLanguages(self) -> List[str]:
        return list(self.supportedLanguages)

    def getLanguageName(self, languageCode: str) -> str:
        names = {"en": "English", "tr": "Turkish"}
        return names.get(languageCode.lower(), languageCode)
