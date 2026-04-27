"""
FastAPI application with webhook endpoints.
Merges template's structured logging middleware with İşbir's message queue integration.
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from ..models.botConfig import BotConfig
from ..services.channelManager import ChannelManager
from ..services.messageQueue import MessageQueue, QueuedMessage
from ..services.intentDetector import isSimpleGreeting
from ..adapters.whatsappAdapter import WhatsAppAdapter

logger = logging.getLogger(__name__)

# Module-level references set during app creation
_channelManager: Optional[ChannelManager] = None
_messageQueue: Optional[MessageQueue] = None
_config: Optional[BotConfig] = None


class RequestLoggingMiddleware:
    """Middleware for structured request/response logging."""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        requestId = str(uuid.uuid4())[:8]
        startTime = time.monotonic()
        
        async def sendWrapper(message):
            if message["type"] == "http.response.start":
                duration = time.monotonic() - startTime
                statusCode = message.get("status", 0)
                
                path = scope.get("path", "unknown")
                method = scope.get("method", "unknown")
                
                logger.info(
                    f"{method} {path} → {statusCode} ({duration:.3f}s)",
                    extra={
                        "requestId": requestId,
                        "method": method,
                        "path": path,
                        "statusCode": statusCode,
                        "duration": round(duration, 3),
                    },
                )
            await send(message)
        
        await self.app(scope, receive, sendWrapper)


def createApp(config: BotConfig, channelManager: ChannelManager) -> FastAPI:
    """Create and configure the FastAPI application."""
    global _channelManager, _config
    _channelManager = channelManager
    _config = config
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Application lifecycle manager"""
        global _messageQueue
        
        logger.info("Starting İşbir WhatsApp Chatbot...")
        
        try:
            # Get WhatsApp adapter for process_message callback
            whatsappAdapter = channelManager.getAdapter("whatsapp")
            
            # Initialize message queue
            _messageQueue = MessageQueue(
                processCallback=_processMessage,
                maxSize=config.queueMaxSize,
                workerCount=config.queueWorkerCount,
                timeoutSeconds=config.queueProcessingTimeout,
                debounceSeconds=config.userMessageDebounceSeconds,
            )
            await _messageQueue.start()
            
            logger.info("All services initialized")
            yield
            
        except Exception as e:
            logger.error(f"Startup error: {e}", exc_info=True)
            raise
        
        finally:
            logger.info("Shutting down...")
            
            if _messageQueue:
                await _messageQueue.stop()
            
            await channelManager.shutdownAll()
            logger.info("Shutdown complete")
    
    app = FastAPI(
        title="İşbir WhatsApp Chatbot",
        description="Professional AI chatbot for İşbir Elektrik",
        version="1.0.0",
        lifespan=lifespan,
    )
    
    # Add logging middleware
    app.add_middleware(RequestLoggingMiddleware)
    
    # --- Routes ---
    
    @app.get("/")
    async def root():
        """Root health check"""
        return {
            "status": "running",
            "service": "İşbir WhatsApp Chatbot",
            "version": "1.0.0",
        }
    
    @app.get("/health")
    async def health():
        """Detailed health check with queue and channel stats"""
        queueStats = _messageQueue.getStats() if _messageQueue else {}
        channelStats = channelManager.getStats() if channelManager else {}
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "channelManager": channelManager is not None,
                "messageQueue": _messageQueue is not None,
            },
            "queue": queueStats,
            "channels": channelStats,
        }
    
    @app.get("/webhook/whatsapp")
    async def whatsappWebhookVerify(request: Request):
        """WhatsApp webhook verification (GET)"""
        params = request.query_params
        
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")
        
        if mode == "subscribe" and token == config.whatsappWebhookVerifyToken:
            logger.info("Webhook verified")
            return Response(content=challenge, media_type="text/plain")
        
        logger.warning("Webhook verification failed")
        return JSONResponse({"error": "Verification failed"}, status_code=403)
    
    @app.post("/webhook/whatsapp")
    async def whatsappWebhookHandler(request: Request):
        """Handle incoming WhatsApp messages (POST)"""
        try:
            data = await request.json()
            logger.info(f"Webhook data received: {data}")
            
            # Get WhatsApp adapter
            adapter = channelManager.getAdapter("whatsapp")
            if not adapter or not isinstance(adapter, WhatsAppAdapter):
                logger.warning("No WhatsApp adapter registered")
                return Response(status_code=200)
            
            # Ignore status updates
            if WhatsAppAdapter.isStatusUpdate(data):
                return Response(status_code=200)
            
            # Extract message
            messageData = WhatsAppAdapter.extractMessageData(data)
            if not messageData:
                logger.debug("No valid message in webhook")
                return Response(status_code=200)
            
            phone = messageData["from"]
            text = messageData["text"]
            messageId = messageData["message_id"]
            
            logger.info(
                f"Message from {phone}: {text[:50]}...",
                extra={"phone": phone, "messageLength": len(text)}
            )
            
            # Mark as read
            await adapter.markAsRead(messageId)
            
            # Tüm mesajlar debouncer'a girer, 3 saniye sessizlik sonrası
            # birleşik metin _processMessage içinde kontrol edilir.

            
            # Create queued message for non-greeting messages
            queuedMsg = QueuedMessage(
                phone=phone,
                text=text,
                message_id=messageId,
                timestamp=datetime.now(),
            )
            
            # Enqueue for processing
            if _messageQueue:
                enqueued = await _messageQueue.enqueue(queuedMsg)
                if not enqueued:
                    logger.warning("Message not enqueued (debounced or queue full)")
            
            return Response(status_code=200)
            
        except Exception as e:
            logger.error(f"Webhook error: {e}", exc_info=True)
            return Response(status_code=200)
    
    return app


