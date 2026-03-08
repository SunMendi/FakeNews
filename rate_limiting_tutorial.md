# Sliding Window Rate Limiting with Redis & Django

This document summarizes the mentorship session on implementing a sliding window rate limiter using Redis in a Django Rest Framework (DRF) project.

## 🧠 Concepts Learned

### 1. Redis
*   **What it is:** A blazing-fast, in-memory, NoSQL key-value store. It doesn't use traditional tables, columns, or rows. You create keys on the fly (e.g., `rate_limit:search:192.168.1.1`).
*   **How Django talks to it:** 
    *   `redis` (redis-py): The core python library that translates Python to network packets Redis understands.
    *   `django-redis`: A bridge plugin that integrates Redis into Django's standard caching system, while also providing a "backdoor" (`cache.client.get_client()`) to use advanced Redis features.

### 2. The Sliding Window Algorithm
*   **The Problem with Fixed Windows:** Simply counting requests per clock minute (e.g., 12:00 to 12:01) is flawed because a user can spam requests at 12:00:59 and 12:01:01, bypassing the intended limit.
*   **The Solution:** The sliding window looks back exactly *X seconds* from the current millisecond. If there are fewer requests in that window than the limit, the request is allowed.
*   **Redis Sorted Sets (`ZSET`):** We use this advanced data structure to store timestamps. 
    *   `Key`: The user's IP + endpoint.
    *   `Score`: The exact timestamp of the request.
    *   `Value`: A unique string for that request.

### 3. Redis Pipelines
*   We use a `pipeline()` to bundle multiple Redis commands (`ZREMRANGEBYSCORE`, `ZADD`, `ZCARD`, `EXPIRE`) and execute them atomically. This prevents "race conditions" where two requests hit the server at the exact same millisecond and corrupt the count.

### 4. DRF Custom Permissions
*   Instead of cluttering the main API logic, we enforce rate limits using Django Rest Framework's custom `BasePermission` classes. If a permission class returns `False` (or raises an exception), DRF intercepts the request and automatically returns a `429 Too Many Requests` error.

---

## 🛠️ Step-by-Step Implementation Process

### Step 1: Configure Django Settings
We added configuration to `core/core/settings.py` to tell Django to use `django-redis` as the default cache backend and set up our rate limit variables.

```python
# core/core/settings.py

REDIS_URL = os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/1')
REDIS_KEY_PREFIX = os.getenv('REDIS_KEY_PREFIX', 'fakenews')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'TIMEOUT': None,
        'KEY_PREFIX': REDIS_KEY_PREFIX,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
    }
}

RATE_LIMITS = {
    'search': {
        'limit': int(os.getenv('RATE_LIMIT_SEARCH_LIMIT', '5')),
        'window_seconds': int(os.getenv('RATE_LIMIT_SEARCH_WINDOW_SECONDS', '60')),
    },
}
```

### Step 2: The Core Rate Limiting Logic
We created a utility file `core/core/utils/rate_limit.py` to handle the Redis sorted set operations.

```python
# core/core/utils/rate_limit.py
import time
from typing import Optional
from django.core.cache import cache

def is_rate_limited(ip_address: str, endpoint: str, limit: int, window_seconds: int) -> bool:
    try:
        redis_client = cache.client.get_client()
    except AttributeError:
        return False

    redis_key = f"rate_limit:{endpoint}:{ip_address}"
    current_time_ms = int(time.time() * 1000)
    window_start_ms = current_time_ms - (window_seconds * 1000)
    
    pipeline = redis_client.pipeline()

    try:
        # A: Remove old requests
        pipeline.zremrangebyscore(redis_key, 0, window_start_ms)
        # B: Add current request
        request_member = f"req_{current_time_ms}"
        pipeline.zadd(redis_key, {request_member: current_time_ms})
        # C: Count requests in window
        pipeline.zcard(redis_key)
        # D: Set expiration to clean up memory
        pipeline.expire(redis_key, window_seconds)

        results = pipeline.execute()
        request_count = results[2]

        if request_count > limit:
             return True

        return False

    except Exception as e:
         print(f"Rate Limiter Redis Error: {e}")
         return False
```

### Step 3: Create the DRF Permission Class
We created `core/core/utils/permissions.py` to intercept API requests, extract the IP address, and apply our rate limit logic.

```python
# core/core/utils/permissions.py
from rest_framework import permissions
from rest_framework.exceptions import Throttled
from .rate_limit import is_rate_limited
from django.conf import settings

class SearchRateLimitPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        if not ip_address:
             ip_address = "unknown_ip"

        search_limits = getattr(settings, 'RATE_LIMITS', {}).get('search', {})
        limit = search_limits.get('limit', 5)
        window_seconds = search_limits.get('window_seconds', 60)

        is_blocked = is_rate_limited(
            ip_address=ip_address,
            endpoint="search",
            limit=limit,
            window_seconds=window_seconds
        )

        if is_blocked:
            raise Throttled(detail="Rate limit exceeded. Please wait a moment before trying again.")
            
        return True
```

### Step 4: Apply to the View
Finally, we applied our custom permission class to the specific endpoint we wanted to protect in `core/claims/views.py`.

```python
# core/claims/views.py
from core.utils.permissions import SearchRateLimitPermission

class SearchAPIView(APIView):
    # We add our custom permission alongside existing ones
    permission_classes = [AllowAny, SearchRateLimitPermission]

    def post(self, request):
        # ... normal view logic continues here ...
```
