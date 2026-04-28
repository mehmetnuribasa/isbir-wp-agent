import asyncio
import pytest
from datetime import datetime
from aiChatbot.services.messageQueue import MessageQueue, QueuedMessage, SmartMessageDebouncer

@pytest.fixture
def message_queue():
    # Use a dummy process callback
    processed_messages = []
    
    async def dummy_process(phone, text, messageId):
        processed_messages.append((phone, text, messageId))
        await asyncio.sleep(0.1) # Simulate some work
    
    # Very short debounce for testing (0.5s)
    mq = MessageQueue(
        processCallback=dummy_process, 
        maxSize=100, 
        workerCount=2, 
        timeoutSeconds=5, 
        debounceSeconds=0.5
    )
    mq.processed_messages = processed_messages # Attach to inspect later
    return mq

@pytest.mark.asyncio
async def test_debouncer_merges_rapid_messages(message_queue):
    await message_queue.start()
    
    now = datetime.now()
    phone = "905551234567"
    
    # Send 3 messages rapidly (under 0.5s)
    await message_queue.enqueue(QueuedMessage(phone, "merhaba", "id1", now))
    await asyncio.sleep(0.1)
    await message_queue.enqueue(QueuedMessage(phone, "nasılsın", "id2", now))
    await asyncio.sleep(0.1)
    await message_queue.enqueue(QueuedMessage(phone, "sorum var", "id3", now))
    
    # Wait for debounce to trigger and processing to finish (0.5 + 0.2 buffer)
    await asyncio.sleep(0.8)
    
    assert len(message_queue.processed_messages) == 1
    processed_phone, processed_text, processed_id = message_queue.processed_messages[0]
    
    assert processed_phone == phone
    # Messages should be merged with newlines
    assert processed_text == "merhaba\nnasılsın\nsorum var"
    assert processed_id == "id1" # Should use the first message's ID
    
    await message_queue.stop()

@pytest.mark.asyncio
async def test_debouncer_limits_max_messages(message_queue):
    await message_queue.start()
    
    # Reduce max messages to 3 for testing
    message_queue.debouncer.maxMessages = 3
    
    now = datetime.now()
    phone = "905559998877"
    
    # Send 4 messages rapidly
    for i in range(4):
        await message_queue.enqueue(QueuedMessage(phone, f"msg{i}", f"id{i}", now))
        await asyncio.sleep(0.05)
    
    # Wait a bit
    await asyncio.sleep(0.8)
    
    # It should have triggered a forced push at the 3rd message, and the 4th message should be in a new session
    assert len(message_queue.processed_messages) == 2
    
    assert message_queue.processed_messages[0][1] == "msg0\nmsg1\nmsg2"
    assert message_queue.processed_messages[1][1] == "msg3"
    
    await message_queue.stop()
