"""Best-effort Redis cache with an explicit TTL."""

import logging
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from weather_cache_api.schemas import CacheMetricsResponse, WeatherResponse

logger = logging.getLogger(__name__)


class RedisLike(Protocol):
    async def get(self, name: str) -> str | None: ...

    async def set(self, name: str, value: str, ex: int) -> object: ...


@dataclass
class CacheMetrics:
    hits: int = 0
    misses: int = 0
    errors: int = 0

    def snapshot(self) -> CacheMetricsResponse:
        total = self.hits + self.misses
        return CacheMetricsResponse(
            cache_hits=self.hits,
            cache_misses=self.misses,
            cache_errors=self.errors,
            hit_rate=round(self.hits / total, 4) if total else 0.0,
        )


class WeatherCache:
    def __init__(self, redis: RedisLike, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds
        self.metrics = CacheMetrics()

    @staticmethod
    def key(city: str) -> str:
        return f"weather:v1:{' '.join(city.split()).casefold()}"

    async def get(self, city: str) -> WeatherResponse | None:
        try:
            value = await self.redis.get(self.key(city))
        except Exception:
            # Cache is an optimization: a Redis failure must not break the API.
            self.metrics.errors += 1
            self.metrics.misses += 1
            logger.warning("Redis GET failed; continuing without cache", exc_info=True)
            return None
        if value is None:
            self.metrics.misses += 1
            return None
        try:
            result = WeatherResponse.model_validate_json(value)
        except ValidationError:
            self.metrics.errors += 1
            self.metrics.misses += 1
            logger.warning("Discarding invalid cache entry for city %r", city)
            return None
        self.metrics.hits += 1
        return result

    async def set(self, city: str, response: WeatherResponse) -> None:
        try:
            await self.redis.set(self.key(city), response.model_dump_json(), ex=self.ttl_seconds)
        except Exception:
            self.metrics.errors += 1
            logger.warning("Redis SET failed; returning uncached result", exc_info=True)
