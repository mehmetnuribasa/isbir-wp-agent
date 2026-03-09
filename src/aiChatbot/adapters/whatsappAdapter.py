"""
WhatsApp adapter using direct httpx calls to WhatsApp Cloud API.
Combines template's ChannelAdapter interface with İşbir's interactive messaging features.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..interfaces.channelAdapter import (
    ChannelAdapter,
    MessageConversionError,
    MessageSendError,
)
from ..models.standardMessage import StandardMessage

logger = logging.getLogger(__name__)


class WhatsAppAdapter(ChannelAdapter):
    """
    WhatsApp Cloud API adapter with interactive messaging support.
    Uses httpx for direct API calls (no PyWa wrapper).
    Supports: text messages, interactive buttons, interactive lists,
    mark-as-read, typing indicator.
    """
    
    def __init__(
        self,
        phoneNumberId: str,
        accessToken: str,
        webhookVerifyToken: Optional[str] = None,
        apiVersion: str = "v21.0",
    ):
        super().__init__(
            channelType="whatsapp",
            config={
                "phoneNumberId": phoneNumberId,
                "apiVersion": apiVersion,
            },
        )
        self.phoneNumberId = phoneNumberId
        self.accessToken = accessToken
        self.webhookVerifyToken = webhookVerifyToken
        self.apiVersion = apiVersion
        self.baseUrl = f"https://graph.facebook.com/{apiVersion}/{phoneNumberId}"
        
        self.headers = {
            "Authorization": f"Bearer {accessToken}",
            "Content-Type": "application/json",
        }
        
        self._client: Optional[httpx.AsyncClient] = None
        
        logger.info("WhatsApp adapter initialized (httpx-based, interactive support)")
    
    async def _getClient(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def initializeChannel(self) -> bool:
        """Initialize WhatsApp adapter"""
        self.isInitialized = True
        return True
    
    def receiveMessage(self, rawMessage: Any) -> Optional[StandardMessage]:
        """Convert WhatsApp webhook data to StandardMessage"""
        try:
            messageData = self.extractMessageData(rawMessage)
            if not messageData:
                return None
            
            return StandardMessage(
                userId=messageData["from"],
                channelId=messageData["from"],
                content=messageData["text"],
                messageId=messageData["message_id"],
                channelType="whatsapp",
                metadata={
                    "type": messageData.get("type", "text"),
                    "timestamp": messageData.get("timestamp"),
                },
            )
        except Exception as e:
            logger.error(f"Error converting message: {e}", exc_info=True)
            return None
    
    async def sendMessage(
        self,
        content: str,
        channelId: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send text message through WhatsApp"""
        try:
            await self.sendTextMessage(channelId, content)
            return True
        except Exception as e:
            logger.error(f"Error sending message to {channelId}: {e}", exc_info=True)
            return False
    
    def validateWebhook(self, request: Any) -> bool:
        """Validate webhook verify request"""
        if not self.webhookVerifyToken:
            return True
        
        try:
            params = request.get("queryParams", {})
            mode = params.get("hub.mode")
            token = params.get("hub.verify_token")
            return mode == "subscribe" and token == self.webhookVerifyToken
        except Exception:
            return False
    
    def getSupportedMessageTypes(self) -> List[str]:
        """Get supported message types"""
        return ["text", "interactive"]
    
    async def shutdown(self) -> None:
        """Clean up HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.info("WhatsApp adapter HTTP client closed")
        self.isInitialized = False
    
    # --- WhatsApp API methods ---
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _makeRequest(
        self,
        endpoint: str,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Make HTTP request to WhatsApp API with retry."""
        client = await self._getClient()
        url = f"{self.baseUrl}/{endpoint}"
        
        try:
            response = await client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            data = response.json()
            logger.debug(f"WhatsApp API response: {data}")
            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Request error: {e}")
            raise
    
    async def markAsRead(self, messageId: str) -> bool:
        """Mark a message as read"""
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": messageId,
        }
        try:
            await self._makeRequest("messages", payload)
            logger.debug(f"Marked message {messageId} as read")
            return True
        except Exception as e:
            logger.error(f"Failed to mark as read: {e}")
            return False
    
    async def sendTypingIndicator(self, phone: str) -> None:
        """
        Simulate typing indicator.
        WhatsApp Cloud API does not expose a native 'typing' endpoint.
        We simulate by inserting a short delay.
        """
        import asyncio
        logger.debug(f"Typing indicator → {phone}")
        await asyncio.sleep(0.8)
    
    async def sendTextMessage(
        self,
        to: str,
        text: str,
        previewUrl: bool = False,
    ) -> Optional[str]:
        """Send a text message"""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": previewUrl, "body": text},
        }
        try:
            response = await self._makeRequest("messages", payload)
            messageId = response.get("messages", [{}])[0].get("id")
            logger.info(f"Text sent to {to}", extra={"to": to})
            return messageId
        except Exception as e:
            logger.error(f"Failed to send text: {e}")
            return None
    
    async def sendInteractiveButtons(
        self,
        to: str,
        bodyText: str,
        buttons: List[Dict[str, str]],
        headerText: Optional[str] = None,
        footerText: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send an interactive button message (max 3 buttons).
        
        Args:
            to: Recipient phone number
            bodyText: Main message text
            buttons: List of dicts with 'id' and 'title' keys (max 3, title max 20 chars)
            headerText: Optional header
            footerText: Optional footer
        """
        buttonObjects = [
            {
                "type": "reply",
                "reply": {
                    "id": btn["id"][:256],
                    "title": btn["title"][:20],
                },
            }
            for btn in buttons[:3]
        ]
        
        interactiveObj: Dict[str, Any] = {
            "type": "button",
            "body": {"text": bodyText},
            "action": {"buttons": buttonObjects},
        }
        
        if headerText:
            interactiveObj["header"] = {"type": "text", "text": headerText}
        if footerText:
            interactiveObj["footer"] = {"text": footerText}
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": interactiveObj,
        }
        
        try:
            response = await self._makeRequest("messages", payload)
            messageId = response.get("messages", [{}])[0].get("id")
            logger.info(f"Interactive buttons sent to {to}")
            return messageId
        except Exception as e:
            logger.error(f"Failed to send interactive buttons: {e}")
            # Fallback to plain text
            fallback = bodyText + "\n\n" + "\n".join(f"• {btn['title']}" for btn in buttons)
            return await self.sendTextMessage(to, fallback)
    
    async def sendInteractiveList(
        self,
        to: str,
        bodyText: str,
        buttonLabel: str,
        sections: List[Dict[str, Any]],
        headerText: Optional[str] = None,
        footerText: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send an interactive list message (for 4+ options).
        
        Args:
            to: Recipient phone number
            bodyText: Main message text
            buttonLabel: Label on list trigger button (max 20 chars)
            sections: List of dicts: {'title': str, 'rows': [{'id': str, 'title': str}]}
            headerText: Optional header
            footerText: Optional footer
        """
        interactiveObj: Dict[str, Any] = {
            "type": "list",
            "body": {"text": bodyText},
            "action": {
                "button": buttonLabel[:20],
                "sections": sections,
            },
        }
        
        if headerText:
            interactiveObj["header"] = {"type": "text", "text": headerText}
        if footerText:
            interactiveObj["footer"] = {"text": footerText}
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": interactiveObj,
        }
        
        try:
            response = await self._makeRequest("messages", payload)
            messageId = response.get("messages", [{}])[0].get("id")
            logger.info(f"Interactive list sent to {to}")
            return messageId
        except Exception as e:
            logger.error(f"Failed to send interactive list: {e}")
            fallbackLines = [bodyText]
            for section in sections:
                for row in section.get("rows", []):
                    fallbackLines.append(f"• {row['title']}")
            return await self.sendTextMessage(to, "\n".join(fallbackLines))
    
    # --- Webhook parsing helpers ---
    
    @staticmethod
    def extractMessageData(webhookData: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Extract message from WhatsApp webhook payload."""
        try:
            entry = webhookData.get("entry", [])
            if not entry:
                return None
            
            changes = entry[0].get("changes", [])
            if not changes:
                return None
            
            value = changes[0].get("value", {})
            messages = value.get("messages", [])
            
            if not messages:
                return None
            
            message = messages[0]
            msgType = message.get("type")
            
            # Handle text messages
            if msgType == "text":
                return {
                    "from": message.get("from"),
                    "message_id": message.get("id"),
                    "text": message.get("text", {}).get("body", ""),
                    "timestamp": message.get("timestamp"),
                    "type": msgType,
                }
            
            # Handle interactive replies (button or list selections)
            if msgType == "interactive":
                interactive = message.get("interactive", {})
                replyType = interactive.get("type")
                
                if replyType == "button_reply":
                    selected = interactive.get("button_reply", {})
                    text = selected.get("title", selected.get("id", ""))
                elif replyType == "list_reply":
                    selected = interactive.get("list_reply", {})
                    text = selected.get("title", selected.get("id", ""))
                else:
                    logger.debug(f"Unknown interactive type: {replyType}")
                    return None
                
                logger.debug(f"Interactive reply: {replyType} → '{text}'")
                return {
                    "from": message.get("from"),
                    "message_id": message.get("id"),
                    "text": text,
                    "timestamp": message.get("timestamp"),
                    "type": msgType,
                }
            
            logger.debug(f"Ignoring unsupported message type: {msgType}")
            return None
            
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Parse error: {e}")
            return None
    
    @staticmethod
    def isStatusUpdate(webhookData: Dict[str, Any]) -> bool:
        """Check if webhook payload is a status update (not a message)."""
        try:
            value = webhookData["entry"][0]["changes"][0]["value"]
            return "statuses" in value
        except (KeyError, IndexError):
            return False
