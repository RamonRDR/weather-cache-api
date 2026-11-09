"""Best-effort, Redis-backed fixed-window rate limiting per client IP."""

import hashlib
import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


class RedisLimiterLike(Protocol):
    async def eval(self, script: str, numkeys: int, *keys_and_args: object) -> object: ...


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter:
    def __init__(self, redis: RedisLimiterLike, requests: int, window_seconds: int) -> None:
        self.redis = redis
        self.requests = requests
        self.window_seconds = window_seconds

    async def check(self, ip_address: str) -> RateLimitDecision:
        # Do not store plaintext IP addresses in Redis keys.
        fingerprint = hashlib.sha256(ip_address.encode("utf-8")).hexdigest()
        key = f"rate:v1:{fingerprint}"
        try:
            count, ttl = await self.redis.eval(_LIMIT_SCRIPT, 1, key, self.window_seconds)
            count, ttl = int(count), int(ttl)
        except Exception:
            logger.warning("Redis rate limiter unavailable; allowing request", exc_info=True)
            return RateLimitDecision(allowed=True)
        if count <= self.requests:
            return RateLimitDecision(allowed=True)
        return RateLimitDecision(
            allowed=False,
            retry_after_seconds=max(1, ttl if ttl > 0 else self.window_seconds),
        )
