"""ASGI entrypoint for running the chatbot server via uvicorn."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Tuple

from aiChatbot.api.app import createApp
from aiChatbot.models.botConfig import loadBotConfig
from aiChatbot.services import buildGeminiService
from aiChatbot.services.channelManager import ChannelManager
from aiChatbot.services.messageProcessorService import MessageProcessorService
from aiChatbot.adapters.whatsappAdapter import WhatsAppAdapter
from aiChatbot.utils.loggingConfig import setupLogging


async def _build_dependencies() -> tuple:
    config = loadBotConfig()
    
    setupLogging(
        level=config.logLevel,
        format_type=config.logFormat,
        enable_correlation_ids=config.logEnableCorrelationIds,
    )
    
    geminiService, knowledgeBase = await buildGeminiService(config)
    sessionManager = geminiService.sessionManager
    
    messageProcessor = MessageProcessorService(
        aiService=geminiService,
        sessionManager=sessionManager,
        defaultLanguage="tr",
    )
    
    channelManager = ChannelManager(messageProcessor=messageProcessor)
    
    if config.whatsappPhoneNumberId and config.whatsappAccessToken:
        whatsappAdapter = WhatsAppAdapter(
            phoneNumberId=config.whatsappPhoneNumberId,
            accessToken=config.whatsappAccessToken,
            webhookVerifyToken=config.whatsappWebhookVerifyToken or None,
            apiVersion=config.whatsappApiVersion,
        )
        channelManager.registerAdapter("whatsapp", whatsappAdapter)
    
    return config, channelManager


def _initialise_dependencies() -> Tuple[Any, Any]:
    """Build async dependencies without blocking the active event loop."""
    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result["value"] = loop.run_until_complete(_build_dependencies())
        except BaseException as exc:
            error["value"] = exc
        finally:
            loop.close()

    thread = threading.Thread(target=_runner, name="dependency-builder", daemon=True)
    thread.start()
    thread.join()

    if "value" not in result:
        raise error.get("value", RuntimeError("Unknown startup failure"))

    return result["value"]


_config, _channel_manager = _initialise_dependencies()
app = createApp(_config, _channel_manager)