async def _processMessage(phone: str, text: str, messageId: str) -> None:
    """
    Process a user message through the AI pipeline.
    Called by the message queue worker after debouncing/concatenation.
    """
    global _channelManager
    
    try:
        adapter = _channelManager.getAdapter("whatsapp") if _channelManager else None
        if not adapter or not isinstance(adapter, WhatsAppAdapter):
            logger.error("No WhatsApp adapter available for response")
            return
        
        # Greeting kontrolü burada yapılır — birleşik metin üzerinde
        if isSimpleGreeting(text):
            greetingText = (
                "Merhaba! Ben İşbir Elektrik dijital asistanıyım. 👋\n"
                "Size nasıl yardımcı olabilirim?"
            )
            sections = [
                {
                    "title": "🔌 Ürünlerimiz",
                    "rows": [
                        {"id": "Pro jeneratörler", "title": "Pro Jeneratörler", "description": "13-2000 kVA"},
                        {"id": "Eco jeneratörler", "title": "Eco Jeneratörler", "description": "20-300 kVA"},
                        {"id": "Hibrit jeneratörler", "title": "Hibrit Jeneratörler", "description": "HBR Serisi"},
                        {"id": "Askeri jeneratörler", "title": "Askeri Jeneratörler", "description": "MIL-STD standartları"},
                        {"id": "Marin jeneratörler", "title": "Marin Jeneratörler", "description": "Türk Loydu sertifikalı"},
                    ],
                },
                {
                    "title": "🛠️ Hizmetler & Diğer",
                    "rows": [
                        {"id": "Teknik destek", "title": "Teknik Destek", "description": "7/24 destek hizmeti"},
                        {"id": "Fiyat teklifi", "title": "Fiyat Teklifi", "description": "Satış ekibine bağlanma"},
                        {"id": "Iletisim bilgileri", "title": "İletişim Bilgileri", "description": "Büro ve fabrika"},
                    ],
                },
            ]
            await adapter.sendInteractiveList(
                phone,
                bodyText=greetingText,
                buttonLabel="Konu Seç",
                sections=sections,
                footerText="📞 444 09 10  |  📧 isbir@isbirelektrik.com.tr",
            )
            logger.info(f"Greeting menu sent to {phone}")
            return
        
        # Typing indicator
        await adapter.sendTypingIndicator(phone)
        
        # Process through the channel manager pipeline
        from ..models.standardMessage import StandardMessage
        
        standardMsg = StandardMessage(
            userId=phone,
            channelId=phone,
            content=text,
            channelType="whatsapp",
            metadata={"message_id": messageId},
        )
        
        response = await _channelManager.messageProcessor.processMessage(standardMsg)
        
        if response:
            await adapter.sendTextMessage(phone, response)
            logger.info(f"Response sent to {phone}")
        
    except Exception as e:
        logger.error(f"Processing error for {phone}: {e}", exc_info=True)
        
        try:
            if adapter:
                await adapter.sendTextMessage(
                    phone,
                    "Üzgünüm, bir hata oluştu. Lütfen tekrar deneyin veya "
                    "📞 444 09 10 ile iletişime geçin.",
                )
        except Exception:
            pass
