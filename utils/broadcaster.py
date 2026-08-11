import redis.asyncio as redis
from config import settings
import json

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

async def broadcast_log(session_id: str, message: str):
    """
    Publish a log message to the session's Redis channel.
    """
    channel = f"session_{session_id}_logs"
    await redis_client.publish(channel, json.dumps({"data": message}))

async def subscribe_logs(session_id: str):
    """
    Async generator that subscribes to the session's Redis channel
    and yields SSE formatted messages.
    """
    channel = f"session_{session_id}_logs"
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                payload = json.loads(message["data"])
                # Yield in standard SSE format
                yield f"data: {payload['data']}\n\n"
                
                # If we send a specific termination message, break
                if "[END_OF_STREAM]" in payload['data']:
                    break
    finally:
        await pubsub.unsubscribe(channel)
