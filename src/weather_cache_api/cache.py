"""Best-effort Redis cache with an explicit TTL."""

import logging
from typing import Protocol

from pydantic import ValidationError

from weather_cache_api.schemas import WeatherResponse

logger = logging.getLogger(__name__)


class RedisLike(Protocol):
    async def get(self, name: str) -> str | None: ...

    async def set(self, name: str, value: str, ex: int) -> object: ...


class WeatherCache:
    def __init__(self, redis: RedisLike, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def key(city: str) -> str:
        return f"weather:v1:{' '.join(city.split()).casefold()}"

    async def get(self, city: str) -> WeatherResponse | None:
        try:
            value = await self.redis.get(self.key(city))
        except Exception:
            # Cache is an optimization: a Redis failure must not break the API.
            logger.warning("Redis GET failed; continuing without cache", exc_info=True)
            return None
        if value is None:
            return None
        try:
            return WeatherResponse.model_validate_json(value)
        except (ValidationError, ValueError):
            logger.warning("Discarding invalid cache entry for city %r", city)
            return None

    async def set(self, city: str, response: WeatherResponse) -> None:
        try:
            await self.redis.set(
                self.key(city), response.model_dump_json(), ex=self.ttl_seconds
            )
        except Exception:
            logger.warning("Redis SET failed; returning uncached result", exc_info=True)
