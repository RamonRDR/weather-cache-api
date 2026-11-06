"""Integration checks against a real Redis instance (opt in locally)."""

import asyncio
import os
from uuid import uuid4

import pytest

from weather_cache_api.cache import WeatherCache
from weather_cache_api.limiter import RateLimiter
from weather_cache_api.schemas import WeatherResponse

RUN_REDIS_TESTS = os.getenv("RUN_REDIS_TESTS") == "1"
REDIS_TEST_URL = os.getenv("REDIS_TEST_URL", "redis://localhost:6379/15")
requires_redis = pytest.mark.skipif(not RUN_REDIS_TESTS, reason="Set RUN_REDIS_TESTS=1")


@requires_redis
def test_real_redis_cache_expires_after_one_second():
    from redis.asyncio import Redis

    city = f"ttl-test-{uuid4().hex}"
    payload = WeatherResponse.model_validate(
        {
            "location": {
                "name": "Synthetic City",
                "country": "Test Country",
                "latitude": 0.0,
                "longitude": 0.0,
            },
            "current": {
                "observed_at": "2026-11-06T12:00:00Z",
                "temperature_c": 20.0,
                "apparent_temperature_c": 20.0,
                "relative_humidity_percent": 50,
                "precipitation_mm": 0.0,
                "weather_code": 1,
                "wind_speed_kmh": 5.0,
            },
        }
    )

    async def verify():
        client = Redis.from_url(REDIS_TEST_URL, decode_responses=True)
        key = WeatherCache.key(city)
        try:
            await client.ping()
            cache = WeatherCache(client, ttl_seconds=1)
            assert await cache.get(city) is None
            await cache.set(city, payload)
            assert (await cache.get(city)) == payload
            assert await client.ttl(key) in (0, 1)
            await asyncio.sleep(1.2)
            assert await cache.get(city) is None
            assert cache.metrics.hits == 1
            assert cache.metrics.misses == 2
        finally:
            await client.delete(key)
            await client.aclose()

    asyncio.run(verify())


@requires_redis
def test_real_redis_rate_limit_resets_after_window():
    from redis.asyncio import Redis

    client_id = f"test-client-{uuid4().hex}"

    async def verify():
        client = Redis.from_url(REDIS_TEST_URL, decode_responses=True)
        try:
            await client.ping()
            limiter = RateLimiter(client, requests=2, window_seconds=1)
            assert (await limiter.check(client_id)).allowed
            assert (await limiter.check(client_id)).allowed
            denied = await limiter.check(client_id)
            assert denied.allowed is False
            assert denied.retry_after_seconds >= 1
            await asyncio.sleep(1.2)
            assert (await limiter.check(client_id)).allowed
        finally:
            await client.aclose()

    asyncio.run(verify())
