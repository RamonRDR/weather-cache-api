"""Synthetic, reproducible service-level benchmark with real Redis and mocked HTTP.

Usage: python scripts/benchmark.py --samples 30 --delay-ms 30
Requires a running Redis server. Results depend on the machine and are not
live Open-Meteo timings or evidence of production performance.
"""

import argparse
import asyncio
import json
import os
import statistics
import time
from math import ceil
from uuid import uuid4

import httpx
from redis.asyncio import Redis

from weather_cache_api.cache import WeatherCache
from weather_cache_api.open_meteo import OpenMeteoClient
from weather_cache_api.service import WeatherService

GEO = {
    "results": [{"name": "Benchmark City", "country": "Synthetic", "latitude": 0.0, "longitude": 0.0}]
}
CURRENT = {
    "current": {
        "time": "2026-11-06T12:00",
        "temperature_2m": 20.0,
        "relative_humidity_2m": 50,
        "apparent_temperature": 20.0,
        "precipitation": 0.0,
        "weather_code": 1,
        "wind_speed_10m": 5.0,
    }
}


def stats(times_ms: list[float]) -> dict[str, float]:
    ordered = sorted(times_ms)
    return {
        "mean_ms": round(statistics.mean(ordered), 3),
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[ceil(0.95 * len(ordered)) - 1], 3),
    }


async def benchmark(samples: int, delay_ms: float, redis_url: str) -> dict[str, object]:
    redis = Redis.from_url(redis_url, decode_responses=True)
    city = f"benchmark-{uuid4().hex}"
    key = WeatherCache.key(city)
    provider_requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal provider_requests
        provider_requests += 1
        await asyncio.sleep(delay_ms / 1000)
        if request.url.host == "geocoding-api.open-meteo.com":
            return httpx.Response(200, json=GEO)
        return httpx.Response(200, json=CURRENT)

    try:
        await redis.ping()  # Do not silently benchmark Redis fail-open mode.
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            service = WeatherService(OpenMeteoClient(http_client), WeatherCache(redis, 60))
            cold: list[float] = []
            warm: list[float] = []

            for _ in range(samples):
                await redis.delete(key)
                start = time.perf_counter()
                response = await service.get_weather(city)
                cold.append((time.perf_counter() - start) * 1000)
                if response.cached:
                    raise RuntimeError("Cold-cache measurement unexpectedly hit the cache")

            await redis.delete(key)
            await service.get_weather(city)  # Seed cache, excluded from timings.
            upstream_before_warm = provider_requests

            for _ in range(samples):
                start = time.perf_counter()
                response = await service.get_weather(city)
                warm.append((time.perf_counter() - start) * 1000)
                if not response.cached:
                    raise RuntimeError("Warm-cache measurement missed the cache")

            if provider_requests != upstream_before_warm:
                raise RuntimeError("Warm-cache path unexpectedly called the weather provider")

            cold_stats, warm_stats = stats(cold), stats(warm)
            return {
                "method": "service-level; real Redis; synthetic delayed httpx.MockTransport",
                "samples_per_mode": samples,
                "simulated_delay_per_upstream_call_ms": delay_ms,
                "uncached": cold_stats,
                "cached": warm_stats,
                "median_ratio": round(
                    cold_stats["p50_ms"] / warm_stats["p50_ms"], 2
                ) if warm_stats["p50_ms"] > 0 else None,
                "upstream_requests": provider_requests,
            }
    finally:
        await redis.delete(key)
        await redis.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=30, help="Samples per mode (min: 3)")
    parser.add_argument("--delay-ms", type=float, default=30.0, help="Synthetic per-call delay")
    parser.add_argument(
        "--redis-url",
        default=os.getenv("BENCHMARK_REDIS_URL", "redis://localhost:6379/15"),
        help="Dedicated local Redis database (do not use production)",
    )
    args = parser.parse_args()
    if args.samples < 3 or args.delay_ms < 0:
        parser.error("--samples must be >= 3 and --delay-ms must be nonnegative")
    print(json.dumps(asyncio.run(benchmark(args.samples, args.delay_ms, args.redis_url)), indent=2))


if __name__ == "__main__":
    main()
