"""
Main application entrypoint.
Bootstraps configuration, logging, services, and runs the FastAPI server.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import uvicorn

from aiChatbot.api.app import createApp
from aiChatbot.models.botConfig import loadBotConfig
from aiChatbot.services import buildGeminiService
from aiChatbot.services.channelManager import ChannelManager
from aiChatbot.services.messageProcessorService import MessageProcessorService
from aiChatbot.adapters.whatsappAdapter import WhatsAppAdapter
from aiChatbot.utils.loggingConfig import setupLogging

logger = logging.getLogger(__name__)


async def bootstrap():
    """Bootstrap the application: load config, build services, create app."""
    # Load configuration
    config = loadBotConfig()
    
    # Setup logging
    setupLogging(
        level=config.logLevel,
        format_type=config.logFormat,
        enable_correlation_ids=config.logEnableCorrelationIds,
    )
    
    logger.info("Starting İşbir WhatsApp Chatbot...")
    logger.info(f"Environment: {config.environment}")
    
    # Build Gemini AI service
    geminiService, knowledgeBase = await buildGeminiService(config)
    sessionManager = geminiService.sessionManager
    
    # Build message processor
    messageProcessor = MessageProcessorService(
        aiService=geminiService,
        sessionManager=sessionManager,
        defaultLanguage="tr",
    )
    
    # Build channel manager
    channelManager = ChannelManager(messageProcessor=messageProcessor)
    
    # Register WhatsApp adapter if configured
    if config.whatsappPhoneNumberId and config.whatsappAccessToken:
        whatsappAdapter = WhatsAppAdapter(
            phoneNumberId=config.whatsappPhoneNumberId,
            accessToken=config.whatsappAccessToken,
            webhookVerifyToken=config.whatsappWebhookVerifyToken or None,
            apiVersion=config.whatsappApiVersion,
        )
        channelManager.registerAdapter("whatsapp", whatsappAdapter)
        logger.info("WhatsApp adapter registered")
    else:
        logger.warning("WhatsApp credentials not configured — adapter not registered")
    
    # Create FastAPI app
    app = createApp(config, channelManager)
    
    logger.info(f"Server ready on {config.serverHost}:{config.serverPort}")
    
    return app, config


def main():
    """Main entry point."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        app, config = loop.run_until_complete(bootstrap())
        
        uvicorn.run(
            app,
            host=config.serverHost,
            port=config.serverPort,
            log_level=config.logLevel.lower(),
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
