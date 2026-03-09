"""
Channel manager for routing messages to appropriate adapters.
"""

import logging
from typing import Any, Dict, Optional

from ..interfaces.channelAdapter import ChannelAdapter
from ..interfaces.messageProcessor import MessageProcessor
from ..models.standardMessage import StandardMessage

logger = logging.getLogger(__name__)


class ChannelManager:
    """
    Manages multiple channel adapters and routes messages between them.
    """
    
    def __init__(self, messageProcessor: MessageProcessor):
        self.messageProcessor = messageProcessor
        self._adapters: Dict[str, ChannelAdapter] = {}
        logger.info("ChannelManager initialized")
    
    def registerAdapter(self, channelName: str, adapter: ChannelAdapter) -> None:
        """Register a channel adapter"""
        self._adapters[channelName] = adapter
        logger.info(
            f"Adapter registered: {channelName}",
            extra={"channelName": channelName, "adapterType": type(adapter).__name__}
        )
    
    def getAdapter(self, channelName: str) -> Optional[ChannelAdapter]:
        """Get a registered adapter by name"""
        return self._adapters.get(channelName)
    
    async def processWebhookMessage(
        self,
        channelName: str,
        rawMessage: Any,
    ) -> Optional[str]:
        """
        Process an incoming webhook message through registered adapter.
        
        Args:
            channelName: Name of the channel
            rawMessage: Raw message from webhook
            
        Returns:
            AI response text if message was processed, None otherwise
        """
        adapter = self._adapters.get(channelName)
        if not adapter:
            logger.warning(f"No adapter registered for channel: {channelName}")
            return None
        
        try:
            # Convert raw message to standard message
            standardMessage = adapter.receiveMessage(rawMessage)
            
            if standardMessage is None:
                logger.debug(f"No valid message extracted from {channelName} webhook")
                return None
            
            # Process through message processor
            response = await self.messageProcessor.processMessage(standardMessage)
            
            # Send response back through the channel
            if response:
                await adapter.sendMessage(
                    content=response,
                    channelId=standardMessage.channelId,
                    metadata=standardMessage.metadata,
                )
            
            return response
            
        except Exception as e:
            logger.error(
                f"Error processing {channelName} message: {e}",
                exc_info=True,
            )
            return None
    
    def getRegisteredChannels(self) -> list[str]:
        """Get list of registered channel names"""
        return list(self._adapters.keys())
    
    async def shutdownAll(self) -> None:
        """Shutdown all registered adapters"""
        for name, adapter in self._adapters.items():
            try:
                await adapter.shutdown()
                logger.info(f"Adapter shut down: {name}")
            except Exception as e:
                logger.error(f"Error shutting down adapter {name}: {e}")
    
    def getStats(self) -> Dict[str, Any]:
        """Get channel manager statistics"""
        return {
            "registeredChannels": list(self._adapters.keys()),
            "adapterCount": len(self._adapters),
        }
