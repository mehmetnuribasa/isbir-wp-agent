"""
Production-grade Message Queue System.
Handles controlled, fault-isolated message processing with debouncing.
Adapted from İşbir-Whatsapp-Chatbot into clean architecture.
"""

import asyncio
import logging
import traceback
from typing import Dict, Callable, Any
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class QueuedMessage:
    """Represents a message in the processing queue"""
    phone: str
    text: str
    message_id: str
    timestamp: datetime
    retry_count: int = 0
    max_retries: int = 2


class SmartMessageDebouncer:
    """
    Per-user message debouncing with smart concatenation.
    Merges rapid messages together with safety limits to prevent spam/OOM.
    """
    
    def __init__(self, target_queue: asyncio.Queue, debounceSeconds: float = 2.0):
        self.target_queue = target_queue
        self.debounceSeconds = debounceSeconds
        
        # 3-Layer Security Limits
        self.maxMessages = 10        # Max 10 mesaj birleştirilebilir
        self.maxChars = 1500         # Toplam karakter sınırı
        self.maxWaitSeconds = 10.0   # En fazla 10 saniye bekletilebilir
        
        self.sessions: Dict[str, dict] = {}
        self._lock = asyncio.Lock()
        
    async def processMessage(self, phone: str, newMessage: QueuedMessage) -> bool:
        """Process incoming message. Returns True if accepted into concatenation buffer."""
        async with self._lock:
            now = datetime.now()
            
            if phone in self.sessions:
                session = self.sessions[phone]
                
                # Güvenlik Kontrolleri (Limits)
                timeElapsed = (now - session["firstTime"]).total_seconds()
                currentChars = sum(len(m.text) for m in session["messages"])
                
                if (timeElapsed >= self.maxWaitSeconds or 
                    len(session["messages"]) >= self.maxMessages or 
                    currentChars + len(newMessage.text) > self.maxChars):
                    
                    # Sınır aşıldı: Eskileri hemen kuyruğa at, yenisi için yeni seans başlat
                    logger.warning(f"Debounce limits hit for {phone}, forcing push.")
                    await self._pushSessionUnsafe(phone)
                    self._startSessionUnsafe(phone, newMessage, now)
                    return True
                
                # Sınırlar güvenliyse: Listeye ekle ve zamanlayıcıyı sıfırla
                session["messages"].append(newMessage)
                session["lastTime"] = now
                
                session["task"].cancel()
                session["task"] = asyncio.create_task(self._waitAndPush(phone))
                
                logger.info(f"Concatenated message {len(session['messages'])} for {phone}")
                return True
                
            else:
                self._startSessionUnsafe(phone, newMessage, now)
                return True
                
    def _startSessionUnsafe(self, phone: str, msg: QueuedMessage, now: datetime):
        """Start a new concatenation session for user (internal, unsafe)."""
        task = asyncio.create_task(self._waitAndPush(phone))
        self.sessions[phone] = {
            "messages": [msg],
            "firstTime": now,
            "lastTime": now,
            "task": task
        }
        
    async def _waitAndPush(self, phone: str):
        """Wait for silence, then push to main queue."""
        try:
            await asyncio.sleep(self.debounceSeconds)
        except asyncio.CancelledError:
            return  # Yeni mesaj geldi, zamanlayıcı sıfırlandı
            
        async with self._lock:
            await self._pushSessionUnsafe(phone)
            
    async def _pushSessionUnsafe(self, phone: str):
        """Merge all messages and push to the actual processing queue."""
        if phone not in self.sessions:
            return
            
        session = self.sessions.pop(phone)
        messages = session["messages"]
        if not messages:
            return
            
        # Mesajları birleştir
        mergedText = "\n".join(m.text for m in messages)
        firstMsg = messages[0]
        
        mergedMsg = QueuedMessage(
            phone=phone,
            text=mergedText,
            message_id=firstMsg.message_id,
            timestamp=firstMsg.timestamp,
            retry_count=0,
            max_retries=firstMsg.max_retries
        )
        
        try:
            self.target_queue.put_nowait(mergedMsg)
            logger.info(f"Pushed merged message ({len(messages)} parts) to main queue for {phone}")
        except asyncio.QueueFull:
            logger.error(f"Queue full! Dropped merged message for {phone}")


