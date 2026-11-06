"""FastAPI entry point and HTTP error boundaries."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request

from weather_cache_api.cache import WeatherCache
from weather_cache_api.config import Settings
from weather_cache_api.open_meteo import (
    CityNotFoundError,
    InvalidProviderResponseError,
    OpenMeteoClient,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from weather_cache_api.limiter import RateLimiter
from weather_cache_api.schemas import CacheMetricsResponse, WeatherResponse
from weather_cache_api.service import WeatherService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from redis import asyncio as redis  # Loaded at startup; keeps tests independent of Redis.

    settings = Settings()
    cache_client = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as http_client:
            app.state.weather_service = WeatherService(
                OpenMeteoClient(http_client), WeatherCache(cache_client, settings.cache_ttl_seconds)
            )
            app.state.rate_limiter = RateLimiter(
                cache_client, settings.rate_limit_requests, settings.rate_limit_window_seconds
            )
            yield
    finally:
        await cache_client.aclose()


def get_weather_service(request: Request) -> WeatherService:
    return request.app.state.weather_service


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


async def enforce_rate_limit(
    request: Request,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> None:
    # Trust the ASGI peer, not an unauthenticated X-Forwarded-For header.
    client_ip = request.client.host if request.client is not None else "unknown"
    decision = await limiter.check(client_ip)
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


app = FastAPI(
    title="Weather Cache API",
    description="Current weather by city, backed by Open-Meteo and a Redis TTL cache.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/weather", response_model=WeatherResponse, tags=["weather"])
async def get_weather(
    city: Annotated[str, Query(min_length=1, max_length=100, description="City to search")],
    service: Annotated[WeatherService, Depends(get_weather_service)],
    _: Annotated[None, Depends(enforce_rate_limit)],
) -> WeatherResponse:
    city = " ".join(city.split())
    if not city:
        raise HTTPException(status_code=422, detail="City must not be blank")
    try:
        return await service.get_weather(city)
    except CityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="City not found") from exc
    except ProviderTimeoutError as exc:
        raise HTTPException(status_code=504, detail="Weather provider timed out") from exc
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Weather provider is unavailable") from exc
    except InvalidProviderResponseError as exc:
        raise HTTPException(status_code=502, detail="Invalid weather provider response") from exc


@app.get("/metrics", response_model=CacheMetricsResponse, tags=["operations"])
async def get_metrics(
    service: Annotated[WeatherService, Depends(get_weather_service)],
) -> CacheMetricsResponse:
    """In-process cache counters for this application worker only."""
    return service.cache.metrics.snapshot()
