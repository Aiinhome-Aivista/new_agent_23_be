import asyncio
import json

# In-memory store for session queues instead of Redis
session_queues = {}

def get_queue(session_id: str) -> asyncio.Queue:
    if session_id not in session_queues:
        session_queues[session_id] = asyncio.Queue()
    return session_queues[session_id]

async def broadcast_log(session_id: str, message: str):
    """
    Publish a log message to the session's in-memory queue.
    """
    queue = get_queue(session_id)
    await queue.put({"data": message})

async def subscribe_logs(session_id: str):
    """
    Async generator that subscribes to the session's in-memory queue
    and yields SSE formatted messages.
    """
    queue = get_queue(session_id)
    
    try:
        while True:
            payload = await queue.get()
            
            # Yield raw SSE format for StreamingResponse
            yield f"data: {payload['data']}\n\n"
            
            # If we send a specific termination message, break
            if "[END_OF_STREAM]" in payload['data']:
                break
    finally:
        # Cleanup queue after stream ends
        if session_id in session_queues:
            del session_queues[session_id]
