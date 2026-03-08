from rest_framework import permissions
from rest_framework.exceptions import Throttled
from .rate_limit import is_rate_limited
from django.conf import settings

class SearchRateLimitPermission(permissions.BasePermission):
    """
    Limits users to a specific number of searches per minute based on their IP address.
    Configured in Django settings under RATE_LIMITS['search'].
    """
    def has_permission(self, request, view):
        # 1. Extract the client's IP address
        # We check HTTP_X_FORWARDED_FOR first in case the app is behind a proxy/load balancer
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # If multiple IPs are present, the first one is the original client IP
            ip_address = x_forwarded_for.split(',')[0].strip()
        else:
            # Fallback to the direct connection IP
            ip_address = request.META.get('REMOTE_ADDR')

        # Fallback if IP cannot be determined for some reason
        if not ip_address:
             ip_address = "unknown_ip"

        # 2. Get limits from settings (or use defaults: 5 requests per 60 seconds)
        search_limits = getattr(settings, 'RATE_LIMITS', {}).get('search', {})
        limit = search_limits.get('limit', 5)
        window_seconds = search_limits.get('window_seconds', 60)

        # 3. Check our Redis sliding window rate limiter
        is_blocked = is_rate_limited(
            ip_address=ip_address,
            endpoint="search",
            limit=limit,
            window_seconds=window_seconds
        )

        # 4. Deny access if blocked
        if is_blocked:
            # Raising Throttled automatically returns an HTTP 429 Too Many Requests response
            raise Throttled(detail="Rate limit exceeded. Please wait a moment before trying again.")
            
        # 5. Allow access
        return True