class MessageQueue:
    """
    Async message queue with worker pool for controlled processing.
    Provides fault isolation and prevents system-wide crashes.
    """
    
    def __init__(
        self,
        processCallback: Callable,
        maxSize: int = 1000,
        workerCount: int = 3,
        timeoutSeconds: int = 60,
        debounceSeconds: float = 2.0,
    ):
        self.processCallback = processCallback
        self.maxSize = maxSize
        self.workerCount = workerCount
        self.timeoutSeconds = timeoutSeconds
        
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=maxSize)
        self.workers: list = []
        self.running = False
        
        self.debouncer = SmartMessageDebouncer(self.queue, debounceSeconds)
        
        self.stats = {
            "total_enqueued": 0,
            "total_processed": 0,
            "total_failed": 0,
            "total_timeout": 0,
            "total_debounced": 0,
        }
        
        logger.info(
            f"Message queue initialized",
            extra={"workerCount": workerCount, "maxSize": maxSize}
        )
    
    async def start(self) -> None:
        """Start queue workers"""
        if self.running:
            return
        
        self.running = True
        
        for i in range(self.workerCount):
            worker = asyncio.create_task(self._worker(i))
            self.workers.append(worker)
        
        logger.info(f"Started {self.workerCount} queue workers")
    
    async def stop(self) -> None:
        """Stop queue workers gracefully"""
        self.running = False
        
        for worker in self.workers:
            worker.cancel()
        
        await asyncio.gather(*self.workers, return_exceptions=True)
        logger.info("Queue workers stopped")
    
    async def enqueue(self, message: QueuedMessage) -> bool:
        """Add message to queue with smart debouncing & concatenation."""
        try:
            accepted = await self.debouncer.processMessage(message.phone, message)
            if accepted:
                self.stats["total_enqueued"] += 1
                logger.debug(
                    f"Buffered message from {message.phone}",
                    extra={"phone": message.phone}
                )
                return True
            else:
                self.stats["total_debounced"] += 1
                return False
                
        except Exception as e:
            logger.error(f"Error enqueueing message: {e}", exc_info=True)
            return False
    
    async def _worker(self, workerId: int) -> None:
        """Worker task that processes messages from queue."""
        logger.info(f"Worker {workerId} started")
        
        while self.running:
            try:
                try:
                    message = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                await self._processMessageSafe(message, workerId)
                self.queue.task_done()
                
            except asyncio.CancelledError:
                logger.info(f"Worker {workerId} cancelled")
                break
            except Exception as e:
                logger.error(f"Worker {workerId} error: {e}", exc_info=True)
                continue
        
        logger.info(f"Worker {workerId} stopped")
    
    async def _processMessageSafe(self, message: QueuedMessage, workerId: int) -> None:
        """Process a single message with complete fault isolation."""
        startTime = datetime.now()
        
        try:
            logger.info(
                f"Worker {workerId} processing message from {message.phone} "
                f"(attempt {message.retry_count + 1}/{message.max_retries + 1})",
                extra={"workerId": workerId, "phone": message.phone, "attempt": message.retry_count + 1}
            )
            
            await asyncio.wait_for(
                self.processCallback(message.phone, message.text, message.message_id),
                timeout=self.timeoutSeconds
            )
            
            self.stats["total_processed"] += 1
            duration = (datetime.now() - startTime).total_seconds()
            logger.info(
                f"Worker {workerId} completed message in {duration:.2f}s",
                extra={"workerId": workerId, "duration": duration}
            )
            
        except asyncio.TimeoutError:
            self.stats["total_timeout"] += 1
            logger.error(
                f"Worker {workerId} timeout processing message from {message.phone}",
                extra={"workerId": workerId, "phone": message.phone, "timeout": self.timeoutSeconds}
            )
        
        except Exception as e:
            self.stats["total_failed"] += 1
            logger.error(
                f"Worker {workerId} failed processing message from {message.phone}: {e}",
                extra={"workerId": workerId, "phone": message.phone},
                exc_info=True
            )
            
            # Retry logic
            if message.retry_count < message.max_retries:
                message.retry_count += 1
                logger.info(
                    f"Retrying message from {message.phone} (attempt {message.retry_count + 1})",
                    extra={"phone": message.phone, "attempt": message.retry_count + 1}
                )
                
                await asyncio.sleep(2.0 ** message.retry_count)
                try:
                    await self.queue.put(message)
                except asyncio.QueueFull:
                    logger.error("Cannot retry - queue full")
            else:
                logger.error(f"Max retries reached for {message.phone}")
    
    def getStats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        return {
            **self.stats,
            "queue_size": self.queue.qsize(),
            "worker_count": len(self.workers),
            "running": self.running,
        }
