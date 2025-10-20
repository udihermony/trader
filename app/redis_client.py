"""
Redis client for async task queuing and caching.
"""

import json
import asyncio
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta

import redis.asyncio as redis
from redis.asyncio import Redis
from loguru import logger

from app.config import settings


class RedisClient:
    """Async Redis client for task queuing and caching."""
    
    def __init__(self):
        self._redis: Optional[Redis] = None
        self._connection_pool = None
    
    async def connect(self):
        """Connect to Redis server."""
        try:
            self._connection_pool = redis.ConnectionPool.from_url(
                settings.redis_url,
                password=settings.redis_password,
                decode_responses=True,
                max_connections=20
            )
            self._redis = Redis(connection_pool=self._connection_pool)
            
            # Test connection
            await self._redis.ping()
            logger.info("Connected to Redis successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Redis server."""
        if self._redis:
            await self._redis.close()
            logger.info("Disconnected from Redis")
    
    @property
    def redis(self) -> Redis:
        """Get Redis client instance."""
        if self._redis is None:
            raise RuntimeError("Redis client not connected. Call connect() first.")
        return self._redis
    
    # Queue Operations
    async def enqueue_task(self, queue_name: str, task_data: Dict[str, Any], priority: int = 0) -> bool:
        """Enqueue a task to the specified queue."""
        try:
            task = {
                "id": f"{queue_name}_{datetime.utcnow().timestamp()}",
                "data": task_data,
                "priority": priority,
                "created_at": datetime.utcnow().isoformat(),
                "attempts": 0,
                "max_attempts": 3
            }
            
            # Use priority-based queuing
            score = priority + datetime.utcnow().timestamp()
            await self.redis.zadd(f"queue:{queue_name}", {json.dumps(task): score})
            
            logger.debug(f"Enqueued task to {queue_name}: {task['id']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to enqueue task to {queue_name}: {e}")
            return False
    
    async def dequeue_task(self, queue_name: str, timeout: int = 0) -> Optional[Dict[str, Any]]:
        """Dequeue a task from the specified queue."""
        try:
            # Get task with highest priority (lowest score)
            result = await self.redis.bzpopmin(f"queue:{queue_name}", timeout=timeout)
            
            if result:
                queue, task_json, score = result
                task = json.loads(task_json)
                logger.debug(f"Dequeued task from {queue_name}: {task['id']}")
                return task
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to dequeue task from {queue_name}: {e}")
            return None
    
    async def get_queue_size(self, queue_name: str) -> int:
        """Get the size of a queue."""
        try:
            return await self.redis.zcard(f"queue:{queue_name}")
        except Exception as e:
            logger.error(f"Failed to get queue size for {queue_name}: {e}")
            return 0
    
    async def clear_queue(self, queue_name: str) -> bool:
        """Clear all tasks from a queue."""
        try:
            await self.redis.delete(f"queue:{queue_name}")
            logger.info(f"Cleared queue: {queue_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear queue {queue_name}: {e}")
            return False
    
    # Cache Operations
    async def set_cache(self, key: str, value: Any, expire_seconds: Optional[int] = None) -> bool:
        """Set a cache value."""
        try:
            serialized_value = json.dumps(value, default=str)
            await self.redis.set(key, serialized_value, ex=expire_seconds)
            return True
        except Exception as e:
            logger.error(f"Failed to set cache key {key}: {e}")
            return False
    
    async def get_cache(self, key: str) -> Optional[Any]:
        """Get a cache value."""
        try:
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Failed to get cache key {key}: {e}")
            return None
    
    async def delete_cache(self, key: str) -> bool:
        """Delete a cache key."""
        try:
            result = await self.redis.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"Failed to delete cache key {key}: {e}")
            return False
    
    async def exists_cache(self, key: str) -> bool:
        """Check if a cache key exists."""
        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Failed to check cache key {key}: {e}")
            return False
    
    # Pub/Sub Operations
    async def publish_message(self, channel: str, message: Dict[str, Any]) -> bool:
        """Publish a message to a channel."""
        try:
            serialized_message = json.dumps(message, default=str)
            subscribers = await self.redis.publish(channel, serialized_message)
            logger.debug(f"Published message to {channel}, {subscribers} subscribers")
            return True
        except Exception as e:
            logger.error(f"Failed to publish message to {channel}: {e}")
            return False
    
    async def subscribe_to_channel(self, channel: str, callback):
        """Subscribe to a channel and call callback for each message."""
        try:
            pubsub = self.redis.pubsub()
            await pubsub.subscribe(channel)
            
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        await callback(channel, data)
                    except Exception as e:
                        logger.error(f"Error processing message from {channel}: {e}")
                        
        except Exception as e:
            logger.error(f"Failed to subscribe to {channel}: {e}")
    
    # Rate Limiting
    async def is_rate_limited(self, key: str, limit: int, window_seconds: int) -> bool:
        """Check if a key is rate limited."""
        try:
            current_time = datetime.utcnow()
            window_start = current_time - timedelta(seconds=window_seconds)
            
            # Use sliding window counter
            pipe = self.redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start.timestamp())
            pipe.zcard(key)
            pipe.zadd(key, {str(current_time.timestamp()): current_time.timestamp()})
            pipe.expire(key, window_seconds)
            
            results = await pipe.execute()
            current_count = results[1]
            
            return current_count >= limit
            
        except Exception as e:
            logger.error(f"Failed to check rate limit for {key}: {e}")
            return False
    
    # Health Check
    async def health_check(self) -> Dict[str, Any]:
        """Perform Redis health check."""
        try:
            info = await self.redis.info()
            ping_time = await self.redis.ping()
            
            return {
                "status": "healthy",
                "ping": ping_time,
                "version": info.get("redis_version"),
                "uptime": info.get("uptime_in_seconds"),
                "connected_clients": info.get("connected_clients"),
                "used_memory": info.get("used_memory_human")
            }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Global Redis client instance
redis_client = RedisClient()
