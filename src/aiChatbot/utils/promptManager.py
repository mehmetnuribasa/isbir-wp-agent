"""
Prompt management utility for loading and formatting system prompts
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class PromptManager:
    """
    Manages system prompts and language-specific instructions from prompts.json
    """
    
    def __init__(self, promptsPath: Optional[str] = None):
        if promptsPath is None:
            projectRoot = Path(__file__).parent.parent.parent.parent
            promptsPath = str(projectRoot / "data" / "prompts.json")
        
        self.promptsPath = Path(promptsPath)
        self._prompts: Optional[Dict[str, Any]] = None
        self._systemInstruction: Optional[str] = None
        self._loadPrompts()
    
    def _loadPrompts(self) -> None:
        """Load prompts from JSON file"""
        try:
            if not self.promptsPath.exists():
                logger.warning(f"Prompts file not found: {self.promptsPath}, using defaults")
                self._prompts = self._getDefaultPrompts()
                return
            
            with open(self.promptsPath, "r", encoding="utf-8") as f:
                self._prompts = json.load(f)
            
            logger.info(f"Loaded prompts from {self.promptsPath}")
        except Exception as e:
            logger.error(f"Error loading prompts from {self.promptsPath}: {e}", exc_info=True)
            self._prompts = self._getDefaultPrompts()
    
    def _getDefaultPrompts(self) -> Dict[str, Any]:
        """Get default prompts if file is not available"""
        return {
            "system_instruction": {
                "role": "Sen İşbir Elektrik'in müşteri temsilcisisin.",
                "responsibilities": ["Doğru bilgi ver", "Müşterilere yardımcı ol"],
                "communication_guidelines": {},
                "closing": "Profesyonel ve yardımsever ol."
            },
            "language_instructions": {
                "tr": "Türkçe olarak net ve samimi yanıtlar ver.",
                "en": "Respond in clear, friendly English."
            },
            "error_messages": {
                "tr": "Üzgünüm, bir sorun oluştu. Lütfen tekrar deneyin.",
                "en": "Sorry, something went wrong. Please try again."
            }
        }
    
    def _ensurePromptsLoaded(self) -> Dict[str, Any]:
        if self._prompts is None:
            self._loadPrompts()
        if self._prompts is None:
            raise RuntimeError("Failed to load prompts")
        return self._prompts
    
    def getSystemInstruction(self) -> str:
        """Build formatted system instruction from prompts configuration"""
        if self._systemInstruction is not None:
            return self._systemInstruction
        
        prompts = self._ensurePromptsLoaded()
        sysInst = prompts.get("system_instruction", {})
        
        sections = []
        
        if "role" in sysInst:
            sections.append(sysInst["role"])
        
        if "company_overview" in sysInst:
            sections.append(f"\n# ŞİRKET BİLGİLERİ\n{sysInst['company_overview']}")
        
        if "responsibilities" in sysInst:
            sections.append("\n# GÖREV")
            for resp in sysInst["responsibilities"]:
                sections.append(f"- {resp}")
        
        if "communication_guidelines" in sysInst:
            sections.append("\n# İLETİŞİM KURALLARI")
            guidelines = sysInst["communication_guidelines"]
            idx = 1
            for key, value in guidelines.items():
                sections.append(f"{idx}. **{key.replace('_', ' ').title()}**: {value}")
                idx += 1
        
        if "knowledge_base_usage" in sysInst:
            sections.append("\n# BİLGİ TABANI KULLANIMI")
            for item in sysInst["knowledge_base_usage"]:
                sections.append(f"- {item}")
        
        if "prohibited_actions" in sysInst:
            sections.append("\n# YAPILMAMASI GEREKENLER")
            for item in sysInst["prohibited_actions"]:
                sections.append(f"- {item}")
        
        if "examples" in sysInst:
            sections.append("\n# ÖRNEKLER")
            for example in sysInst["examples"]:
                sections.append(example)
        
        if "escalation" in sysInst:
            sections.append("\n# ESKALEyon\nCevaplandıramadığın sorular için:")
            escalation = sysInst["escalation"]
            for key, value in escalation.items():
                label = key.replace("_", " ").title()
                sections.append(f"- {label} → \"{value}\"")
        
        if "response_format" in sysInst:
            sections.append("\n# YANIT FORMATI")
            for item in sysInst["response_format"]:
                sections.append(f"- {item}")
        
        if "closing" in sysInst:
            sections.append(f"\n{sysInst['closing']}")
        
        self._systemInstruction = "\n".join(sections)
        return self._systemInstruction
    
    def getLanguageInstruction(self, language: str) -> str:
        """Get language-specific instruction"""
        prompts = self._ensurePromptsLoaded()
        instructions = prompts.get("language_instructions", {})
        return instructions.get(language, instructions.get("tr", "Türkçe olarak net ve samimi yanıtlar ver."))
    
    def getRateLimitMessage(self, language: str) -> str:
        """Get rate limit message in specified language"""
        prompts = self._ensurePromptsLoaded()
        rateLimitMessages = prompts.get("rate_limit_messages", {})
        return rateLimitMessages.get(
            language,
            rateLimitMessages.get("tr", "Çok fazla istek. Lütfen biraz bekleyin.")
        )
    
    def getErrorMessage(self, language: str) -> str:
        """Get generic error message in specified language"""
        prompts = self._ensurePromptsLoaded()
        errorMessages = prompts.get("error_messages", {})
        return errorMessages.get(
            language,
            errorMessages.get("tr", "Üzgünüm, bir sorun oluştu. Lütfen tekrar deneyin.")
        )

    def reloadPrompts(self) -> None:
        """Reload prompts from file"""
        self._systemInstruction = None
        self._prompts = None
        self._loadPrompts()
        logger.info("Prompts reloaded")


# Global singleton instance
_promptManager: Optional[PromptManager] = None


def getPromptManager(promptsPath: Optional[str] = None) -> PromptManager:
    """Get global PromptManager instance"""
    global _promptManager
    if _promptManager is None:
        _promptManager = PromptManager(promptsPath)
    return _promptManager
