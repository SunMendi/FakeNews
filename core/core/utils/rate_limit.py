import time
from typing import Optional

from django.core.cache import cache


def is_rate_limited(ip_address: str, endpoint: str, limit: int, window_seconds: int) -> bool:
    """
    Checks if an IP address has exceeded the rate limit for a specific endpoint using
    the Sliding Window algorithm with Redis Sorted Sets (ZSET).

    Returns:
        bool: True if the request is rate-limited (blocked), False if allowed.
    """
    
    # 1. Get the raw Redis connection
    # We use cache.client.get_client() to access advanced Redis features (ZSET)
    # because Django's default cache API only supports basic key-value operations.
    try:
        redis_client = cache.client.get_client()
    except AttributeError:
        # Fallback for local development if Redis isn't running correctly
        return False

    # 2. Create a unique key for this IP and endpoint
    # Example: "rate_limit:search:192.168.1.5"
    redis_key = f"rate_limit:{endpoint}:{ip_address}"

    # 3. Get current time in milliseconds
    current_time_ms = int(time.time() * 1000)

    # 4. Calculate the start of our sliding window
    # Everything before this time is expired and should not count against the limit.
    window_start_ms = current_time_ms - (window_seconds * 1000)

    # 5. Create a Redis Pipeline
    # A pipeline groups multiple commands together so they execute atomically.
    # This prevents race conditions if two requests hit at the exact same millisecond.
    pipeline = redis_client.pipeline()

    try:
        # Step A: Remove old requests that fall outside the current sliding window
        # ZREMRANGEBYSCORE key min max
        pipeline.zremrangebyscore(redis_key, 0, window_start_ms)

        # Step B: Add the current request
        # ZADD key {value: score}
        # Value must be unique, so we combine current time with a simple string
        # Score is used for sorting/filtering, which is our timestamp
        request_member = f"req_{current_time_ms}"
        pipeline.zadd(redis_key, {request_member: current_time_ms})

        # Step C: Count how many requests are in the current window
        # ZCARD key returns the total number of items in the sorted set
        pipeline.zcard(redis_key)

        # Step D: Set an expiration on the entire key to clean up memory
        # If the user doesn't make another request for the window duration, the whole key deletes itself.
        pipeline.expire(redis_key, window_seconds)

        # 6. Execute all pipeline commands at once
        results = pipeline.execute()

        # 7. Analyze the results
        # results is a list matching our pipeline steps: [zrem_count, zadd_count, zcard_count, expire_result]
        # We care about Step C (index 2): The total number of requests in the window
        request_count = results[2]

        # 8. Make the decision
        # If the count is strictly greater than the limit, block the request.
        if request_count > limit:
             # Even though we just added the current request, we are blocking it.
             # In a strict implementation, we might not count blocked requests,
             # but counting them acts as a penalty for spamming.
             return True

        return False

    except Exception as e:
         # If Redis fails for some reason (network error), fail open (allow the request)
         # We don't want to bring down the whole app just because the rate limiter is sick.
         print(f"Rate Limiter Redis Error: {e}")
         return False
