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


class MessageDebouncer:
    """
    Per-user message debouncing to handle rapid message floods.
    Only processes the most recent message within a time window.
    """
    
    def __init__(self, debounceSeconds: float = 2.0):
        self.debounceSeconds = debounceSeconds
        self.pendingMessages: Dict[str, QueuedMessage] = {}
        self.lastProcessed: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
    
    async def shouldProcess(self, phone: str, newMessage: QueuedMessage) -> bool:
        """Determine if a message should be processed or debounced."""
        async with self._lock:
            now = datetime.now()
            
            lastTime = self.lastProcessed.get(phone)
            if lastTime and (now - lastTime).total_seconds() < self.debounceSeconds:
                self.pendingMessages[phone] = newMessage
                logger.info(
                    f"Debouncing message from {phone} (rapid messages)",
                    extra={"phone": phone}
                )
                return False
            
            if phone in self.pendingMessages:
                self.pendingMessages.pop(phone)
                logger.info(f"Skipping old message, processing latest from {phone}")
            
            self.lastProcessed[phone] = now
            return True


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
        
        self.debouncer = MessageDebouncer(debounceSeconds)
        
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
        """Add message to queue with debouncing."""
        try:
            shouldProcess = await self.debouncer.shouldProcess(message.phone, message)
            
            if not shouldProcess:
                self.stats["total_debounced"] += 1
                return False
            
            try:
                self.queue.put_nowait(message)
                self.stats["total_enqueued"] += 1
                logger.debug(
                    f"Enqueued message from {message.phone}",
                    extra={"phone": message.phone, "queueSize": self.queue.qsize()}
                )
                return True
            except asyncio.QueueFull:
                logger.error(f"Queue full! Cannot enqueue message from {message.phone}")
                return False
                
        except Exception as e:
            logger.error(f"Error enqueueing message: {e}")
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
